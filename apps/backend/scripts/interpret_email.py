"""Run local email interpretation and explicit owner identity corrections."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import stat
import sys
from pathlib import Path
from uuid import uuid4

import httpx2
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from email_support.agents.email_interpretation import EmailInterpretationAgent
from email_support.integrations.llm_gateway import GatewayClient
from email_support.models.email_interpretation import (
    CompanyCorrectionRequest,
    NormalizedInputCreate,
)
from email_support.research_config import ResearchSettings
from email_support.services.company_identity import CompanyIdentityService
from email_support.storage.postgres.persistence.database import (
    create_database_engine,
    create_session_factory,
    dispose_database_engine,
)
from email_support.storage.postgres.persistence.identity import create_normalized_input
from email_support.tools.execution import RunBudget, ToolExecutor


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_private_json(path: Path, value: object) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, sort_keys=True, indent=2)
        output.write("\n")


def _database_url() -> str:
    value = os.environ.get("EMAIL_SUPPORT_DATABASE_URL", "")
    if not value.startswith("postgresql+psycopg://"):
        raise ValueError("EMAIL_SUPPORT_DATABASE_URL must use async Psycopg")
    return value


async def _correct(request_path: Path, output_path: Path) -> None:
    request = CompanyCorrectionRequest.model_validate(_read_json(request_path))
    engine = create_database_engine(_database_url())
    sessions = create_session_factory(engine)
    try:
        async with sessions() as session, session.begin():
            result = await CompanyIdentityService(session).correct(request)
        _write_private_json(
            output_path,
            {
                "contact_id": str(result.id),
                "company_id": str(result.company_id) if result.company_id else None,
                "identity_revision": result.identity_revision,
            },
        )
    finally:
        await dispose_database_engine(engine)


async def _interpret(input_path: Path, output_path: Path) -> None:
    normalized = NormalizedInputCreate.model_validate(_read_json(input_path))
    settings = ResearchSettings.from_environment(os.environ)
    engine = create_database_engine(_database_url())
    sessions: async_sessionmaker[AsyncSession] = create_session_factory(engine)
    run_id = uuid4()
    try:
        async with httpx2.AsyncClient() as client:
            gateway = GatewayClient(settings, client)
            executor = ToolExecutor(
                [],
                RunBudget(
                    max_calls=1,
                    max_attempts=settings.max_attempts,
                    max_concurrency=1,
                    deadline_seconds=settings.total_deadline_seconds,
                ),
            )
            agent = EmailInterpretationAgent(gateway, settings.gateway_model, executor)
            interpretation = await agent.interpret(normalized, run_id=run_id)
        async with sessions() as session, session.begin():
            persisted = await create_normalized_input(session, normalized)
            identity = await CompanyIdentityService(session).resolve(
                persisted, interpretation
            )
        _write_private_json(
            output_path,
            {
                "input_id": str(persisted.id),
                "run_id": str(run_id),
                "prompt_version": "email-interpretation-v1",
                "interpretation": interpretation.model_dump(mode="json"),
                "identity": identity.model_dump(mode="json"),
                "provider_events": [
                    event.model_dump(mode="json") for event in executor.events
                ],
            },
        )
    finally:
        await dispose_database_engine(engine)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    interpret = commands.add_parser("interpret")
    interpret.add_argument("--input", type=Path, required=True)
    interpret.add_argument("--output", type=Path, required=True)
    correct = commands.add_parser("correct-company")
    correct.add_argument("--request", type=Path, required=True)
    correct.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "interpret":
            asyncio.run(_interpret(args.input, args.output))
        else:
            asyncio.run(_correct(args.request, args.output))
    except (OSError, ValueError, ValidationError, httpx2.HTTPError) as error:
        print(f"email operation failed: {type(error).__name__}", file=sys.stderr)
        return 1
    except Exception as error:
        # Provider and database exception strings can contain sensitive details.
        print(f"email operation failed: {type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
