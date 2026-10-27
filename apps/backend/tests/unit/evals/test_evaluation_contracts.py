from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from email_support.models.briefing import BriefingClaim, ClaimKind
from evals.evaluators import evaluate_claim
from evals.models import (
    CapturedCase,
    CaseAssessment,
    CaseResult,
    CaseResultStatus,
    CaseStatus,
    ClaimReview,
    EvaluationCase,
    EvaluationDataset,
    EvaluationRun,
    EvidenceSnapshot,
    ExecutionMode,
    GoldenExpectationReview,
    HumanReview,
    IdentityStatus,
    Relevance,
    ReplayCapture,
    ReviewLabel,
    TaskOutcome,
)
from evals.runner import (
    apply_human_review,
    build_replay_run,
    load_dataset,
    run_self_check,
    validate_dataset,
)


def _source(text: str = "Public company description") -> EvidenceSnapshot:
    return EvidenceSnapshot.model_validate(
        {
            "id": "source-a",
            "url": "https://www.microsoft.com/en-us/about",
            "retrieved_at": datetime(2026, 10, 27, tzinfo=UTC),
            "published_at": None,
            "text": text,
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
        }
    )


def _case(**overrides: object) -> EvaluationCase:
    values: dict[str, object] = {
        "id": "case-a",
        "scenario": "new_company",
        "language": "en",
        "status": CaseStatus.CANDIDATE,
        "synthetic": True,
        "clock": datetime(2026, 10, 27, tzinfo=UTC),
        "timezone": "Asia/Bangkok",
        "email": {
            "from_address": "alex@example.com",
            "subject": "Preparation",
            "body": "Prepare for our discussion.",
        },
        "meeting": None,
        "source_ids": [],
        "expected_identity": "unresolved",
        "expected_facts": [],
        "forbidden_outcomes": ["invented_relationship_history"],
        "checks": ["claim_reference_integrity"],
        "unsupported_checks": [],
    }
    values.update(overrides)
    return EvaluationCase.model_validate(values)


def test_source_snapshot_hash_is_verified() -> None:
    text = "Verified source excerpt"
    with pytest.raises(ValidationError, match="hash"):
        EvidenceSnapshot.model_validate(
            {
                "id": "source-a",
                "url": "https://www.microsoft.com/en-us/about",
                "retrieved_at": datetime(2026, 10, 27, tzinfo=UTC),
                "text": text,
                "sha256": "0" * 64,
            }
        )


def test_case_rejects_unknown_fields_and_naive_clock() -> None:
    with pytest.raises(ValidationError):
        _case(unexpected="not allowed")
    with pytest.raises(ValidationError):
        _case(clock=datetime(2026, 10, 27))


def test_fixture_email_uses_non_deliverable_reserved_domain() -> None:
    _case()
    with pytest.raises(ValidationError, match="reserved example domains"):
        _case(email={"from_address": "alex@company.com", "subject": "x", "body": "y"})


def test_case_ids_and_source_ids_are_unique() -> None:
    source = _source()
    with pytest.raises(ValidationError):
        EvaluationDataset.model_validate(
            {"version": "briefing-v1", "cases": [_case(), _case()], "sources": [source]}
        )
    with pytest.raises(ValidationError):
        EvaluationDataset.model_validate(
            {
                "version": "briefing-v1",
                "cases": [_case()],
                "sources": [source, source],
            }
        )


def test_source_reference_integrity_does_not_claim_semantic_support() -> None:
    claim = BriefingClaim(
        id="fact-1",
        kind=ClaimKind.FACT,
        text="The source does not entail this claim.",
        evidence_ids=["source-a"],
    )
    result = evaluate_claim(claim, {"source-a"}, None)
    assert result.integrity == "valid"
    assert result.support == "pending_human_review"


def test_claim_contract_rejects_model_authored_support_labels() -> None:
    with pytest.raises(ValidationError, match="support"):
        BriefingClaim.model_validate(
            {
                "id": "fact-1",
                "kind": "fact",
                "text": "Claim",
                "evidence_ids": ["source-a"],
                "support": "supported",
            }
        )


def test_missing_claim_or_source_reference_fails_integrity() -> None:
    claim = BriefingClaim(
        id="fact-1",
        kind=ClaimKind.FACT,
        text="Claim",
        evidence_ids=["missing-source"],
    )
    result = evaluate_claim(claim, {"source-a"}, None)
    assert result.integrity == "missing_source"
    assert result.support == "not_assessed"


