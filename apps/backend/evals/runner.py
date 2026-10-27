"""Local dataset validation, deterministic self-check, and captured-output replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Awaitable
from pathlib import Path
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, ValidationError

from email_support.models.briefing import BriefingClaim, ClaimKind
from evals.evaluators import evaluate_claim
from evals.models import (
    CapturedCase,
    CaseResult,
    CaseResultStatus,
    CaseStatus,
    CheckName,
    ClaimEvaluation,
    ClaimIntegrity,
    ClaimSupport,
    EvaluationCase,
    EvaluationDataset,
    EvaluationRun,
    ExecutionMode,
    HumanReview,
    ReplayCapture,
    ReviewLabel,
    TaskOutcome,
    UnsupportedCheck,
)

DATASET_ROOT = Path(__file__).parent / "datasets" / "briefing-v1"
ORACLE_PATH = Path(__file__).parent / "fixtures" / "evaluator-oracle.json"
IMPLEMENTED_CHECKS = {
    CheckName.CLAIM_REFERENCE_INTEGRITY,
    CheckName.SOURCE_PROVENANCE,
    CheckName.WORKFLOW_EVENTS,
    CheckName.USEFULNESS_REVIEW,
}


class EvaluationInputError(ValueError):
    """A safe, user-facing error for invalid evaluation files or bindings."""


class OracleAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claim: BriefingClaim
    source_ids: list[str]
    review: ReviewLabel | None
    expected_integrity: ClaimIntegrity
    expected_support: ClaimSupport


class OracleFixture(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    assertions: list[OracleAssertion]


class LiveInvocation(Protocol):
    def __call__(self, case: EvaluationCase, /) -> Awaitable[CapturedCase]: ...


def load_dataset(directory: Path) -> EvaluationDataset:
    """Load the strict two-file dataset bundle and verify all internal bindings."""

    case_document = _load_json(directory / "cases.json", "dataset cases")
    source_document = _load_json(directory / "sources.json", "dataset sources")
    if not isinstance(case_document, dict) or set(case_document) - {
        "version",
        "cases",
        "golden_reviews",
    }:
        raise EvaluationInputError("Invalid dataset cases: unexpected document fields")
    if not isinstance(source_document, dict) or set(source_document) != {"sources"}:
        raise EvaluationInputError(
            "Invalid dataset sources: expected only a sources field"
        )
    combined = {**case_document, "sources": source_document["sources"]}
    try:
        return EvaluationDataset.model_validate(combined)
    except ValidationError as error:
        raise EvaluationInputError(
            f"Invalid dataset: {_validation_summary(error)}"
        ) from error


def validate_dataset(dataset: EvaluationDataset) -> dict[str, object]:
    counts = {status: 0 for status in CaseStatus}
    languages: dict[str, int] = {}
    for case in dataset.cases:
        counts[case.status] += 1
        languages[case.language.value] = languages.get(case.language.value, 0) + 1
    return {
        "dataset_version": dataset.version,
        "case_count": len(dataset.cases),
        "source_count": len(dataset.sources),
        "candidate_count": counts[CaseStatus.CANDIDATE],
        "reviewed_count": counts[CaseStatus.REVIEWED],
        "unsupported_count": counts[CaseStatus.UNSUPPORTED],
        "languages": dict(sorted(languages.items())),
        "scenarios": sorted({case.scenario.value for case in dataset.cases}),
    }


def run_self_check(oracle_path: Path = ORACLE_PATH) -> bool:
    """Execute the same evaluator used for captured claims against a small oracle."""

    document = _load_json(oracle_path, "evaluator oracle")
    try:
        fixture = OracleFixture.model_validate(document)
    except ValidationError as error:
        raise EvaluationInputError(
            f"Invalid evaluator oracle: {_validation_summary(error)}"
        ) from error
    if len(fixture.assertions) < 2:
        raise EvaluationInputError(
            "Invalid evaluator oracle: at least two assertions are required"
        )
    for assertion in fixture.assertions:
        result = evaluate_claim(
            assertion.claim, set(assertion.source_ids), assertion.review
        )
        if (
            result.integrity is not assertion.expected_integrity
            or result.support is not assertion.expected_support
        ):
            return False
    return any(
        item.expected_support is ClaimSupport.SUPPORTED for item in fixture.assertions
    ) and any(
        item.expected_support is ClaimSupport.UNSUPPORTED for item in fixture.assertions
    )


def load_capture(path: Path, dataset: EvaluationDataset) -> ReplayCapture:
    document = _load_json(path, "captured evaluation results")
    try:
        capture = ReplayCapture.model_validate(document)
    except ValidationError as error:
        raise EvaluationInputError(
            f"Invalid captured results: {_validation_summary(error)}"
        ) from error
    if capture.dataset_version != dataset.version:
        raise EvaluationInputError("Captured results use a different dataset version")
    case_ids = {case.id for case in dataset.cases}
    unknown_ids = {case.case_id for case in capture.cases} - case_ids
    if unknown_ids:
        raise EvaluationInputError("Captured results refer to an unknown dataset case")
    return capture


def build_replay_run(
    dataset: EvaluationDataset, capture: ReplayCapture
) -> EvaluationRun:
    """Evaluate captured, typed outputs without provider or product side effects."""

    captured = {item.case_id: item for item in capture.cases}
    source_hashes = {source.id: source.provenance_hash() for source in dataset.sources}
    case_hashes = {case.id: case.content_hash() for case in dataset.cases}
    preliminary: list[CaseResult] = []
    for case in dataset.cases:
        entry = captured.get(case.id)
        if entry is None:
            preliminary.append(
                CaseResult(case_id=case.id, status=CaseResultStatus.MISSING_RESULT)
            )
            continue

        allowed_sources = set(case.source_ids)
        expected_claim_ids = {fact.id for fact in case.expected_facts}
        claim_results = [
            evaluate_claim(
                claim,
                allowed_sources,
                None,
                expected_claim_ids=expected_claim_ids,
            )
            for claim in entry.claims
        ]
        present_fact_ids = {
            claim.id for claim in entry.claims if claim.kind is ClaimKind.FACT
        }
        missing_facts = expected_claim_ids - present_fact_ids
        claim_results.extend(
            ClaimEvaluation(
                claim_id=claim_id,
                integrity=ClaimIntegrity.MISSING_CLAIM,
                support=ClaimSupport.NOT_ASSESSED,
            )
            for claim_id in sorted(
                missing_facts - {item.claim_id for item in claim_results}
            )
        )
        unsupported = list(case.unsupported_checks)
        unsupported.extend(
            UnsupportedCheck(
                name=check,
                reason="No evaluation result is available for this check yet.",
            )
            for check in case.checks
            if check not in IMPLEMENTED_CHECKS
        )
        invalid_reference = any(
            result.integrity is not ClaimIntegrity.VALID for result in claim_results
        )
        forbidden_event = bool(
            set(case.forbidden_outcomes) & {event.value for event in entry.events}
        )
        if invalid_reference or forbidden_event:
            status = CaseResultStatus.FAILED
        elif case.status is CaseStatus.UNSUPPORTED or unsupported:
            status = CaseResultStatus.UNSUPPORTED_FEATURE
        else:
            status = CaseResultStatus.REVIEW_PENDING

        preliminary.append(
            CaseResult(
                case_id=case.id,
                status=status,
                baseline_eligible=(
                    case.status is CaseStatus.REVIEWED and not unsupported
                ),
                output_hash=_hash_json(entry.model_dump(mode="json")),
                claim_results=claim_results,
                unknown_claim_ids=[
                    claim.id
                    for claim in entry.claims
                    if claim.kind is ClaimKind.UNKNOWN
                ],
                elapsed_ms=entry.elapsed_ms,
                attempts=entry.attempts,
                unsupported_checks=unsupported,
            )
        )

    identity_seed = {
        "dataset_version": dataset.version,
        "dataset_hash": dataset.content_hash(),
        "case_hashes": case_hashes,
        "application_revision": capture.application_revision,
        "prompt_version": capture.prompt_version,
        "model_id": capture.model_id,
        "config_hash": capture.config_hash,
        "source_hashes": source_hashes,
        "outputs": {result.case_id: result.output_hash for result in preliminary},
    }
    run_id = str(uuid5(NAMESPACE_URL, _hash_json(identity_seed)))
    return EvaluationRun(
        id=run_id,
        dataset_version=capture.dataset_version,
        dataset_hash=dataset.content_hash(),
        case_hashes=case_hashes,
        application_revision=capture.application_revision,
        prompt_version=capture.prompt_version,
        model_id=capture.model_id,
        config_hash=capture.config_hash,
        mode=ExecutionMode.REPLAY,
        source_hashes=source_hashes,
        case_results=preliminary,
    )


def apply_human_review(
    run: EvaluationRun,
    dataset: EvaluationDataset,
    capture: ReplayCapture,
    review: HumanReview,
) -> EvaluationRun:
    """Bind manual labels to this capture, then update derived quality statuses."""

    try:
        review.validate_for(run)
    except ValueError as error:
        raise EvaluationInputError(f"Review binding failed: {error}") from error
    cases = {case.id: case for case in dataset.cases}
    captured = {item.case_id: item for item in capture.cases}
    labels = {(item.case_id, item.claim_id): item.label for item in review.claims}
    assessments = {item.case_id: item for item in review.assessments}
    results: list[CaseResult] = []

    for result in run.case_results:
        case = cases[result.case_id]
        entry = captured.get(result.case_id)
        if entry is None:
            results.append(result)
            continue
        expected_claim_ids = {fact.id for fact in case.expected_facts}
        claim_results = [
            evaluate_claim(
                claim,
                set(case.source_ids),
                labels.get((case.id, claim.id)),
                expected_claim_ids=expected_claim_ids,
            )
            for claim in entry.claims
        ]
        review_by_claim = {
            item.claim_id: item for item in review.claims if item.case_id == case.id
        }
        assessment = assessments.get(case.id)
        status = result.status
        if status not in {
            CaseResultStatus.FAILED,
            CaseResultStatus.UNSUPPORTED_FEATURE,
        }:
            factual_claims = [
                item
                for item, claim in zip(claim_results, entry.claims, strict=True)
                if claim.kind is ClaimKind.FACT
            ]
            all_facts_reviewed = all(
                (case.id, claim.claim_id) in labels for claim in factual_claims
            )
            all_claims_reviewed = all(
                (case.id, claim.id) in labels for claim in entry.claims
            )
            kind_classification_rejected = any(
                not review_by_claim[claim.id].kind_correct
                for claim in entry.claims
                if claim.id in review_by_claim
            )
            any_claim_rejected = any(
                labels.get((case.id, claim.id)) is ReviewLabel.UNSUPPORTED
                for claim in entry.claims
            )
            if (
                any(item.support is ClaimSupport.UNSUPPORTED for item in factual_claims)
                or kind_classification_rejected
                or any_claim_rejected
            ):
                status = CaseResultStatus.FAILED
            elif (
                assessment is not None
                and assessment.task_outcome is TaskOutcome.NOT_COMPLETED
            ):
                status = CaseResultStatus.FAILED
            elif (
                case.status is CaseStatus.REVIEWED
                and all_facts_reviewed
                and all_claims_reviewed
                and assessment is not None
                and assessment.task_outcome is TaskOutcome.COMPLETED
            ):
                status = CaseResultStatus.PASSED
            else:
                status = CaseResultStatus.REVIEW_PENDING

        results.append(
            result.model_copy(
                update={
                    "status": status,
                    "claim_results": claim_results,
                    "task_outcome": assessment.task_outcome if assessment else None,
                    "usefulness": assessment.usefulness if assessment else None,
                }
            )
        )

    return run.model_copy(update={"case_results": results})


def load_human_review(path: Path) -> HumanReview:
    document = _load_json(path, "human review")
    try:
        return HumanReview.model_validate(document)
    except ValidationError as error:
        raise EvaluationInputError(
            f"Invalid human review: {_validation_summary(error)}"
        ) from error


def report_for_run(
    run: EvaluationRun, review: HumanReview | None = None
) -> dict[str, object]:
    review_record: dict[str, object] | None = None
    if review is not None:
        review_record = {
            "reviewer": review.reviewer,
            "reviewed_at": review.reviewed_at.isoformat(),
            "record_hash": _hash_json(review.model_dump(mode="json")),
        }
    return {
        "schema_version": "evaluation-results-v1",
        "run_hash": run.content_hash(),
        "run": run.model_dump(mode="json"),
        "coverage": run.coverage().model_dump(mode="json"),
        "usage_totals": run.usage_totals().model_dump(mode="json"),
        "review": review_record,
    }


def validate_review_artifact(run_path: Path, review_path: Path) -> dict[str, object]:
    run_document = _load_json(run_path, "evaluation run")
    review = load_human_review(review_path)
    if not isinstance(run_document, dict) or not isinstance(
        run_document.get("run"), dict
    ):
        raise EvaluationInputError(
            "Invalid evaluation run: expected a sanitized run report"
        )
    try:
        run = EvaluationRun.model_validate(run_document["run"])
        review.validate_for(run)
    except (ValidationError, ValueError) as error:
        detail = (
            _validation_summary(error)
            if isinstance(error, ValidationError)
            else str(error)
        )
        raise EvaluationInputError(f"Review binding failed: {detail}") from error
    return {
        "run_hash": run.content_hash(),
        "review_record_hash": _hash_json(review.model_dump(mode="json")),
        "reviewed_claim_count": len(review.claims),
        "assessed_case_count": len(review.assessments),
        "status": "bound",
    }


async def run_live_evaluation(
    dataset: EvaluationDataset,
    invoke: LiveInvocation | None = None,
) -> list[CapturedCase]:
    """Invoke the injected production workflow; no default adapter is configured."""

    if invoke is None:
        raise EvaluationInputError(
            "Live evaluation is unsupported until a production adapter is available"
        )
    captured: list[CapturedCase] = []
    for case in dataset.cases:
        result = await invoke(case)
        if result.case_id != case.id:
            raise EvaluationInputError(
                "Live workflow returned a result for the wrong case"
            )
        captured.append(result)
    return captured


def _load_json(path: Path, label: str) -> object:
    try:
        with path.open(encoding="utf-8") as stream:
            return json.load(stream)
    except FileNotFoundError as error:
        raise EvaluationInputError(
            f"Invalid {label}: file not found ({path.name})"
        ) from error
    except OSError as error:
        raise EvaluationInputError(
            f"Invalid {label}: file could not be read ({path.name})"
        ) from error
    except UnicodeDecodeError as error:
        raise EvaluationInputError(
            f"Invalid {label}: file is not valid UTF-8 ({path.name})"
        ) from error
    except json.JSONDecodeError as error:
        raise EvaluationInputError(
            f"Invalid {label}: malformed JSON in {path.name} at line {error.lineno}"
        ) from error


def _hash_json(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_json(path: Path, value: object) -> None:
    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise EvaluationInputError(
            f"Output could not be written: {path.name}"
        ) from error
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(payload)
    except FileExistsError as error:
        raise EvaluationInputError(f"Output already exists: {path}") from error
    except OSError as error:
        raise EvaluationInputError(
            f"Output could not be written: {path.name}"
        ) from error


def _validation_summary(error: ValidationError) -> str:
    first = error.errors(include_url=False)[:3]
    categories = ", ".join(
        ".".join(str(part) for part in item["loc"]) for item in first
    )
    return f"contract validation failed ({categories or 'unknown field'})"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m evals")
    subparsers = parser.add_subparsers(dest="command", required=True)

    self_check = subparsers.add_parser(
        "self-check", help="run authored evaluator oracle cases"
    )
    self_check.add_argument("--oracle", type=Path, default=ORACLE_PATH)

    validate = subparsers.add_parser(
        "validate", help="validate a versioned evaluation dataset"
    )
    validate.add_argument("--dataset", type=Path, required=True)

    replay = subparsers.add_parser("replay", help="evaluate offline captured outputs")
    replay.add_argument("--dataset", type=Path, required=True)
    replay.add_argument("--results", type=Path, required=True)
    replay.add_argument("--review", type=Path)
    replay.add_argument("--output", type=Path, required=True)

    review = subparsers.add_parser(
        "review", help="validate a human review's run binding"
    )
    review.add_argument("--run", type=Path, required=True)
    review.add_argument("--review", type=Path, required=True)

    subparsers.add_parser(
        "live", help="live workflow evaluation when the production adapter exists"
    )
    return parser


def main(arguments: list[str] | None = None) -> int:
    args = _parser().parse_args(arguments)
    try:
        if args.command == "self-check":
            if not run_self_check(args.oracle):
                print("oracle: failed", file=sys.stderr)
                return 1
            print("oracle: passed")
            return 0
        if args.command == "validate":
            dataset = load_dataset(args.dataset)
            print(json.dumps(validate_dataset(dataset), indent=2, sort_keys=True))
            return 0
        if args.command == "replay":
            dataset = load_dataset(args.dataset)
            capture = load_capture(args.results, dataset)
            run = build_replay_run(dataset, capture)
            review = load_human_review(args.review) if args.review else None
            if review is not None:
                run = apply_human_review(run, dataset, capture, review)
            report = report_for_run(run, review)
            _write_json(args.output, report)
            print(json.dumps({"status": "written", "run_hash": report["run_hash"]}))
            return 0
        if args.command == "review":
            result = validate_review_artifact(args.run, args.review)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        raise EvaluationInputError(
            "Live evaluation is unsupported until a production adapter is available"
        )
    except EvaluationInputError as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0
