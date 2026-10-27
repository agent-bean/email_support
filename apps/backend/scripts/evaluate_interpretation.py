import argparse
import asyncio
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx2

from email_support.agents.email_interpretation import (
    PROMPT_VERSION,
    EmailInterpretationAgent,
)
from email_support.integrations.llm_gateway import GatewayClient
from email_support.integrations.provider_http import ProviderCallError
from email_support.models.email_interpretation import (
    InputOriginKind,
    MeetingState,
    NormalizedEmailInput,
    NormalizedInputCreate,
    NormalizedMeeting,
)
from email_support.models.persistence.core import TimedMeetingTime
from email_support.models.research import ChatCompletionRequest, ChatCompletionResult
from email_support.research_config import ResearchSettings
from email_support.tools.execution import RunBudget, ToolExecutor
from evals.models import EvaluationCase, EvaluationDataset
from evals.runner import load_dataset


class GatewayCapture:
    def __init__(self, gateway: GatewayClient) -> None:
        self.gateway = gateway
        self.response: ChatCompletionResult | None = None

    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResult:
        self.response = await self.gateway.complete(request)
        return self.response


def select_cases(dataset: EvaluationDataset, ids: list[str]) -> list[EvaluationCase]:
    if not ids:
        return dataset.cases
    requested = set(ids)
    if len(requested) != len(ids) or requested - {case.id for case in dataset.cases}:
        raise ValueError("Case IDs must be unique and belong to the dataset")
    return [case for case in dataset.cases if case.id in requested]


async def run(dataset_path: Path, output: Path, ids: list[str]) -> None:
    dataset = load_dataset(dataset_path)
    selected = select_cases(dataset, ids)
    if any(case.meeting and case.meeting.ends_at is None for case in selected):
        raise ValueError("Live interpretation requires an end time for timed meetings")
    settings = ResearchSettings.from_environment(os.environ).model_copy(
        update={"request_timeout_seconds": 30.0, "total_deadline_seconds": 45.0}
    )
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    application_revision = (
        revision.stdout.strip() if revision.returncode == 0 else "unknown"
    )
    source_root = Path(__file__).resolve().parents[1] / "src" / "email_support"
    implementation = hashlib.sha256()
    for source in (
        source_root / "agents" / "email_interpretation.py",
        source_root / "models" / "email_interpretation.py",
    ):
        implementation.update(source.read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    completed: list[dict[str, Any]] = []
    semaphore = asyncio.Semaphore(2)
    with os.fdopen(fd, "w", encoding="utf-8") as log:

        def write(value: dict[str, Any]) -> None:
            log.write(json.dumps(value, ensure_ascii=False) + "\n")
            log.flush()

        write(
            {
                "type": "run",
                "dataset_version": dataset.version,
                "model_id": settings.gateway_model,
                "prompt_version": PROMPT_VERSION,
                "application_revision": application_revision,
                "implementation_sha256": implementation.hexdigest(),
                "case_count": len(selected),
                "dataset_hash": dataset.content_hash(),
                "request_timeout_seconds": settings.request_timeout_seconds,
                "total_deadline_seconds": settings.total_deadline_seconds,
                "max_attempts": settings.max_attempts,
            }
        )
        print(f"Log: {output}", flush=True)
        async with httpx2.AsyncClient(
            timeout=httpx2.Timeout(settings.request_timeout_seconds),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            gateway = GatewayClient(settings, client)

            async def run_case(case: EvaluationCase) -> None:
                async with semaphore:
                    meeting = None
                    if case.meeting is not None:
                        assert case.meeting.ends_at is not None
                        meeting = NormalizedMeeting(
                            title=case.meeting.title,
                            description=case.meeting.description,
                            time=TimedMeetingTime(
                                starts_at=case.meeting.starts_at,
                                ends_at=case.meeting.ends_at,
                            ),
                            attendees=case.meeting.attendees,
                        )
                    value = NormalizedInputCreate(
                        origin_kind=InputOriginKind.EVALUATION,
                        origin_key=case.id,
                        payload=NormalizedEmailInput(
                            sender_email=case.email.from_address,
                            sender_display_name=None,
                            subject=case.email.subject,
                            body=case.email.body,
                            received_at=case.clock,
                            meeting_state=MeetingState.SCHEDULED
                            if meeting
                            else MeetingState.ABSENT,
                            meeting=meeting,
                        ),
                    )
                    executor = ToolExecutor(
                        [],
                        RunBudget(
                            max_calls=1,
                            max_attempts=settings.max_attempts,
                            max_concurrency=1,
                            deadline_seconds=settings.total_deadline_seconds,
                        ),
                    )
                    tap = GatewayCapture(gateway)
                    row: dict[str, Any] = {
                        "type": "case",
                        "case_id": case.id,
                        "language": case.language.value,
                        "scenario": case.scenario.value,
                        "expected_relevance": case.expected_relevance.value,
                        "input": value.model_dump(mode="json"),
                    }
                    try:
                        interpretation = await EmailInterpretationAgent(
                            tap, settings.gateway_model, executor
                        ).interpret(value, run_id=uuid4())
                        row.update(
                            {
                                "status": "valid",
                                "observed_relevance": interpretation.relevance.value,
                                "relevance_match": interpretation.relevance.value
                                == case.expected_relevance.value,
                                "output": interpretation.model_dump(mode="json"),
                            }
                        )
                    except ProviderCallError as error:
                        row.update(
                            {"status": "error", "error_category": error.category.value}
                        )
                    except Exception as error:
                        row.update(
                            {"status": "error", "error_type": type(error).__name__}
                        )
                    row["provider_events"] = [
                        event.model_dump(mode="json") for event in executor.events
                    ]
                    if tap.response is not None:
                        row["model_response"] = tap.response.completion.content
                        row["finish_reason"] = (
                            tap.response.completion.finish_reason.value
                        )
                    write(row)
                    completed.append(row)
                    detail = row.get(
                        "error_category",
                        row.get("observed_relevance", row.get("error_type", "")),
                    )
                    print(
                        f"{len(completed)}/{len(selected)} {case.id}: "
                        f"{row['status']} {detail}",
                        flush=True,
                    )

            await asyncio.gather(*(run_case(case) for case in selected))
        summary = {
            "type": "summary",
            "case_count": len(completed),
            "valid": sum(row["status"] == "valid" for row in completed),
            "errors": sum(row["status"] == "error" for row in completed),
            "relevance_matches": sum(
                row.get("relevance_match") is True for row in completed
            ),
        }
        write(summary)
        print(json.dumps(summary), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run production email interpretation for a candidate dataset; "
            "writes sensitive full inputs and outputs."
        )
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case-id", action="append", default=[])
    args = parser.parse_args()
    asyncio.run(run(args.dataset, args.output, args.case_id))


if __name__ == "__main__":
    main()