def test_review_binding_rejects_wrong_run_or_stale_source_hash() -> None:
    run = EvaluationRun(
        id=str(uuid4()),
        dataset_version="briefing-v1",
        dataset_hash="d" * 64,
        case_hashes={"case-a": "e" * 64},
        application_revision="a" * 40,
        prompt_version="prompt-v1",
        model_id="unreported",
        config_hash="b" * 64,
        mode=ExecutionMode.REPLAY,
        source_hashes={"source-a": _source().provenance_hash()},
        case_results=[
            CaseResult.model_validate(
                {
                    "case_id": "case-a",
                    "status": "review_pending",
                    "claim_results": [
                        {
                            "claim_id": "fact-1",
                            "integrity": "valid",
                            "support": "pending_human_review",
                        }
                    ],
                }
            )
        ],
    )
    review = HumanReview(
        run_id=str(uuid4()),
        dataset_version="briefing-v1",
        run_hash=run.content_hash(),
        source_hashes={"source-a": "c" * 64},
        reviewer="owner",
        reviewed_at=datetime(2026, 10, 27, tzinfo=UTC),
        claims=[
            ClaimReview(
                case_id="case-a", claim_id="fact-1", label=ReviewLabel.SUPPORTED
            )
        ],
    )
    with pytest.raises((ValidationError, ValueError)):
        review.validate_for(run)


def test_unreviewed_cases_never_become_golden_and_unsupported_is_not_pass() -> None:
    assert _case().status is CaseStatus.CANDIDATE
    case = _case(status="unsupported")
    assert case.status is CaseStatus.UNSUPPORTED


def test_aggregation_keeps_unknown_usage_and_separates_retry_totals() -> None:
    run = EvaluationRun.model_validate(
        {
            "id": str(uuid4()),
            "dataset_version": "briefing-v1",
            "application_revision": "a" * 40,
            "prompt_version": "prompt-v1",
            "model_id": "model-v1",
            "config_hash": "b" * 64,
            "mode": "replay",
            "dataset_hash": "d" * 64,
            "case_hashes": {"case-a": "e" * 64, "case-b": "f" * 64},
            "source_hashes": {},
            "case_results": [
                {
                    "case_id": "case-a",
                    "status": "review_pending",
                    "attempts": [
                        {
                            "attempt": 1,
                            "input_tokens": 11,
                            "output_tokens": 5,
                            "cost_usd": None,
                        },
                        {
                            "attempt": 2,
                            "input_tokens": None,
                            "output_tokens": None,
                            "cost_usd": None,
                        },
                    ],
                },
                {"case_id": "case-b", "status": "unsupported_feature", "attempts": []},
            ],
        }
    )
    totals = run.usage_totals()
    assert totals.attempted_input_tokens == 11
    assert totals.terminal_input_tokens is None
    assert totals.attempted_cost_usd is None
    assert run.coverage().unsupported_feature == 1
    assert run.coverage().pass_denominator == 0


def test_candidate_failure_is_excluded_from_quality_denominator() -> None:
    run = EvaluationRun.model_validate(
        {
            "id": str(uuid4()),
            "dataset_version": "briefing-v1",
            "application_revision": "a" * 40,
            "prompt_version": "prompt-v1",
            "model_id": "model-v1",
            "config_hash": "b" * 64,
            "mode": "replay",
            "dataset_hash": "d" * 64,
            "case_hashes": {"candidate": "e" * 64},
            "source_hashes": {},
            "case_results": [
                {"case_id": "candidate", "status": "failed", "baseline_eligible": False}
            ],
        }
    )
    assert run.coverage().failed == 1
    assert run.coverage().pass_denominator == 0


def test_wrong_kind_expected_fact_does_not_duplicate_result_ids() -> None:
    dataset = load_dataset(
        Path(__file__).parents[3] / "evals" / "datasets" / "briefing-v1"
    )
    case = next(item for item in dataset.cases if item.id == "stale-sources-en")
    capture = ReplayCapture(
        dataset_version=dataset.version,
        application_revision="a" * 40,
        prompt_version="prompt-v1",
        model_id="model-v1",
        config_hash="b" * 64,
        cases=[
            CapturedCase(
                case_id=case.id,
                relevance=case.expected_relevance,
                identity=case.expected_identity,
                identity_company=case.expected_company,
                identity_candidates=case.expected_identity_candidates,
                claims=[
                    BriefingClaim(
                        id="adobe-mission",
                        kind=ClaimKind.SUGGESTION,
                        text="Microsoft empowers people.",
                        evidence_ids=["adobe-about"],
                    )
                ],
            )
        ],
    )
    run = build_replay_run(dataset, capture)
    result = next(item for item in run.case_results if item.case_id == case.id)
    assert result.status.value == "failed"
    assert len({item.claim_id for item in result.claim_results}) == len(
        result.claim_results
    )


