"""Explicit checkpoint schema setup and fail-closed saver lifecycle."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import psycopg
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg.rows import DictRow, dict_row
from sqlalchemy.engine import make_url


class CheckpointSetupRequired(RuntimeError):
    """The checkpoint schema has not been initialized at the supported version."""


def _dsn(database_url: str) -> str:
    url = make_url(database_url)
    if url.drivername != "postgresql+psycopg":
        raise ValueError("checkpoint database must use postgresql+psycopg")
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


@asynccontextmanager
async def checkpoint_connection(
    database_url: str,
) -> AsyncIterator[psycopg.AsyncConnection[DictRow]]:
    async with await psycopg.AsyncConnection.connect(
        _dsn(database_url),
        autocommit=True,
        row_factory=dict_row,
        options="-c search_path=briefing_checkpoints",
    ) as connection:
        yield connection


async def setup_checkpoints(
    database_url: str, backup: Callable[[], Awaitable[None]]
) -> None:
    await backup()
    async with checkpoint_connection(database_url) as connection:
        saver = AsyncPostgresSaver(
            connection, serde=JsonPlusSerializer(allowed_msgpack_modules=[])
        )
        await saver.setup()


@asynccontextmanager
async def checkpoint_saver(database_url: str) -> AsyncIterator[AsyncPostgresSaver]:
    async with checkpoint_connection(database_url) as connection:
        try:
            cursor = await connection.execute(
                "SELECT max(v) AS version FROM checkpoint_migrations"
            )
            row = await cursor.fetchone()
        except psycopg.Error as error:
            raise CheckpointSetupRequired("checkpoint setup is missing") from error
        if row is None or row["version"] != len(AsyncPostgresSaver.MIGRATIONS) - 1:
            raise CheckpointSetupRequired("checkpoint schema version is incompatible")
        yield AsyncPostgresSaver(
            connection, serde=JsonPlusSerializer(allowed_msgpack_modules=[])
        )
