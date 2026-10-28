"""Evidence-bound review aids; semantic judgments remain human decisions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from email_support.models.email_interpretation import (
    EmailInterpretation,
    FollowUpIntent,
    InputOriginKind,
    MeetingState,
    NormalizedInputCreate,
)
from evals.models import CheckName, EvaluationDataset, Relevance
from evals.runner import EvaluationInputError, load_dataset


class CaseBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    case_id: str
    case_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class PairRubric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    expected_company_mentions: list[str]
    expected_need: str = Field(min_length=1)
    unknowns_and_forbidden: str = Field(min_length=1)
    cases: dict[str, CaseBinding]
    relevance_review: str | None = None
    expected_follow_up: FollowUpIntent | None = None
    follow_up_guidance: str | None = None


class Rubric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    dataset_version: str
    dataset_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    pairs: list[PairRubric]


def load_rubric(path: Path, dataset: EvaluationDataset) -> Rubric:
    try:
        rubric = Rubric.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise EvaluationInputError("Invalid interpretation rubric") from exc
    if (
        rubric.dataset_version != dataset.version
        or rubric.dataset_hash != dataset.content_hash()
    ):
        raise EvaluationInputError("Rubric does not bind to this dataset")
    cases = {case.id: case for case in dataset.cases}
    seen: set[str] = set()
    pair_ids: set[str] = set()
    for pair in rubric.pairs:
        if pair.id in pair_ids or set(pair.cases) != {"en", "vi"}:
            raise EvaluationInputError("Rubric pairs must be unique and bilingual")
        pair_ids.add(pair.id)
        for language, binding in pair.cases.items():
            case = cases.get(binding.case_id)
            if (
                case is None
                or binding.case_id in seen
                or binding.case_id != f"{pair.id}-{language}"
                or case.language.value != language
                or case.content_hash() != binding.case_hash
            ):
                raise EvaluationInputError("Rubric case binding is invalid")
            seen.add(binding.case_id)
    if seen != set(cases):
        raise EvaluationInputError("Rubric must cover every dataset case")
    return rubric


def build_review(
    dataset: EvaluationDataset,
    rubric: Rubric,
    records: list[dict[str, Any]],
    *,
    include_content: bool = False,
) -> dict[str, Any]:
    cases = {case.id: case for case in dataset.cases}
    captured: dict[str, dict[str, Any]] = {}
    for record in records:
        case_id = record.get("case_id")
        if case_id not in cases or case_id in captured:
            raise EvaluationInputError("Capture has an unknown or duplicate case")
        if record.get("status") == "valid":
            try:
                normalized = NormalizedInputCreate.model_validate(record.get("input"))
                interpretation = EmailInterpretation.model_validate(
                    record.get("output")
                )
                case = cases[case_id]
                payload = normalized.payload
                if (
                    normalized.origin_kind is not InputOriginKind.EVALUATION
                    or normalized.origin_key != case.id
                    or payload.sender_email != case.email.from_address
                    or payload.sender_display_name is not None
                    or payload.subject != case.email.subject
                    or payload.body != case.email.body
                    or payload.received_at != case.clock
                    or (payload.meeting is None) != (case.meeting is None)
                    or payload.meeting_state
                    is not (
                        MeetingState.SCHEDULED if case.meeting else MeetingState.ABSENT
                    )
                ):
                    raise ValueError("Captured input differs from dataset")
                if payload.meeting is not None and case.meeting is not None:
                    meeting = payload.meeting
                    if (
                        meeting.title != case.meeting.title
                        or meeting.description != case.meeting.description
                        or meeting.time.kind != "timed"
                        or meeting.time.starts_at != case.meeting.starts_at
                        or meeting.time.ends_at != case.meeting.ends_at
                        or meeting.attendees != case.meeting.attendees
                    ):
                        raise ValueError("Captured meeting differs from dataset")
                interpretation.validate_evidence_against(payload)
            except (ValidationError, ValueError, KeyError, TypeError):
                raise EvaluationInputError(
                    "Invalid or unbound captured result"
                ) from None
        captured[case_id] = record
    case_reports: list[dict[str, Any]] = []
    pair_reports: list[dict[str, Any]] = []
    for pair in rubric.pairs:
        outputs: dict[str, dict[str, Any] | None] = {}
        for language, binding in pair.cases.items():
            case_record = captured.get(binding.case_id)
            output: dict[str, Any] | None = (
                case_record.get("output")
                if case_record and case_record.get("status") == "valid"
                else None
            )
            if not isinstance(output, dict):
                output = None
            outputs[language] = output
            companies = (
                [x.get("name", "") for x in output.get("company_candidates", [])]
                if output
                else []
            )
            expected = pair.expected_company_mentions
            case = cases[binding.case_id]
            expected_relevance = case.expected_relevance.value
            observed = output.get("relevance") if output else None
            if (
                CheckName.RELEVANCE not in case.checks
                or case.expected_relevance is Relevance.UNKNOWN
            ):
                check = {
                    "status": "not_evaluated",
                    "reason": "Relevance is not applicable or has no expected label.",
                }
            elif output is None:
                check = {
                    "status": "not_evaluated",
                    "reason": "No valid captured output.",
                }
            elif observed == expected_relevance:
                check = {
                    "status": "pass",
                    "reason": (
                        f"Observed '{observed}' matches "
                        f"expected '{expected_relevance}'."
                    ),
                }
            else:
                check = {
                    "status": "fail",
                    "reason": (
                        f"Expected '{expected_relevance}'; observed '{observed}'."
                    ),
                }
            follow_up_observed = output.get("follow_up_intent") if output else None
            if pair.expected_follow_up is None:
                follow_up_check = {
                    "status": "not_evaluated",
                    "reason": "No follow-up expectation.",
                }
            elif follow_up_observed is None:
                follow_up_check = {
                    "status": "not_evaluated",
                    "reason": "No valid follow-up output.",
                }
            else:
                expected_follow_up = pair.expected_follow_up.value
                follow_up_check = {
                    "status": "pass"
                    if follow_up_observed == expected_follow_up
                    else "fail",
                    "reason": (
                        f"Expected '{expected_follow_up}'; "
                        f"observed '{follow_up_observed}'."
                    ),
                }
            content = {}
            if include_content:
                content = {
                    "input": {
                        "email": case.email.model_dump(mode="json"),
                        "meeting": case.meeting.model_dump(mode="json")
                        if case.meeting
                        else None,
                    },
                    "normalized_input": case_record.get("input")
                    if case_record
                    else None,
                    "output": output,
                    "raw_model_responses": case_record.get("model_responses")
                    if case_record
                    else None,
                    "raw_model_response": case_record.get("model_response")
                    if case_record
                    else None,
                }
            case_reports.append(
                {
                    **content,
                    "relevance_check": check,
                    "follow_up_check": follow_up_check,
                    "expected_follow_up": pair.expected_follow_up.value
                    if pair.expected_follow_up
                    else None,
                    "follow_up_guidance": pair.follow_up_guidance,
                    "unsupported_checks": [
                        item.model_dump(mode="json") for item in case.unsupported_checks
                    ],
                    "case_id": binding.case_id,
                    "status": case_record.get("status") if case_record else "missing",
                    "expected_relevance": cases[
                        binding.case_id
                    ].expected_relevance.value,
                    "observed_relevance": output.get("relevance") if output else None,
                    "expected_company_mentions": expected,
                    "missing_company_mentions": [
                        name
                        for name in expected
                        if not any(
                            name.casefold() == str(found).casefold()
                            for found in companies
                        )
                    ]
                    if output
                    else None,
                    "needs_count": len(output.get("stated_needs", []))
                    if output
                    else None,
                    "unknowns_count": len(output.get("unknowns", []))
                    if output
                    else None,
                    "expected_need": pair.expected_need,
                    "unknowns_and_forbidden": pair.unknowns_and_forbidden,
                    "relevance_review": pair.relevance_review,
                    "review_status": "pending_human_review",
                }
            )
        en, vi = outputs.get("en"), outputs.get("vi")
        pair_reports.append(
            {
                "pair_id": pair.id,
                "relevance_equal": en.get("relevance") == vi.get("relevance")
                if en and vi
                else None,
                "needs_presence_equal": bool(en.get("stated_needs"))
                == bool(vi.get("stated_needs"))
                if en and vi
                else None,
                "unknowns_presence_equal": bool(en.get("unknowns"))
                == bool(vi.get("unknowns"))
                if en and vi
                else None,
                "company_names_equal": {
                    item["name"].casefold() for item in en.get("company_candidates", [])
                }
                == {
                    item["name"].casefold() for item in vi.get("company_candidates", [])
                }
                if en and vi
                else None,
                "review_status": "pending_human_review",
            }
        )
    return {
        "dataset_version": dataset.version,
        "dataset_hash": dataset.content_hash(),
        "cases": case_reports,
        "pairs": pair_reports,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument(
        "--include-content",
        action="store_true",
        help="Include private input and output in the report",
    )
    args = parser.parse_args()
    try:
        dataset = load_dataset(args.dataset)
        rubric = load_rubric(args.dataset / "interpretation-rubric.json", dataset)
        rows = [
            json.loads(line)
            for line in args.log.read_text(encoding="utf-8").splitlines()
        ]
        runs = [row for row in rows if row.get("type") == "run"]
        if len(runs) != 1 or runs[0].get("dataset_hash") != dataset.content_hash():
            raise EvaluationInputError("Capture does not bind to this dataset")
        report = build_review(
            dataset,
            rubric,
            [row for row in rows if row.get("type") == "case"],
            include_content=args.include_content,
        )
        report["run"] = {
            key: runs[0].get(key)
            for key in (
                "model_id",
                "prompt_version",
                "application_revision",
                "implementation_sha256",
            )
        }
    except (OSError, ValueError, TypeError, AttributeError):
        print("Invalid interpretation review input", file=sys.stderr)
        raise SystemExit(1) from None
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
