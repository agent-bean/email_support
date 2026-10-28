"""Exercise the production graph against real canonical and checkpoint storage."""

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from email_support.agents.email_interpretation import EmailInterpretationAgent
from email_support.agents.web_research import ApprovedResearch
from email_support.models.email_interpretation import NormalizedInputCreate
from email_support.models.persistence import CompanyCreate, ContactCreate
from email_support.models.research import (
    ChatCompletion,
    ChatCompletionRequest,
    ChatCompletionResult,
    CompletionFinishReason,
    WebSearchResult,
)
from email_support.services.briefing_attempts import BriefingAttemptJournal
from email_support.services.briefing_ownership import acquire_run_ownership
from email_support.storage.postgres.checkpoints import (
    checkpoint_saver,
    setup_checkpoints,
)
from email_support.storage.postgres.persistence.briefing_runs import (
    begin_run,
    current_run,
)
from email_support.storage.postgres.persistence.core import (
    create_company,
    create_contact,
)
from email_support.storage.postgres.persistence.identity import create_normalized_input
from email_support.tools.execution import RunBudget, ToolExecutor
from email_support.tools.research import build_research_tools
from email_support.workflows.company_briefing.graph import (
    create_graph,
    ensure_review_pause,
)
from email_support.workflows.company_briefing.runtime import ProductionRuntime


class Gateway:
    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResult:
        assert request.tools is None
        if (
            request.response_schema
            and request.response_schema.get("title") == "EmailInterpretation"
        ):
            data: dict[str, Any] = {
                "relevance": "relevant",
                "follow_up_intent": "reply",
                "company_candidates": [],
                "contact_candidates": [],
                "stated_needs": [],
                "ambiguity_reasons": [],
                "unknowns": [],
            }
        else:
            data = {
                "claims": [
                    {
                        "id": "need-1",
                        "kind": "need",
                        "text": "Discuss planning",
                        "evidence_ids": ["email"],
                    }
                ]
            }
        return ChatCompletionResult(
            completion=ChatCompletion(
                content=json.dumps(data), finish_reason=CompletionFinishReason.STOP
            )
        )


class Search:
    async def search(
        self, company: Any, topic: Any, *, max_results: int
    ) -> WebSearchResult:
        return WebSearchResult(sources=[])


class Fetch:
    async def fetch(self, url: str, *, source_id: Any) -> Any:
        pytest.fail("empty search must not fetch")


