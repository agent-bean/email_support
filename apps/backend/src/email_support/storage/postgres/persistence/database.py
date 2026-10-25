"""Explicit PostgreSQL engine and caller-owned session construction."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_database_engine(database_url: str) -> AsyncEngine:
    """Create an engine without connecting until the caller first uses it."""
    return create_async_engine(database_url, pool_pre_ping=True)


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create sessions whose transaction and lifetime remain caller-owned."""
    return async_sessionmaker(engine, expire_on_commit=False)


async def dispose_database_engine(engine: AsyncEngine) -> None:
    await engine.dispose()
