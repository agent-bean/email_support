"""Run, inspect or recover a bounded company briefing on local PostgreSQL."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx2

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from email_support.agents.email_interpretation import (
    PROMPT_VERSION,
    EmailInterpretationAgent,
)
from email_support.agents.report_generation import (
    SYNTHESIS_PROMPT_VERSION,
    ReportValidationError,
)
from email_support.agents.web_research import ApprovedResearch
from email_support.integrations.llm_gateway import GatewayClient
from email_support.integrations.provider_http import ProviderCallError
from email_support.integrations.tavily import TavilySearch
from email_support.integrations.web_fetch import WebFetcher
from email_support.models.email_interpretation import NormalizedInputCreate
from email_support.research_config import ResearchSettings
from email_support.services.briefing_attempts import BriefingAttemptJournal
from email_support.services.briefing_ownership import acquire_run_ownership
from email_support.storage.postgres.checkpoints import checkpoint_saver
from email_support.storage.postgres.persistence.briefing_runs import (
    begin_run,
    current_run,
)
from email_support.storage.postgres.persistence.core import (
    PersistenceConflict,
    PersistenceNotFound,
)
from email_support.storage.postgres.persistence.database import (
    create_database_engine,
    dispose_database_engine,
)
from email_support.storage.postgres.persistence.identity import create_normalized_input
from email_support.storage.postgres.persistence.tables import BriefingRunRow
from email_support.tools.execution import RunBudget, ToolExecutor
from email_support.tools.research import build_research_tools
from email_support.workflows.company_briefing.graph import (
    create_graph,
    ensure_review_pause,
)
from email_support.workflows.company_briefing.runtime import ProductionRuntime
from scripts.interpret_email import _database_url, _read_json, _write_private_json  # noqa: E402


def _config_hash(
    settings: ResearchSettings, public: ApprovedResearch, company_id: UUID
) -> str:
    config = {
        "public": public.model_dump(mode="json"),
        "company_id": str(company_id),
        "gateway_url": str(settings.gateway_base_url),
        "model": settings.gateway_model,
        "prompt_version": PROMPT_VERSION,
        "synthesis_prompt_version": SYNTHESIS_PROMPT_VERSION,
        "request_timeout_seconds": settings.request_timeout_seconds,
        "total_deadline_seconds": settings.total_deadline_seconds,
        "max_attempts": settings.max_attempts,
        "max_tool_calls": settings.max_tool_calls,
        "max_concurrency": settings.max_concurrency,
        "max_search_results": settings.max_search_results,
        "max_fetch_bytes": settings.max_fetch_bytes,
        "max_provider_response_bytes": settings.max_provider_response_bytes,
    }
    return hashlib.sha256(
        json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def _inspect(run_id: UUID) -> dict[str, object]:
    engine = create_database_engine(_database_url())
    try:
        async with acquire_run_ownership(engine, run_id) as owner:
            async with owner.transaction() as session:
                row = await session.get(BriefingRunRow, run_id)
                if row is None:
                    raise PersistenceNotFound("run not found")
                if row.status in {"running", "pending_review"}:
                    row = await current_run(session, run_id)
                return {
                    "run_id": str(run_id),
                    "status": row.status,
                    "stop_reason": row.stop_reason,
                    "briefing_id": str(row.briefing_id) if row.briefing_id else None,
                    "version_id": str(row.briefing_version_id)
                    if row.briefing_version_id
                    else None,
                    "attempts": row.attempts,
                }
    finally:
        await dispose_database_engine(engine)


async def _run(args: argparse.Namespace) -> dict[str, object]:
    normalized = NormalizedInputCreate.model_validate(_read_json(args.input))
    public = ApprovedResearch.model_validate(_read_json(args.public_research))
    company_id = UUID(args.company_id)
    run_id = UUID(args.run_id)
    settings = ResearchSettings.from_environment(os.environ)
    config_hash = _config_hash(settings, public, company_id)
    database_url = _database_url()
    engine = create_database_engine(database_url)
    try:
        async with checkpoint_saver(database_url) as saver:
            async with acquire_run_ownership(engine, run_id) as owner:
                async with owner.transaction() as session:
                    source = await create_normalized_input(session, normalized)
                    row = await begin_run(
                        session, run_id, source.id, source.content_hash, config_hash
                    )
                    if row.status == "pending_review":
                        row = await current_run(session, run_id)
                    pending_binding = (
                        {
                            "briefing_id": str(row.briefing_id),
                            "version_id": str(row.briefing_version_id),
                        }
                        if row.status == "pending_review"
                        else None
                    )
                    if row.status == "stopped":
                        return {
                            "run_id": str(run_id),
                            "status": "stopped",
                            "stop_reason": row.stop_reason,
                        }
                    if row.status == "running":
                        await current_run(session, run_id)
                    attempts = len(row.attempts)
                    remaining = settings.total_deadline_seconds - max(
                        0.0, (datetime.now(UTC) - row.created_at).total_seconds()
                    )
                    if remaining <= 0 and pending_binding is None:
                        raise PersistenceConflict("run deadline exhausted")
                    if pending_binding is not None:
                        remaining = settings.total_deadline_seconds
                async with httpx2.AsyncClient(
                    timeout=httpx2.Timeout(settings.request_timeout_seconds),
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    gateway = GatewayClient(settings, client)
                    tools, _ = build_research_tools(
                        TavilySearch(settings, client),
                        WebFetcher(
                            max_bytes=settings.max_fetch_bytes,
                            timeout_seconds=settings.request_timeout_seconds,
                        ),
                        approved_companies=frozenset({public.company}),
                    )
                    budget = RunBudget(
                        max_calls=settings.max_tool_calls,
                        max_attempts=settings.max_attempts,
                        max_concurrency=settings.max_concurrency,
                        deadline_seconds=remaining,
                        calls_used=min(attempts, settings.max_tool_calls),
                        attempts_used=attempts,
                    )
                    executor = ToolExecutor(
                        tools,
                        budget,
                        journal=BriefingAttemptJournal(
                            owner, settings.max_tool_calls * settings.max_attempts
                        ),
                    )
                    runtime = ProductionRuntime(
                        owner=owner,
                        input_value=normalized,
                        config_hash=config_hash,
                        run_id=run_id,
                        approved_company_id=company_id,
                        interpreter=EmailInterpretationAgent(
                            gateway, settings.gateway_model, executor
                        ),
                        gateway=gateway,
                        model=settings.gateway_model,
                        executor=executor,
                    )
                    graph = create_graph(runtime, saver)
                    config = {"configurable": {"thread_id": str(run_id)}}
                    if pending_binding is not None:
                        await owner.supervise(
                            ensure_review_pause(
                                graph,
                                config,
                                run_id=str(run_id),
                                input_id=str(source.id),
                                public_request=public.model_dump(mode="json"),
                                binding=pending_binding,
                            )
                        )
                        return {
                            "run_id": str(run_id),
                            "status": "pending_review",
                            "binding": pending_binding,
                        }
                    snapshot = await graph.aget_state(config)
                    if snapshot.values:
                        if not args.recover:
                            raise PersistenceConflict(
                                "existing checkpoint requires recover"
                            )
                        if snapshot.values.get("run_id") != str(
                            run_id
                        ) or snapshot.values.get("input_id") != str(source.id):
                            raise PersistenceConflict("checkpoint identity differs")
                        if snapshot.values.get("public_request") != public.model_dump(
                            mode="json"
                        ):
                            raise PersistenceConflict("checkpoint request differs")
                        result = await owner.supervise(
                            graph.ainvoke(None, config, durability="sync")
                        )
                    else:
                        if row.status == "running":
                            raise PersistenceConflict("running state has no checkpoint")
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
                    async with owner.transaction() as session:
                        stored = await session.get(BriefingRunRow, run_id)
                        if stored is None:
                            raise PersistenceNotFound("run not found")
                        if result.get("stop_reason"):
                            if stored.status != "stopped":
                                raise PersistenceConflict(
                                    "stopped result is inconsistent"
                                )
                        else:
                            stored = await current_run(session, run_id)
                            if (
                                stored.status != "pending_review"
                                or not result.get("__interrupt__")
                                or result.get("binding")
                                != {
                                    "briefing_id": str(stored.briefing_id),
                                    "version_id": str(stored.briefing_version_id),
                                }
                            ):
                                raise PersistenceConflict(
                                    "review pause is inconsistent"
                                )
                    return {
                        "run_id": str(run_id),
                        "config_hash": config_hash,
                        "status": "stopped"
                        if result.get("stop_reason")
                        else "pending_review",
                        "stop_reason": result.get("stop_reason"),
                        "binding": result.get("binding"),
                        "resolution": result.get("resolution"),
                        "report": result.get("report"),
                        "research": result.get("research"),
                        "events": [
                            event.model_dump(mode="json") for event in executor.events
                        ],
                    }
    finally:
        await dispose_database_engine(engine)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "recover"):
        command = commands.add_parser(name)
        command.add_argument("--input", type=Path, required=True)
        command.add_argument("--public-research", type=Path, required=True)
        command.add_argument("--company-id", required=True)
        command.add_argument("--run-id", required=True)
        command.add_argument("--output", type=Path, required=True)
        command.set_defaults(recover=name == "recover")
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--run-id", required=True)
    inspect.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = asyncio.run(
            _inspect(UUID(args.run_id)) if args.command == "inspect" else _run(args)
        )
        _write_private_json(args.output, result)
    except ReportValidationError as error:
        print(f"briefing report validation failed: {error.reason}", file=sys.stderr)
        return 1
    except ProviderCallError as error:
        print(f"briefing provider failed: {error.category.value}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"briefing operation failed: {type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
