"""Exclusive session-scoped ownership for one local briefing run."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from typing import TypeVar
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession


class RunBusy(RuntimeError):
    """Another invocation owns this run."""


class OwnershipLost(RuntimeError):
    """The physical connection holding the lock is no longer usable."""


T = TypeVar("T")


def _lock_key(run_id: UUID) -> int:
    digest = hashlib.blake2b(run_id.bytes, digest_size=8, person=b"briefing").digest()
    return int.from_bytes(digest, "big", signed=True)


class RunOwnership:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection
        self._transaction_lock = asyncio.Lock()

    async def supervise(self, operation: Awaitable[T], *, interval: float = 1) -> T:
        """Cancel work if the advisory-lock session becomes unavailable."""
        if interval <= 0:
            raise ValueError("monitor interval must be positive")
        task = asyncio.ensure_future(operation)

        async def monitor() -> None:
            while True:
                await asyncio.sleep(interval)
                try:
                    async with self.transaction() as session:
                        await session.execute(text("SELECT 1"))
                except Exception as error:
                    raise OwnershipLost("run ownership connection was lost") from error

        watchdog = asyncio.create_task(monitor())
        try:
            done, _ = await asyncio.wait(
                {task, watchdog}, return_when=asyncio.FIRST_COMPLETED
            )
            if watchdog in done:
                await watchdog
                raise OwnershipLost("ownership monitor stopped")
            return await task
        finally:
            for pending in (task, watchdog):
                if not pending.done():
                    pending.cancel()
            await asyncio.gather(task, watchdog, return_exceptions=True)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        async with self._transaction_lock:
            if self._connection.closed or self._connection.invalidated:
                raise OwnershipLost("run ownership connection was lost")
            connection = await self._connection.execution_options(
                isolation_level="READ COMMITTED"
            )
            try:
                async with connection.begin():
                    async with AsyncSession(
                        bind=connection, expire_on_commit=False
                    ) as session:
                        yield session
                        await session.flush()
            finally:
                if not connection.closed and not connection.invalidated:
                    await connection.execution_options(isolation_level="AUTOCOMMIT")


@asynccontextmanager
async def acquire_run_ownership(
    engine: AsyncEngine, run_id: UUID
) -> AsyncIterator[RunOwnership]:
    key = _lock_key(run_id)
    async with engine.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        acquired = await conn.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": key}
        )
        await conn.commit()
        if not acquired:
            raise RunBusy("run is already owned")
        try:
            yield RunOwnership(conn)
        finally:
            if not conn.closed and not conn.invalidated:
                await conn.scalar(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                await conn.commit()
