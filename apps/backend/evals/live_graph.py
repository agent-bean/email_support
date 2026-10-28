"""Explicit live graph evaluation capture; semantic reviews remain human-owned."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.engine import make_url

from email_support.agents.web_research import ApprovedResearch
from email_support.integrations.provider_http import ProviderCallError
from email_support.models.email_interpretation import (
    InputOriginKind,
    NormalizedInputCreate,
)
from email_support.models.persistence import TimedMeetingTime
from evals.models import EvaluationCase
from evals.runner import EvaluationInputError, load_dataset
from scripts.run_company_briefing import _run
from scripts.test_database import DatabaseLifecycle


class CaseInvocation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    case_id: str = Field(min_length=1, max_length=100)
    input: Path
    public_research: Path
    company_id: UUID
    run_id: UUID


class InvocationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    cases: list[CaseInvocation] = Field(min_length=1, max_length=1000)


def verify_input(case: EvaluationCase, value: NormalizedInputCreate) -> None:
    payload = value.payload
    if value.origin_kind is not InputOriginKind.EVALUATION:
        raise EvaluationInputError("live cases require evaluation-origin inputs")
    if (
        payload.sender_email != case.email.from_address
        or payload.subject != case.email.subject
        or payload.body != case.email.body
        or payload.received_at != case.clock
    ):
        raise EvaluationInputError("normalized email does not match dataset case")
    if case.meeting is None:
        if payload.meeting is not None or payload.meeting_state.value != "absent":
            raise EvaluationInputError("normalized meeting does not match dataset case")
        return
    meeting = payload.meeting
    expected = case.meeting
    if (
        meeting is None
        or not isinstance(meeting.time, TimedMeetingTime)
        or expected.ends_at is None
        or meeting.title != expected.title
        or meeting.description != expected.description
        or meeting.time.starts_at != expected.starts_at
        or meeting.time.ends_at != expected.ends_at
        or meeting.attendees != expected.attendees
    ):
        raise EvaluationInputError("normalized meeting does not match dataset case")


async def capture(dataset_path: Path, manifest_path: Path) -> dict[str, Any]:
    dataset = load_dataset(dataset_path)
    try:
        manifest = InvocationManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise EvaluationInputError("invalid live invocation manifest") from error
    cases = {case.id: case for case in dataset.cases}
    seen: set[str] = set()
    run_ids: set[UUID] = set()
    for invocation in manifest.cases:
        if (
            invocation.case_id not in cases
            or invocation.case_id in seen
            or invocation.run_id in run_ids
        ):
            raise EvaluationInputError(
                "manifest has unknown or duplicate cases or run IDs"
            )
        seen.add(invocation.case_id)
        run_ids.add(invocation.run_id)
        try:
            value = NormalizedInputCreate.model_validate_json(
                invocation.input.read_text(encoding="utf-8")
            )
            ApprovedResearch.model_validate_json(
                invocation.public_research.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError) as error:
            raise EvaluationInputError("invalid normalized case input") from error
        verify_input(cases[invocation.case_id], value)
    lifecycle = DatabaseLifecycle.from_environment()
    database_value = os.environ.get("EMAIL_SUPPORT_DATABASE_URL")
    if not database_value:
        raise EvaluationInputError("live evaluation requires an owned test database")
    database_url = make_url(database_value)
    database_name = database_url.database
    if database_name is None or database_url != make_url(
        lifecycle.target_url(database_name)
    ):
        raise EvaluationInputError("live evaluation requires an owned test database")
    await asyncio.to_thread(
        lifecycle.backup_database, database_name, "before-live-evaluation"
    )
    captures: list[dict[str, Any]] = []
    for invocation in manifest.cases:
        case = cases[invocation.case_id]
        try:
            result = await _run(
                argparse.Namespace(
                    input=invocation.input,
                    public_research=invocation.public_research,
                    company_id=str(invocation.company_id),
                    run_id=str(invocation.run_id),
                    recover=False,
                )
            )
            if result.get("status") == "pending_review" and not result.get("report"):
                raise EvaluationInputError("run has no fresh graph capture")
            captures.append(
                {
                    "case_id": case.id,
                    "case_hash": case.content_hash(),
                    "status": "review_pending",
                    "result": result,
                    "claim_support": "not_reviewed",
                    "meeting_usefulness": "not_reviewed",
                }
            )
        except Exception as error:
            captures.append(
                {
                    "case_id": case.id,
                    "case_hash": case.content_hash(),
                    "status": "execution_error",
                    "error_type": type(error).__name__,
                    "error_category": (
                        error.category.value
                        if isinstance(error, ProviderCallError)
                        else None
                    ),
                    "claim_support": "not_reviewed",
                    "meeting_usefulness": "not_reviewed",
                }
            )
    return {
        "mode": "live",
        "dataset_version": dataset.version,
        "dataset_hash": dataset.content_hash(),
        "case_count": len(dataset.cases),
        "captured_count": len(captures),
        "not_run": sorted(set(cases) - seen),
        "cases": captures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(args.output, flags, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            result = asyncio.run(capture(args.dataset, args.manifest))
            json.dump(result, output, ensure_ascii=False, indent=2)
            output.write("\n")
    except Exception as error:
        print(f"live evaluation failed: {type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