def test_replay_accepts_max_claims_plus_missing_expected_fact() -> None:
    dataset = load_dataset(
        Path(__file__).parents[3] / "evals" / "datasets" / "briefing-v1"
    )
    case = next(item for item in dataset.cases if item.id == "stale-sources-en")
    capture = ReplayCapture(
        dataset_version=dataset.version,
        application_revision="a" * 40,
        prompt_version="prompt-v1",
        model_id="model-v1",
        config_hash="b" * 64,
        cases=[
            CapturedCase(
                case_id=case.id,
                claims=[
                    BriefingClaim(
                        id=f"question-{index}",
                        kind=ClaimKind.QUESTION,
                        text="What is the source?",
                        evidence_ids=[],
                    )
                    for index in range(500)
                ],
            )
        ],
    )
    run = build_replay_run(dataset, capture)
    result = next(item for item in run.case_results if item.case_id == case.id)
    assert len(result.claim_results) == 501


def test_human_can_reject_claim_misclassified_as_nonfactual() -> None:
    dataset = load_dataset(
        Path(__file__).parents[3] / "evals" / "datasets" / "briefing-v1"
    )
    case = next(item for item in dataset.cases if item.id == "injection-en")
    capture = ReplayCapture(
        dataset_version=dataset.version,
        application_revision="a" * 40,
        prompt_version="prompt-v1",
        model_id="model-v1",
        config_hash="b" * 64,
        cases=[
            CapturedCase(
                case_id=case.id,
                relevance=case.expected_relevance,
                identity=case.expected_identity,
                identity_company=case.expected_company,
                identity_candidates=case.expected_identity_candidates,
                claims=[
                    BriefingClaim(
                        id="misclassified",
                        kind=ClaimKind.SUGGESTION,
                        text="Microsoft has secretly approved our proposal.",
                        evidence_ids=[],
                    )
                ],
            )
        ],
    )
    run = build_replay_run(dataset, capture)
    review = HumanReview(
        run_id=run.id,
        dataset_version=run.dataset_version,
        run_hash=run.content_hash(),
        source_hashes=run.source_hashes,
        reviewer="owner",
        reviewed_at=datetime(2026, 10, 27, tzinfo=UTC),
        claims=[
            ClaimReview(
                case_id=case.id,
                claim_id="misclassified",
                label=ReviewLabel.UNSUPPORTED,
                kind_correct=False,
            )
        ],
    )
    result = apply_human_review(run, dataset, capture, review)
    assert (
        next(
            item for item in result.case_results if item.case_id == case.id
        ).status.value
        == "failed"
    )


def test_missing_identity_capture_stays_unsupported() -> None:
    dataset = load_dataset(
        Path(__file__).parents[3] / "evals" / "datasets" / "briefing-v1"
    )
    case = next(item for item in dataset.cases if item.id == "ambiguous-identity-en")
    capture = ReplayCapture(
        dataset_version=dataset.version,
        application_revision="a" * 40,
        prompt_version="prompt-v1",
        model_id="model-v1",
        config_hash="b" * 64,
        cases=[CapturedCase(case_id=case.id)],
    )
    result = next(
        item
        for item in build_replay_run(dataset, capture).case_results
        if item.case_id == case.id
    )
    assert result.status.value == "unsupported_feature"
    assert any(
        item.name.value == "identity_resolution" for item in result.unsupported_checks
    )


@pytest.mark.parametrize(
    ("observed", "expected_status", "expected_correct"),
    [
        (Relevance.RELEVANT, CaseResultStatus.REVIEW_PENDING, True),
        (Relevance.IRRELEVANT, CaseResultStatus.FAILED, False),
        (None, CaseResultStatus.UNSUPPORTED_FEATURE, None),
    ],
)
def test_relevance_can_be_evaluated_without_identity(
    observed: Relevance | None,
    expected_status: CaseResultStatus,
    expected_correct: bool | None,
) -> None:
    case = _case(checks=["relevance"], expected_relevance="relevant")
    dataset = EvaluationDataset(version="interpretation-v2", cases=[case], sources=[])
    capture = ReplayCapture(
        dataset_version=dataset.version,
        application_revision="a" * 40,
        prompt_version="prompt-v1",
        model_id="model-v1",
        config_hash="b" * 64,
        cases=[CapturedCase(case_id=case.id, relevance=observed)],
    )
    result = build_replay_run(dataset, capture).case_results[0]
    assert result.status is expected_status
    assert result.relevance_correct is expected_correct
    assert result.identity_correct is None


