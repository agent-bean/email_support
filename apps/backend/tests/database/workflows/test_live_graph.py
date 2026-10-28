"""Explicit opt-in smoke of the production graph and actual provider adapters."""

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from email_support.models.persistence import CompanyCreate, ContactCreate
from email_support.storage.postgres.checkpoints import setup_checkpoints
from email_support.storage.postgres.persistence.core import (
    create_company,
    create_contact,
    get_briefing_version,
    get_evidence,
)
from email_support.storage.postgres.persistence.tables import (
    BriefingRunRow,
    BriefingVersionRow,
)
from scripts.test_database import DatabaseLifecycle


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("BRIEFING_LIVE_SMOKE") != "1", reason="explicit live opt-in required"
)
async def test_live_bounded_graph(
    database_url: str,
    database_lifecycle: DatabaseLifecycle,
    database_sessions: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    async def backup() -> None:
        await asyncio.to_thread(
            database_lifecycle.backup_database,
            database_url.rsplit("/", 1)[-1],
            "live-graph-setup",
        )

    await setup_checkpoints(database_url, backup)
    run_id = uuid4()
    async with database_sessions() as session, session.begin():
        company = await create_company(
            session, CompanyCreate(name="Microsoft", domain="microsoft.com")
        )
        await create_contact(
            session,
            ContactCreate(
                email="alex@example.com", company_id=company.id, display_name="Alex"
            ),
        )
    input_path, public_path, output_path = (
        tmp_path / "input.json",
        tmp_path / "public.json",
        tmp_path / "output.json",
    )
    input_path.write_text(
        json.dumps(
            {
                "origin_kind": "evaluation",
                "origin_key": str(run_id),
                "payload": {
                    "sender_email": "alex@example.com",
                    "sender_display_name": "Alex",
                    "subject": "Business discussion",
                    "body": (
                        "Hello, I represent Microsoft and would like to discuss "
                        "AI automation solutions for our team."
                    ),
                    "received_at": datetime.now(UTC).isoformat(),
                    "meeting_state": "absent",
                    "meeting": None,
                },
            }
        )
    )
    public_path.write_text(
        json.dumps({"company": "microsoft", "topics": ["company_overview"]})
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "scripts/run_company_briefing.py",
        "run",
        "--input",
        str(input_path),
        "--public-research",
        str(public_path),
        "--company-id",
        str(company.id),
        "--run-id",
        str(run_id),
        "--output",
        str(output_path),
        env={**os.environ, "EMAIL_SUPPORT_DATABASE_URL": database_url},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        async with database_sessions() as session:
            failed_run = await session.get(BriefingRunRow, run_id)
            attempts = failed_run.attempts if failed_run is not None else []
        pytest.fail(f"{stderr.decode().strip()}; attempts={attempts}", pytrace=False)
    output = json.loads(output_path.read_text())
    assert output["status"] == "pending_review", output
    async with database_sessions() as session:
        row = await session.get(BriefingRunRow, run_id)
        assert row is not None and row.briefing_version_id is not None
        version = await session.get(BriefingVersionRow, row.briefing_version_id)
        assert version is not None and version.sealed
        stored = await get_briefing_version(
            session, version.briefing_id, version.version_number
        )
        evidence = [
            (await get_evidence(session, evidence_id)).model_dump(mode="json")
            for evidence_id in stored.evidence_ids
        ]
    artifact = {
        "mode": "live",
        "review_status": "unreviewed",
        "run_id": str(run_id),
        "binding": output["binding"],
        "events": output["events"],
        "resolution": output["resolution"],
        "report": output["report"],
        "research": output["research"],
        "markdown": version.markdown,
        "evidence": evidence,
    }
    destination = Path("evals/results") / f"briefing-live-smoke-{run_id}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as file:
        json.dump(artifact, file, ensure_ascii=False, indent=2)
    print(f"Unreviewed live smoke artifact: {destination}")
    assert UUID(output["binding"]["version_id"]) == version.id


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("BRIEFING_LIVE_SMOKE") != "1", reason="explicit live opt-in required"
)
async def test_live_evaluator_invokes_production_graph(
    database_url: str,
    database_lifecycle: DatabaseLifecycle,
    database_sessions: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from evals.live_graph import capture
    from evals.runner import load_dataset

    async def backup() -> None:
        await asyncio.to_thread(
            database_lifecycle.backup_database,
            database_url.rsplit("/", 1)[-1],
            "live-eval-setup",
        )

    await setup_checkpoints(database_url, backup)
    dataset_path = Path("evals/datasets/briefing-v1")
    case = load_dataset(dataset_path).cases[0]
    assert case.meeting is not None and case.meeting.ends_at is not None
    run_id = uuid4()
    async with database_sessions() as session, session.begin():
        company = await create_company(
            session, CompanyCreate(name="Microsoft", domain="microsoft.com")
        )
        await create_contact(
            session,
            ContactCreate(
                email=str(case.email.from_address),
                company_id=company.id,
                display_name=None,
            ),
        )
    input_path, public_path, manifest_path = (
        tmp_path / "eval-input.json",
        tmp_path / "public.json",
        tmp_path / "manifest.json",
    )
    input_path.write_text(
        json.dumps(
            {
                "origin_kind": "evaluation",
                "origin_key": str(run_id),
                "payload": {
                    "sender_email": str(case.email.from_address),
                    "subject": case.email.subject,
                    "body": case.email.body,
                    "received_at": case.clock.isoformat(),
                    "meeting_state": "scheduled",
                    "meeting": {
                        "title": case.meeting.title,
                        "description": case.meeting.description,
                        "time": {
                            "kind": "timed",
                            "starts_at": case.meeting.starts_at.isoformat(),
                            "ends_at": case.meeting.ends_at.isoformat(),
                        },
                        "attendees": case.meeting.attendees,
                    },
                },
            }
        )
    )
    public_path.write_text(
        json.dumps({"company": "microsoft", "topics": ["company_overview"]})
    )
    manifest_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": case.id,
                        "input": str(input_path),
                        "public_research": str(public_path),
                        "company_id": str(company.id),
                        "run_id": str(run_id),
                    }
                ]
            }
        )
    )
    monkeypatch.setenv("EMAIL_SUPPORT_DATABASE_URL", database_url)
    result = await capture(dataset_path, manifest_path)
    assert (
        result["captured_count"] == 1
        and len(result["not_run"]) == len(load_dataset(dataset_path).cases) - 1
    )
    entry = result["cases"][0]
    assert entry["status"] == "review_pending", entry
    assert entry["result"]["status"] == "pending_review", entry
    assert (
        entry["claim_support"] == "not_reviewed"
        and entry["meeting_usefulness"] == "not_reviewed"
    )
    destination = Path("evals/results") / f"briefing-live-eval-{run_id}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
    print(f"Unreviewed live evaluation artifact: {destination}")
