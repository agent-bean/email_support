import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from email_support.services.briefing_ownership import (
    OwnershipLost,
    RunBusy,
    acquire_run_ownership,
)


@pytest.mark.asyncio
async def test_run_lock_rejects_concurrent_owner_and_releases(
    database_engine: AsyncEngine,
) -> None:
    run_id = uuid4()
    async with acquire_run_ownership(database_engine, run_id) as owner:
        async with owner.transaction() as session:
            assert await session.scalar(text("SELECT 42")) == 42
        with pytest.raises(RunBusy):
            async with acquire_run_ownership(database_engine, run_id):
                pytest.fail("second owner acquired lock")
    async with acquire_run_ownership(database_engine, run_id):
        pass


@pytest.mark.asyncio
async def test_lost_connection_cannot_reacquire_and_write(
    database_engine: AsyncEngine,
) -> None:
    async with acquire_run_ownership(database_engine, uuid4()) as owner:
        await owner._connection.invalidate()
        with pytest.raises(OwnershipLost):
            async with owner.transaction():
                pytest.fail("lost owner entered transaction")


@pytest.mark.asyncio
async def test_owner_connection_loss_rolls_back_pending_write(
    database_engine: AsyncEngine,
) -> None:
    from sqlalchemy.exc import DBAPIError

    run_id, company_id = uuid4(), uuid4()
    with pytest.raises(DBAPIError):
        async with acquire_run_ownership(database_engine, run_id) as owner:
            async with owner.transaction() as session:
                pid = await session.scalar(text("SELECT pg_backend_pid()"))
                await session.execute(
                    text("INSERT INTO companies (id, name) VALUES (:id, 'Lost owner')"),
                    {"id": company_id},
                )
                async with database_engine.connect() as killer:
                    assert (
                        await killer.scalar(
                            text("SELECT pg_terminate_backend(:pid)"), {"pid": pid}
                        )
                        is True
                    )
    async with acquire_run_ownership(database_engine, run_id) as new_owner:
        async with new_owner.transaction() as session:
            assert (
                await session.scalar(
                    text("SELECT count(*) FROM companies WHERE id = :id"),
                    {"id": company_id},
                )
                == 0
            )


@pytest.mark.asyncio
async def test_connection_loss_cancels_inflight_operation(
    database_engine: AsyncEngine,
) -> None:
    cancelled = asyncio.Event()
    started = asyncio.Event()

    async def provider() -> None:
        started.set()
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    async with acquire_run_ownership(database_engine, uuid4()) as owner:
        async with owner.transaction() as session:
            pid = await session.scalar(text("SELECT pg_backend_pid()"))
        task = asyncio.create_task(owner.supervise(provider(), interval=0.05))
        await started.wait()
        async with database_engine.connect() as killer:
            assert await killer.scalar(
                text("SELECT pg_terminate_backend(:pid)"), {"pid": pid}
            )
        with pytest.raises(OwnershipLost):
            await asyncio.wait_for(task, timeout=3)
        assert cancelled.is_set()
