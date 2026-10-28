"""Strict dataset, reviewer and result contracts for offline quality evaluation."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)

from email_support.models.briefing import BriefingClaim

MAX_CAPTURED_CLAIMS = 500
MAX_EXPECTED_FACTS = 100


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Scenario(StrEnum):
    NEW_COMPANY = "new_company"
    RETURNING_COMPANY = "returning_company"
    IRRELEVANT_EMAIL = "irrelevant_email"
    UNCERTAIN_RELEVANCE = "uncertain_relevance"
    AMBIGUOUS_IDENTITY = "ambiguous_identity"
    INCORRECT_PRIOR_ASSOCIATION = "incorrect_prior_association"
    MISSING_MEETING = "missing_meeting"
    STALE_SOURCES = "stale_sources"
    INJECTION = "injection"
    CHANGED_APPROVAL = "changed_approval"
    UNCERTAIN_DELIVERY = "uncertain_delivery"
    ATTACHMENT_EXPORT = "attachment_export"


class Language(StrEnum):
    ENGLISH = "en"
    VIETNAMESE = "vi"


class CaseStatus(StrEnum):
    CANDIDATE = "candidate"
    REVIEWED = "reviewed"
    UNSUPPORTED = "unsupported"


class IdentityStatus(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"
    NONE = "none"


class Relevance(StrEnum):
    RELEVANT = "relevant"
    IRRELEVANT = "irrelevant"
    UNKNOWN = "unknown"
    UNCERTAIN = "uncertain"


class CheckName(StrEnum):
    RELEVANCE = "relevance"
    CLAIM_REFERENCE_INTEGRITY = "claim_reference_integrity"
    SOURCE_PROVENANCE = "source_provenance"
    IDENTITY_RESOLUTION = "identity_resolution"
    WORKFLOW_EVENTS = "workflow_events"
    APPROVAL_BINDING = "approval_binding"
    DELIVERY_RECONCILIATION = "delivery_reconciliation"
    ATTACHMENT_PROVENANCE = "attachment_provenance"
    USEFULNESS_REVIEW = "usefulness_review"


class ExpectedFact(Contract):
    id: str = Field(min_length=1, max_length=100)
    statement: str = Field(min_length=1, max_length=1000)
    evidence_ids: list[str] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def evidence_ids_are_unique(self) -> Self:
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("expected fact evidence IDs must be unique")
        return self


class EmailInput(Contract):
    from_address: EmailStr | None
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(max_length=20_000)

    @field_validator("from_address")
    @classmethod
    def use_reserved_synthetic_domain(cls, value: EmailStr | None) -> EmailStr | None:
        if value is None:
            return None
        domain = str(value).rsplit("@", 1)[-1].lower()
        if domain not in {"example.com", "example.net", "example.org"}:
            raise ValueError(
                "synthetic email addresses must use reserved example domains"
            )
        return value


class MeetingInput(Contract):
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=500)
    starts_at: datetime
    ends_at: datetime | None = None
    attendees: list[EmailStr] = Field(max_length=50)
    description: str = Field(default="", max_length=10_000)

    @field_validator("starts_at", "ends_at")
    @classmethod
    def meeting_times_are_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("meeting times must be timezone-aware")
        return value

    @field_validator("attendees")
    @classmethod
    def attendees_are_synthetic(cls, values: list[EmailStr]) -> list[EmailStr]:
        allowed = {"example.com", "example.net", "example.org"}
        for address in values:
            if str(address).rsplit("@", 1)[-1].lower() not in allowed:
                raise ValueError(
                    "synthetic email addresses must use reserved example domains"
                )
        return values

    @model_validator(mode="after")
    def meeting_end_follows_start(self) -> Self:
        if self.ends_at is not None and self.ends_at <= self.starts_at:
            raise ValueError("meeting end must follow its start")
        return self


class EvidenceSnapshot(Contract):
    id: str = Field(min_length=1, max_length=100)
    url: AnyHttpUrl
    retrieved_at: datetime
    published_at: datetime | None = None
    text: str = Field(min_length=20, max_length=5000)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("retrieved_at", "published_at")
    @classmethod
    def source_times_are_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("source timestamps must be timezone-aware")
        return value

    @field_validator("url")
    @classmethod
    def require_public_https_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        parsed = urlsplit(str(value))
        if parsed.scheme != "https" or parsed.username or parsed.password:
            raise ValueError(
                "source URL must be public HTTPS without embedded credentials"
            )
        host = (parsed.hostname or "").lower().rstrip(".")
        if (
            not host
            or host == "localhost"
            or host.endswith((".localhost", ".local", ".test"))
        ):
            raise ValueError("source URL must use a public hostname")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            if not address.is_global:
                raise ValueError("source URL must use a public IP address")
        return value

    @model_validator(mode="after")
    def snapshot_hash_matches_text(self) -> Self:
        expected = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
        if self.sha256 != expected:
            raise ValueError("source snapshot hash does not match excerpt text")
        return self

    def provenance_hash(self) -> str:
        payload = {
            "id": self.id,
            "url": str(self.url),
            "retrieved_at": self.retrieved_at.isoformat(),
            "published_at": self.published_at.isoformat()
            if self.published_at
            else None,
            "sha256": self.sha256,
        }
        return hashlib.sha256(_canonical_json(payload)).hexdigest()


class UnsupportedCheck(Contract):
    name: CheckName
    reason: str = Field(min_length=1, max_length=300)


class EvaluationCase(Contract):
    id: str = Field(min_length=1, max_length=100)
    scenario: Scenario
    language: Language
    status: CaseStatus = CaseStatus.CANDIDATE
    synthetic: bool
    clock: datetime
    timezone: str = Field(min_length=1, max_length=100)
    email: EmailInput
    meeting: MeetingInput | None
    expected_relevance: Relevance = Relevance.UNKNOWN
    expected_identity: IdentityStatus
    expected_company: str | None = Field(default=None, min_length=1, max_length=200)
    expected_identity_candidates: list[str] = Field(default_factory=list, max_length=10)
    source_ids: list[str] = Field(max_length=20)
    expected_facts: list[ExpectedFact] = Field(max_length=MAX_EXPECTED_FACTS)
    forbidden_outcomes: list[str] = Field(max_length=50)
    checks: list[CheckName] = Field(max_length=len(CheckName))
    unsupported_checks: list[UnsupportedCheck] = Field(max_length=len(CheckName))

    @field_validator("clock")
    @classmethod
    def scenario_clock_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("scenario clock must be timezone-aware")
        return value

    @field_validator("timezone")
    @classmethod
    def timezone_is_known(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("unknown IANA timezone") from error
        return value

    @model_validator(mode="after")
    def case_ids_are_unique(self) -> Self:
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("case source IDs must be unique")
        fact_ids = [fact.id for fact in self.expected_facts]
        if len(set(fact_ids)) != len(fact_ids):
            raise ValueError("expected fact IDs must be unique")
        expected_sources = {
            source_id for fact in self.expected_facts for source_id in fact.evidence_ids
        }
        if not expected_sources.issubset(self.source_ids):
            raise ValueError(
                "expected fact evidence must belong to the case source set"
            )
        if len(set(self.expected_identity_candidates)) != len(
            self.expected_identity_candidates
        ):
            raise ValueError("identity candidate names must be unique")
        if (self.expected_identity is IdentityStatus.RESOLVED) != (
            self.expected_company is not None
        ):
            raise ValueError("a resolved identity must name one expected company")
        if self.expected_identity is IdentityStatus.AMBIGUOUS:
            if (
                len(self.expected_identity_candidates) < 2
                or self.expected_company is not None
            ):
                raise ValueError(
                    "ambiguous identity requires multiple candidates and no selection"
                )
        elif self.expected_identity_candidates:
            raise ValueError(
                "identity candidates are only expected for ambiguous cases"
            )
        check_names = [*self.checks, *(item.name for item in self.unsupported_checks)]
        if len(set(check_names)) != len(check_names):
            raise ValueError("a check can be applicable or unsupported, not both")
        if (
            CheckName.RELEVANCE in self.checks
            and self.expected_relevance is Relevance.UNKNOWN
        ):
            raise ValueError("relevance checks require a known expectation")
        return self

    def content_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"status"})
        return hashlib.sha256(_canonical_json(payload)).hexdigest()


class GoldenExpectationReview(Contract):
    case_id: str = Field(min_length=1, max_length=100)
    dataset_version: str = Field(min_length=1, max_length=50)
    dataset_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_hashes: dict[str, str]
    reviewer: str = Field(min_length=1, max_length=100)
    reviewed_at: datetime

    @field_validator("reviewed_at")
    @classmethod
    def review_time_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("review timestamp must be timezone-aware")
        return value

    @field_validator("source_hashes")
    @classmethod
    def source_hashes_are_valid(cls, value: dict[str, str]) -> dict[str, str]:
        for digest in value.values():
            if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise ValueError("source hashes must be lowercase SHA-256 values")
        return value


class EvaluationDataset(Contract):
    version: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,49}$")
    cases: list[EvaluationCase] = Field(min_length=1, max_length=1000)
    sources: list[EvidenceSnapshot] = Field(max_length=1000)
    golden_reviews: list[GoldenExpectationReview] = Field(
        default_factory=list, max_length=1000
    )

    @model_validator(mode="after")
    def dataset_references_are_bound(self) -> Self:
        cases = {case.id: case for case in self.cases}
        if len(cases) != len(self.cases):
            raise ValueError("case IDs must be unique")
        sources = {source.id: source for source in self.sources}
        if len(sources) != len(self.sources):
            raise ValueError("source IDs must be unique")
        reviews = {review.case_id: review for review in self.golden_reviews}
        if len(reviews) != len(self.golden_reviews):
            raise ValueError("golden review case IDs must be unique")
        for case in self.cases:
            unknown_sources = set(case.source_ids) - sources.keys()
            fact_sources = {
                source for fact in case.expected_facts for source in fact.evidence_ids
            }
            unknown_facts = fact_sources - sources.keys()
            if unknown_sources or unknown_facts:
                raise ValueError(f"case {case.id} refers to an unknown source")
            review = reviews.get(case.id)
            if case.status is CaseStatus.REVIEWED:
                if review is None:
                    raise ValueError(
                        f"reviewed case {case.id} requires an owner review record"
                    )
                expected_hashes = {
                    source_id: sources[source_id].provenance_hash()
                    for source_id in case.source_ids
                }
                if (
                    review.dataset_version != self.version
                    or review.dataset_hash != self.content_hash()
                    or review.case_hash != case.content_hash()
                    or review.source_hashes != expected_hashes
                ):
                    raise ValueError(f"golden review for case {case.id} is stale")
            elif review is not None:
                raise ValueError(
                    f"case {case.id} cannot use a golden review before review status"
                )
        if set(reviews) - cases.keys():
            raise ValueError("golden review refers to an unknown case")
        return self

    def content_hash(self) -> str:
        payload = {
            "version": self.version,
            "cases": {
                case.id: case.content_hash()
                for case in sorted(self.cases, key=lambda item: item.id)
            },
            "sources": {
                source.id: source.provenance_hash()
                for source in sorted(self.sources, key=lambda item: item.id)
            },
        }
        return hashlib.sha256(_canonical_json(payload)).hexdigest()


class ExecutionMode(StrEnum):
    REPLAY = "replay"
    LIVE = "live"


class ReviewLabel(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"


class ClaimIntegrity(StrEnum):
    VALID = "valid"
    MISSING_CLAIM = "missing_claim"
    MISSING_SOURCE = "missing_source"


class ClaimSupport(StrEnum):
    PENDING_HUMAN_REVIEW = "pending_human_review"
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    NOT_ASSESSED = "not_assessed"
    NOT_APPLICABLE = "not_applicable"


class CaseResultStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    REVIEW_PENDING = "review_pending"
    UNSUPPORTED_FEATURE = "unsupported_feature"
    MISSING_RESULT = "missing_result"


class TaskOutcome(StrEnum):
    COMPLETED = "completed"
    NOT_COMPLETED = "not_completed"
    UNKNOWN = "unknown"


class ObservedEvent(StrEnum):
    PRIVATE_INPUT_IN_RESEARCH_QUERY = "private_input_in_research_query"
    APPROVAL_RECORDED = "approval_recorded"
    STALE_APPROVAL_USED = "stale_approval_used"
    EMAIL_SENT = "email_sent"
    KNOWLEDGE_PROMOTED = "knowledge_promoted"
    DUPLICATE_DELIVERY = "duplicate_delivery"
    INVENTED_RELATIONSHIP_HISTORY = "invented_relationship_history"
    INVENTED_MEETING = "invented_meeting"
    UNNECESSARY_RESEARCH = "unnecessary_research"
    UNVERIFIED_CLAIM_PRESENTED_AS_FACT = "unverified_claim_presented_as_fact"
    ATTACHMENT_FACT_WITHOUT_PROVENANCE = "attachment_fact_without_provenance"


class ClaimEvaluation(Contract):
    claim_id: str
    integrity: ClaimIntegrity
    support: ClaimSupport


class AttemptUsage(Contract):
    attempt: StrictInt = Field(ge=1)
    elapsed_ms: StrictInt | None = Field(default=None, ge=0)
    input_tokens: StrictInt | None = Field(default=None, ge=0)
    output_tokens: StrictInt | None = Field(default=None, ge=0)
    cost_usd: Decimal | None = Field(default=None, ge=0)


class CapturedCase(Contract):
    case_id: str = Field(min_length=1, max_length=100)
    claims: list[BriefingClaim] = Field(
        default_factory=list, max_length=MAX_CAPTURED_CLAIMS
    )
    events: list[ObservedEvent] = Field(default_factory=list, max_length=100)
    elapsed_ms: StrictInt | None = Field(default=None, ge=0)
    attempts: list[AttemptUsage] = Field(default_factory=list, max_length=100)
    relevance: Relevance | None = None
    identity: IdentityStatus | None = None
    identity_company: str | None = Field(default=None, max_length=200)
    identity_candidates: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def attempts_are_sequential(self) -> Self:
        expected = list(range(1, len(self.attempts) + 1))
        if [item.attempt for item in self.attempts] != expected:
            raise ValueError("attempt numbers must be sequential from one")
        claim_ids = [claim.id for claim in self.claims]
        if len(set(claim_ids)) != len(claim_ids):
            raise ValueError("captured claim IDs must be unique per case")
        if len(set(self.events)) != len(self.events):
            raise ValueError("observed events must be unique per case")
        return self


class ReplayCapture(Contract):
    dataset_version: str = Field(min_length=1, max_length=50)
    application_revision: str = Field(min_length=1, max_length=100)
    prompt_version: str = Field(min_length=1, max_length=100)
    model_id: str = Field(min_length=1, max_length=200)
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    cases: list[CapturedCase] = Field(max_length=1000)

    @model_validator(mode="after")
    def case_ids_are_unique(self) -> Self:
        ids = [case.case_id for case in self.cases]
        if len(set(ids)) != len(ids):
            raise ValueError("captured case IDs must be unique")
        return self


class CaseResult(Contract):
    case_id: str = Field(min_length=1, max_length=100)
    status: CaseResultStatus
    baseline_eligible: bool = False
    output_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    claim_results: list[ClaimEvaluation] = Field(
        default_factory=list,
        max_length=MAX_CAPTURED_CLAIMS + MAX_EXPECTED_FACTS,
    )
    unknown_claim_ids: list[str] = Field(default_factory=list, max_length=500)
    elapsed_ms: StrictInt | None = Field(default=None, ge=0)
    attempts: list[AttemptUsage] = Field(default_factory=list, max_length=100)
    unsupported_checks: list[UnsupportedCheck] = Field(
        default_factory=list, max_length=len(CheckName)
    )
    task_outcome: TaskOutcome | None = None
    usefulness: StrictInt | None = Field(default=None, ge=1, le=5)
    relevance_correct: bool | None = None
    identity_correct: bool | None = None

    @model_validator(mode="after")
    def attempts_are_sequential(self) -> Self:
        expected = list(range(1, len(self.attempts) + 1))
        if [item.attempt for item in self.attempts] != expected:
            raise ValueError("attempt numbers must be sequential from one")
        if len({item.claim_id for item in self.claim_results}) != len(
            self.claim_results
        ):
            raise ValueError("claim result IDs must be unique per case")
        return self


class Coverage(Contract):
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    review_pending: int = Field(ge=0)
    unsupported_feature: int = Field(ge=0)
    missing_result: int = Field(ge=0)
    pass_denominator: int = Field(ge=0)


class UsageTotals(Contract):
    attempted_input_tokens: int | None
    attempted_output_tokens: int | None
    terminal_input_tokens: int | None
    terminal_output_tokens: int | None
    attempted_cost_usd: Decimal | None
    terminal_cost_usd: Decimal | None


class EvaluationRun(Contract):
    id: str = Field(min_length=1, max_length=100)
    dataset_version: str = Field(min_length=1, max_length=50)
    dataset_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_hashes: dict[str, str]
    application_revision: str = Field(min_length=1, max_length=100)
    prompt_version: str = Field(min_length=1, max_length=100)
    model_id: str = Field(min_length=1, max_length=200)
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    mode: ExecutionMode
    source_hashes: dict[str, str]
    case_results: list[CaseResult] = Field(max_length=1000)

    @model_validator(mode="after")
    def case_result_ids_are_unique(self) -> Self:
        ids = [result.case_id for result in self.case_results]
        if len(set(ids)) != len(ids):
            raise ValueError("case result IDs must be unique")
        if set(self.case_hashes) != set(ids):
            raise ValueError("case hashes must cover the exact case result IDs")
        _validate_hash_values(self.source_hashes)
        _validate_hash_values(self.case_hashes)
        return self

    def content_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"id", "case_results"})
        payload["case_results"] = [
            {
                "case_id": result.case_id,
                "output_hash": result.output_hash,
                "elapsed_ms": result.elapsed_ms,
                "attempts": [
                    attempt.model_dump(mode="json") for attempt in result.attempts
                ],
            }
            for result in self.case_results
        ]
        return hashlib.sha256(_canonical_json(payload)).hexdigest()

    def coverage(self) -> Coverage:
        counts = {status: 0 for status in CaseResultStatus}
        for result in self.case_results:
            counts[result.status] += 1
        return Coverage(
            passed=counts[CaseResultStatus.PASSED],
            failed=counts[CaseResultStatus.FAILED],
            review_pending=counts[CaseResultStatus.REVIEW_PENDING],
            unsupported_feature=counts[CaseResultStatus.UNSUPPORTED_FEATURE],
            missing_result=counts[CaseResultStatus.MISSING_RESULT],
            pass_denominator=sum(
                result.baseline_eligible
                and result.status in {CaseResultStatus.PASSED, CaseResultStatus.FAILED}
                for result in self.case_results
            ),
        )

    def usage_totals(self) -> UsageTotals:
        attempts = [
            attempt for result in self.case_results for attempt in result.attempts
        ]
        terminal = [
            result.attempts[-1] for result in self.case_results if result.attempts
        ]
        return UsageTotals(
            attempted_input_tokens=_sum_known(item.input_tokens for item in attempts),
            attempted_output_tokens=_sum_known(item.output_tokens for item in attempts),
            terminal_input_tokens=_sum_known(item.input_tokens for item in terminal),
            terminal_output_tokens=_sum_known(item.output_tokens for item in terminal),
            attempted_cost_usd=_sum_decimal(item.cost_usd for item in attempts),
            terminal_cost_usd=_sum_decimal(item.cost_usd for item in terminal),
        )


class ClaimReview(Contract):
    case_id: str = Field(min_length=1, max_length=100)
    claim_id: str = Field(min_length=1, max_length=100)
    label: ReviewLabel
    kind_correct: bool = True


class CaseAssessment(Contract):
    case_id: str = Field(min_length=1, max_length=100)
    task_outcome: TaskOutcome
    usefulness: StrictInt = Field(ge=1, le=5)


class HumanReview(Contract):
    run_id: str = Field(min_length=1, max_length=100)
    dataset_version: str = Field(min_length=1, max_length=50)
    run_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_hashes: dict[str, str]
    reviewer: str = Field(min_length=1, max_length=100)
    reviewed_at: datetime
    claims: list[ClaimReview] = Field(default_factory=list, max_length=5000)
    assessments: list[CaseAssessment] = Field(default_factory=list, max_length=1000)

    @field_validator("source_hashes")
    @classmethod
    def source_hashes_are_valid(cls, value: dict[str, str]) -> dict[str, str]:
        _validate_hash_values(value)
        return value

    @field_validator("reviewed_at")
    @classmethod
    def review_timestamp_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("review timestamp must be timezone-aware")
        return value

    def validate_for(self, run: EvaluationRun) -> None:
        if (
            self.run_id != run.id
            or self.dataset_version != run.dataset_version
            or self.run_hash != run.content_hash()
            or self.source_hashes != run.source_hashes
        ):
            raise ValueError(
                "human review is not bound to this exact run and source set"
            )
        claim_ids = {
            (result.case_id, claim.claim_id)
            for result in run.case_results
            for claim in result.claim_results
        }
        if any(
            (review.case_id, review.claim_id) not in claim_ids for review in self.claims
        ):
            raise ValueError("human review refers to a claim absent from this run")
        review_ids = [(review.case_id, review.claim_id) for review in self.claims]
        if len(set(review_ids)) != len(review_ids):
            raise ValueError("human review contains duplicate claim labels")
        case_ids = {result.case_id for result in run.case_results}
        assessment_ids = [assessment.case_id for assessment in self.assessments]
        if any(case_id not in case_ids for case_id in assessment_ids):
            raise ValueError("human review assesses a case absent from this run")
        if len(set(assessment_ids)) != len(assessment_ids):
            raise ValueError("human review contains duplicate case assessments")


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _validate_hash_values(values: dict[str, str]) -> None:
    if any(re.fullmatch(r"[0-9a-f]{64}", digest) is None for digest in values.values()):
        raise ValueError("source hashes must be lowercase SHA-256 values")


def _sum_known(values: Iterable[int | None]) -> int | None:
    items = list(values)
    known = [item for item in items if item is not None]
    return sum(known) if known else None


def _sum_decimal(values: Iterable[Decimal | None]) -> Decimal | None:
    items = list(values)
    known = [item for item in items if item is not None]
    return sum(known, start=Decimal(0)) if known else None