def test_relevance_check_requires_a_known_expectation() -> None:
    with pytest.raises(ValidationError):
        _case(checks=["relevance"], expected_relevance="unknown")


def test_interpretation_v2_covers_paired_languages_and_declares_limits() -> None:
    root = Path(__file__).parents[3] / "evals" / "datasets" / "interpretation-v2"
    dataset = load_dataset(root)
    assert len(dataset.cases) == 56
    assert all(case.status is CaseStatus.CANDIDATE for case in dataset.cases)
    assert all(
        [item.value for item in case.checks] == ["relevance"] for case in dataset.cases
    )
    assert all(
        any(
            check.name.value == "identity_resolution"
            for check in case.unsupported_checks
        )
        for case in dataset.cases
    )
    by_id = {case.id: case for case in dataset.cases}
    for case in dataset.cases:
        counterpart = case.id[:-3] + ("-vi" if case.language.value == "en" else "-en")
        assert counterpart in by_id
        assert by_id[counterpart].expected_relevance is case.expected_relevance
    report = validate_dataset(dataset)
    assert report["languages"] == {"en": 28, "vi": 28}
    assert report["relevance_expectations"] == {
        "irrelevant": 14,
        "relevant": 32,
        "uncertain": 10,
    }
    assert report["unsupported_checks"] == {
        "identity_resolution": 56,
        "workflow_events": 6,
    }
    case = dataset.cases[0]
    capture = ReplayCapture(
        dataset_version=dataset.version,
        application_revision="a" * 40,
        prompt_version="prompt-v1",
        model_id="model-v1",
        config_hash="b" * 64,
        cases=[CapturedCase(case_id=case.id, relevance=case.expected_relevance)],
    )
    result = next(
        r
        for r in build_replay_run(dataset, capture).case_results
        if r.case_id == case.id
    )
    assert result.relevance_correct is True
    assert result.identity_correct is None
    assert result.status is CaseResultStatus.UNSUPPORTED_FEATURE


def test_customer_examples_preserve_input_and_report_missing_workflow() -> None:
    root = Path(__file__).parents[3] / "evals" / "datasets" / "customer-examples-v1"
    dataset = load_dataset(root)
    assert len(dataset.cases) == 12
    assert validate_dataset(dataset)["languages"] == {"en": 6, "vi": 6}
    assert not dataset.sources
    assert all(
        case.synthetic and case.status is CaseStatus.CANDIDATE for case in dataset.cases
    )
    for case in dataset.cases:
        assert case.meeting is None
        assert "https://" in case.email.body
        assert {item.name.value for item in case.unsupported_checks} >= {
            "identity_resolution",
            "source_provenance",
            "claim_reference_integrity",
            "usefulness_review",
        }
    viettel = next(case for case in dataset.cases if case.id == "viettel-solutions-vi")
    assert any(
        item.name.value == "attachment_provenance"
        for item in viettel.unsupported_checks
    )


def test_dataset_loads_bilingual_candidate_scenarios_and_verified_sources() -> None:
    root = Path(__file__).parents[3] / "evals" / "datasets" / "briefing-v1"
    dataset = load_dataset(root)
    assert len(dataset.cases) == 24
    assert len(dataset.sources) >= 1
    assert all(case.synthetic for case in dataset.cases)
    assert all(source.published_at is None for source in dataset.sources)
    assert {case.scenario for case in dataset.cases} == {
        "new_company",
        "returning_company",
        "irrelevant_email",
        "uncertain_relevance",
        "ambiguous_identity",
        "incorrect_prior_association",
        "missing_meeting",
        "stale_sources",
        "injection",
        "changed_approval",
        "uncertain_delivery",
        "attachment_export",
    }
    assert {case.language.value for case in dataset.cases} == {"en", "vi"}
    assert all(
        {case.language.value for case in dataset.cases if case.scenario is scenario}
        == {"en", "vi"}
        for scenario in {case.scenario for case in dataset.cases}
    )
    assert all(case.expected_relevance is not None for case in dataset.cases)
    assert all(
        "identity_resolution" in {check.value for check in case.checks}
        for case in dataset.cases
    )
    assert all(
        case.forbidden_outcomes and case.checks or case.unsupported_checks
        for case in dataset.cases
    )


