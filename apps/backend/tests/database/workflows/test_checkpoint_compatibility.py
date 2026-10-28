from __future__ import annotations

from typing import Any, TypedDict

import psycopg
import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from psycopg.rows import dict_row
from sqlalchemy.engine import make_url


class State(TypedDict):
    reference: str


async def pause(state: State) -> dict[str, str]:
    interrupt({"reference": state["reference"]})
    return {}


def compile_graph(saver: AsyncPostgresSaver) -> Any:
    graph = StateGraph(State)
    graph.add_node("pause", pause)
    graph.add_edge(START, "pause")
    graph.add_edge("pause", END)
    return graph.compile(checkpointer=saver)


@pytest.mark.asyncio
async def test_checkpoint_pause_survives_new_connection(database_url: str) -> None:
    url = make_url(database_url).set(drivername="postgresql")
    dsn = url.render_as_string(hide_password=False)
    async with await psycopg.AsyncConnection.connect(
        dsn, autocommit=True, row_factory=dict_row
    ) as conn:
        await conn.execute("CREATE SCHEMA checkpoint_preflight")
        await conn.execute("SET search_path TO checkpoint_preflight")
        saver = AsyncPostgresSaver(
            conn, serde=JsonPlusSerializer(allowed_msgpack_modules=[])
        )
        await saver.setup()
        await saver.setup()
        graph = compile_graph(saver)
        config = {"configurable": {"thread_id": "preflight"}}
        result = await graph.ainvoke(
            {"reference": "version-1"}, config, durability="sync"
        )
        assert result["__interrupt__"][0].value == {"reference": "version-1"}
    async with await psycopg.AsyncConnection.connect(
        dsn, autocommit=True, row_factory=dict_row
    ) as conn:
        await conn.execute("SET search_path TO checkpoint_preflight")
        saver = AsyncPostgresSaver(
            conn, serde=JsonPlusSerializer(allowed_msgpack_modules=[])
        )
        state = await compile_graph(saver).aget_state(config)
        assert state.values["reference"] == "version-1"
        assert state.next == ("pause",)


@pytest.mark.asyncio
async def test_advisory_lock_survives_autocommit_transaction_transition(
    database_engine: Any,
) -> None:
    from sqlalchemy import text

    async with database_engine.connect() as owner, database_engine.connect() as other:
        owner = await owner.execution_options(isolation_level="AUTOCOMMIT")
        locked = await owner.scalar(text("SELECT pg_try_advisory_lock(92641)"))
        assert locked is True
        await owner.commit()
        owner = await owner.execution_options(isolation_level="READ COMMITTED")
        async with owner.begin():
            assert await owner.scalar(text("SELECT pg_backend_pid()")) is not None
            assert (
                await other.scalar(text("SELECT pg_try_advisory_lock(92641)")) is False
            )
        owner = await owner.execution_options(isolation_level="AUTOCOMMIT")
        assert await owner.scalar(text("SELECT pg_advisory_unlock(92641)")) is True
        await owner.commit()
        assert await other.scalar(text("SELECT pg_try_advisory_lock(92641)")) is True
        assert await other.scalar(text("SELECT pg_advisory_unlock(92641)")) is True


@pytest.mark.asyncio
async def test_guarded_checkpoint_setup_and_recovery(
    database_url: str, database_lifecycle: Any
) -> None:
    import asyncio

    from email_support.storage.postgres.checkpoints import (
        CheckpointSetupRequired,
        checkpoint_saver,
        setup_checkpoints,
    )

    with pytest.raises(CheckpointSetupRequired):
        async with checkpoint_saver(database_url):
            pytest.fail("uninitialized saver accepted")

    async def backup() -> None:
        name = database_url.rsplit("/", 1)[-1]
        await asyncio.to_thread(
            database_lifecycle.backup_database, name, "checkpoint-setup"
        )

    await setup_checkpoints(database_url, backup)
    await setup_checkpoints(database_url, backup)
    config = {"configurable": {"thread_id": "guarded"}}
    async with checkpoint_saver(database_url) as saver:
        graph = compile_graph(saver)
        await graph.ainvoke({"reference": "version-2"}, config, durability="sync")
    async with checkpoint_saver(database_url) as saver:
        state = await compile_graph(saver).aget_state(config)
        assert state.values["reference"] == "version-2"
        assert state.next == ("pause",)
    archive = await asyncio.to_thread(
        database_lifecycle.backup_database,
        database_url.rsplit("/", 1)[-1],
        "checkpoint-restore-source",
    )
    restored = await asyncio.to_thread(
        database_lifecycle.restore_target, archive, "checkpoint-restore"
    )
    try:
        async with checkpoint_saver(database_lifecycle.target_url(restored)) as saver:
            state = await compile_graph(saver).aget_state(config)
            assert state.values["reference"] == "version-2"
            assert state.next == ("pause",)
    finally:
        await asyncio.to_thread(database_lifecycle.drop_target, restored)