@pytest.mark.asyncio
async def test_graph_binds_and_persists_pause_in_postgres(
    database_url: str,
    database_lifecycle: Any,
    database_engine: AsyncEngine,
    database_sessions: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    async def backup() -> None:
        await asyncio.to_thread(
            database_lifecycle.backup_database,
            database_url.rsplit("/", 1)[-1],
            "graph-checkpoint",
        )

    await setup_checkpoints(database_url, backup)
    value = NormalizedInputCreate.model_validate(
        {
            "origin_kind": "evaluation",
            "origin_key": str(uuid4()),
            "payload": {
                "sender_email": "contact@example.com",
                "subject": "Planning",
                "body": "Discuss planning",
                "received_at": datetime.now(UTC),
                "meeting_state": "absent",
                "meeting": None,
            },
        }
    )
    run_id = uuid4()
    public = ApprovedResearch.model_validate(
        {"company": "microsoft", "topics": ["company_overview"]}
    )
    async with database_sessions() as session, session.begin():
        company = await create_company(
            session, CompanyCreate(name="Microsoft", domain="example.com")
        )
        await create_contact(
            session,
            ContactCreate(
                email="contact@example.com", company_id=company.id, display_name=None
            ),
        )
        source = await create_normalized_input(session, value)
        await begin_run(session, run_id, source.id, source.content_hash, "a" * 64)
    async with acquire_run_ownership(database_engine, run_id) as owner:
        async with checkpoint_saver(database_url) as saver:
            tools, _ = build_research_tools(
                Search(), Fetch(), approved_companies=frozenset({public.company})
            )
            executor = ToolExecutor(
                tools,
                RunBudget(
                    max_calls=5, max_attempts=1, max_concurrency=1, deadline_seconds=10
                ),
                journal=BriefingAttemptJournal(owner, 5),
            )
            gateway = Gateway()
            runtime = ProductionRuntime(
                owner=owner,
                input_value=value,
                config_hash="a" * 64,
                run_id=run_id,
                approved_company_id=company.id,
                interpreter=EmailInterpretationAgent(gateway, "model", executor),
                gateway=gateway,
                model="model",
                executor=executor,
            )
            graph = create_graph(runtime, saver)
            config = {"configurable": {"thread_id": str(run_id)}}
            result = await owner.supervise(
                graph.ainvoke(
                    {
                        "run_id": str(run_id),
                        "input_id": str(source.id),
                        "public_request": public.model_dump(mode="json"),
                    },
                    config,
                    durability="sync",
                )
            )
            assert result["__interrupt__"]
            async with owner.transaction() as session:
                row = await current_run(session, run_id)
                assert row.status == "pending_review"
                assert str(row.briefing_version_id) == result["binding"]["version_id"]
            await saver.adelete_thread(str(run_id))
            await owner.supervise(
                ensure_review_pause(
                    graph,
                    config,
                    run_id=str(run_id),
                    input_id=str(source.id),
                    public_request=public.model_dump(mode="json"),
                    binding=result["binding"],
                )
            )
            async with owner.transaction() as session:
                row = await current_run(session, run_id)
                assert str(row.briefing_version_id) == result["binding"]["version_id"]
    async with checkpoint_saver(database_url) as saver:
        graph = create_graph(runtime, saver)
        state = await graph.aget_state(config)
        assert state.values["binding"] == result["binding"]
        assert state.next == ("approval",)
    output = tmp_path / "inspect.json"
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "scripts/run_company_briefing.py",
        "inspect",
        "--run-id",
        str(run_id),
        "--output",
        str(output),
        env={**os.environ, "EMAIL_SUPPORT_DATABASE_URL": database_url},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    assert process.returncode == 0, stderr.decode()
    inspected = json.loads(output.read_text())
    assert inspected["status"] == "pending_review"
    assert inspected["version_id"] == result["binding"]["version_id"]


@pytest.mark.asyncio
async def test_process_crash_after_binding_recovers_same_version(
    database_url: str,
    database_lifecycle: Any,
    database_engine: AsyncEngine,
    database_sessions: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    async def backup() -> None:
        await asyncio.to_thread(
            database_lifecycle.backup_database,
            database_url.rsplit("/", 1)[-1],
            "crash-checkpoint",
        )

    await setup_checkpoints(database_url, backup)
    run_id = uuid4()
    value = NormalizedInputCreate.model_validate(
        {
            "origin_kind": "evaluation",
            "origin_key": str(run_id),
            "payload": {
                "sender_email": "crash@example.com",
                "subject": "Planning",
                "body": "Discuss planning",
                "received_at": datetime.now(UTC),
                "meeting_state": "absent",
                "meeting": None,
            },
        }
    )
    public = ApprovedResearch.model_validate(
        {"company": "microsoft", "topics": ["company_overview"]}
    )
    async with database_sessions() as session, session.begin():
        company = await create_company(
            session, CompanyCreate(name="Microsoft", domain="example.com")
        )
        await create_contact(
            session,
            ContactCreate(
                email="crash@example.com", company_id=company.id, display_name=None
            ),
        )
        source = await create_normalized_input(session, value)
        await begin_run(session, run_id, source.id, source.content_hash, "a" * 64)
    config_path = tmp_path / "crash-input.json"
    config_path.write_text(
        json.dumps(
            {
                "run_id": str(run_id),
                "input_id": str(source.id),
                "company_id": str(company.id),
                "input": value.model_dump(mode="json"),
                "public": public.model_dump(mode="json"),
            }
        )
    )
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "tests.database.workflows.crash_after_binding",
        str(config_path),
        env={**os.environ, "EMAIL_SUPPORT_DATABASE_URL": database_url},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await child.communicate()
    assert child.returncode == 73, stderr.decode()
    async with acquire_run_ownership(database_engine, run_id) as owner:
        async with owner.transaction() as session:
            row = await current_run(session, run_id)
            assert (
                row.status == "pending_review" and row.briefing_version_id is not None
            )
            binding = {
                "briefing_id": str(row.briefing_id),
                "version_id": str(row.briefing_version_id),
            }
        async with checkpoint_saver(database_url) as saver:
            tools, _ = build_research_tools(
                Search(), Fetch(), approved_companies=frozenset({public.company})
            )
            executor = ToolExecutor(
                tools,
                RunBudget(
                    max_calls=5, max_attempts=1, max_concurrency=1, deadline_seconds=10
                ),
                journal=BriefingAttemptJournal(owner, 5),
            )
            gateway = Gateway()
            runtime = ProductionRuntime(
                owner=owner,
                input_value=value,
                config_hash="a" * 64,
                run_id=run_id,
                approved_company_id=company.id,
                interpreter=EmailInterpretationAgent(gateway, "model", executor),
                gateway=gateway,
                model="model",
                executor=executor,
            )
            graph = create_graph(runtime, saver)
            config = {"configurable": {"thread_id": str(run_id)}}
            await owner.supervise(
                ensure_review_pause(
                    graph,
                    config,
                    run_id=str(run_id),
                    input_id=str(source.id),
                    public_request=public.model_dump(mode="json"),
                    binding=binding,
                )
            )
            state = await graph.aget_state(config)
            assert state.next == ("approval",) and state.values["binding"] == binding
        async with owner.transaction() as session:
            row = await current_run(session, run_id)
            assert str(row.briefing_version_id) == binding["version_id"]