def test_identity_mismatch_fails_independently_of_briefing_claims() -> None:
    dataset = load_dataset(
        Path(__file__).parents[3] / "evals" / "datasets" / "briefing-v1"
    )
    case = next(item for item in dataset.cases if item.id == "irrelevant-email-en")
    capture = ReplayCapture(
        dataset_version=dataset.version,
        application_revision="a" * 40,
        prompt_version="prompt-v1",
        model_id="model-v1",
        config_hash="b" * 64,
        cases=[
            CapturedCase(
                case_id=case.id,
                relevance=Relevance.IRRELEVANT,
                identity=IdentityStatus.RESOLVED,
            )
        ],
    )
    result = next(
        item
        for item in build_replay_run(dataset, capture).case_results
        if item.case_id == case.id
    )
    assert result.relevance_correct is True
    assert result.identity_correct is False
    assert result.status is CaseResultStatus.FAILED


def test_reviewed_case_requires_bound_golden_record_and_human_run_review() -> None:
    source = _source()
    case = _case(
        source_ids=[source.id],
        expected_facts=[
            {"id": "fact-1", "statement": "Expected fact.", "evidence_ids": [source.id]}
        ],
    )
    candidate_dataset = EvaluationDataset(
        version="briefing-v1", cases=[case], sources=[source]
    )
    reviewed_case = case.model_copy(update={"status": CaseStatus.REVIEWED})

    golden = GoldenExpectationReview(
        case_id=case.id,
        dataset_version="briefing-v1",
        dataset_hash=candidate_dataset.content_hash(),
        case_hash=case.content_hash(),
        source_hashes={source.id: source.provenance_hash()},
        reviewer="owner",
        reviewed_at=datetime(2026, 10, 27, tzinfo=UTC),
    )
    dataset = EvaluationDataset(
        version="briefing-v1",
        cases=[reviewed_case],
        sources=[source],
        golden_reviews=[golden],
    )
    assert dataset.content_hash() == candidate_dataset.content_hash()
    changed_case = case.model_copy(update={"expected_relevance": Relevance.IRRELEVANT})
    changed_dataset = EvaluationDataset(
        version="briefing-v1", cases=[changed_case], sources=[source]
    )
    assert changed_dataset.content_hash() != candidate_dataset.content_hash()
    changed_source = _source("A different verified company description")
    assert changed_source.provenance_hash() != source.provenance_hash()
    capture = ReplayCapture(
        dataset_version=dataset.version,
        application_revision="a" * 40,
        prompt_version="prompt-v1",
        model_id="model-v1",
        config_hash="b" * 64,
        cases=[
            CapturedCase(
                case_id=case.id,
                claims=[
                    BriefingClaim(
                        id="fact-1",
                        kind=ClaimKind.FACT,
                        text="Captured claim.",
                        evidence_ids=[source.id],
                    )
                ],
            )
        ],
    )
    run = build_replay_run(dataset, capture)
    review = HumanReview(
        run_id=run.id,
        dataset_version=run.dataset_version,
        run_hash=run.content_hash(),
        source_hashes=run.source_hashes,
        reviewer="owner",
        reviewed_at=datetime(2026, 10, 27, tzinfo=UTC),
        claims=[
            ClaimReview(case_id=case.id, claim_id="fact-1", label=ReviewLabel.SUPPORTED)
        ],
        assessments=[
            CaseAssessment(
                case_id=case.id,
                task_outcome=TaskOutcome.COMPLETED,
                usefulness=4,
            )
        ],
    )
    reviewed_run = apply_human_review(run, dataset, capture, review)
    assert reviewed_run.case_results[0].status.value == "passed"
    assert reviewed_run.case_results[0].claim_results[0].support.value == "supported"
    assert reviewed_run.case_results[0].usefulness == 4
    assert reviewed_run.content_hash() == run.content_hash()
    changed_run = build_replay_run(changed_dataset, capture)
    assert changed_run.content_hash() != run.content_hash()
    with pytest.raises(ValueError, match="not bound"):
        review.validate_for(changed_run)


def test_oracle_fixture_is_executable_against_production_evaluator() -> None:
    assert run_self_check() is True
