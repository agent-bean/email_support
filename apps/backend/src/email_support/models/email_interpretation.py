"""Typed normalized input and email interpretation contracts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from email_support.models.persistence.common import (
    EmailAddress,
    NonBlankText,
    PersistenceContract,
    _normalize_email_domain,
    _normalize_optional_email_domain,
    _normalize_utc,
)
from email_support.models.persistence.core import MeetingTime


class InputOriginKind(StrEnum):
    LOCAL_IMPORT = "local_import"
    EVALUATION = "evaluation"
    PROVIDER = "provider"


class ProviderSourceKind(StrEnum):
    MAIL = "mail"
    MEETING = "meeting"


class ProviderSourceReference(PersistenceContract):
    kind: ProviderSourceKind
    record_id: UUID
    external_id: NonBlankText = Field(max_length=500)


class MeetingState(StrEnum):
    ABSENT = "absent"
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"


class InputField(StrEnum):
    SENDER_NAME = "sender_display_name"
    EMAIL_SUBJECT = "subject"
    EMAIL_BODY = "body"
    MEETING_TITLE = "meeting.title"
    MEETING_DESCRIPTION = "meeting.description"


class NormalizedMeeting(PersistenceContract):
    title: str | None = Field(default=None, max_length=500)
    description: str = Field(default="", max_length=10_000)
    time: MeetingTime
    attendees: list[EmailAddress] = Field(default_factory=list, max_length=50)

    @field_validator("attendees")
    @classmethod
    def normalize_attendee_domains(cls, values: list[str]) -> list[str]:
        return [_normalize_email_domain(value) for value in values]


class NormalizedEmailInput(PersistenceContract):
    sender_email: EmailAddress | None
    sender_display_name: str | None = Field(default=None, max_length=300)
    subject: str | None = Field(default=None, max_length=500)
    body: str = Field(default="", max_length=100_000)
    received_at: datetime
    meeting_state: MeetingState
    meeting: NormalizedMeeting | None

    _sender_domain_lower = field_validator("sender_email")(
        _normalize_optional_email_domain
    )
    _received_at_utc = field_validator("received_at")(_normalize_utc)

    @model_validator(mode="after")
    def meeting_matches_state(self) -> Self:
        if (self.meeting_state is MeetingState.SCHEDULED) != (self.meeting is not None):
            raise ValueError("meeting details must match the explicit meeting state")
        return self


class NormalizedInputCreate(PersistenceContract):
    origin_kind: InputOriginKind
    origin_key: NonBlankText = Field(max_length=500)
    payload: NormalizedEmailInput
    provider_source: ProviderSourceReference | None = None

    @model_validator(mode="after")
    def provider_source_matches_origin(self) -> Self:
        if (self.origin_kind is InputOriginKind.PROVIDER) != (
            self.provider_source is not None
        ):
            raise ValueError("provider origin requires a canonical source reference")
        return self

    @property
    def content_hash(self) -> str:
        document = {
            "payload": self.payload.model_dump(mode="json"),
            "provider_source": (
                self.provider_source.model_dump(mode="json")
                if self.provider_source is not None
                else None
            ),
        }
        canonical = json.dumps(
            document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class NormalizedInputRecord(PersistenceContract):
    id: UUID
    origin_kind: InputOriginKind
    origin_key: str
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload: NormalizedEmailInput
    provider_source: ProviderSourceReference | None
    created_at: datetime

    _created_at_utc = field_validator("created_at")(_normalize_utc)


class CompanyIdentityStatus(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"
    NONE = "none"


class CompanyCorrectionRequest(PersistenceContract):
    contact_id: UUID
    company_id: UUID | None
    expected_revision: int = Field(ge=1)


class IdentitySnapshot(PersistenceContract):
    status: CompanyIdentityStatus
    contact_id: UUID | None
    company_id: UUID | None
    identity_revision: int | None = Field(default=None, ge=1)
    candidate_company_ids: list[UUID] = Field(max_length=20)

    @model_validator(mode="after")
    def snapshot_is_consistent(self) -> Self:
        if self.status is CompanyIdentityStatus.RESOLVED:
            if (
                self.contact_id is None
                or self.company_id is None
                or self.identity_revision is None
            ):
                raise ValueError("resolved identity requires a mapped contact")
        elif self.company_id is not None:
            raise ValueError("non-resolved identity cannot select a company")
        if self.status is CompanyIdentityStatus.NONE and self.contact_id is not None:
            raise ValueError("no-identity status cannot reference a contact")
        return self


class EmailRelevance(StrEnum):
    RELEVANT = "relevant"
    IRRELEVANT = "irrelevant"
    UNCERTAIN = "uncertain"


class EvidenceSpan(PersistenceContract):
    field: InputField
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def nonempty(self) -> Self:
        if self.end <= self.start:
            raise ValueError("evidence span end must follow start")
        return self

    def validate_against(self, payload: NormalizedEmailInput) -> str:
        source = _input_text(payload, self.field)
        if source is None or self.end > len(source):
            raise ValueError("evidence span is outside the normalized input")
        matched = source[self.start : self.end]
        if matched != self.quote:
            raise ValueError("evidence span does not match input")
        return matched


class CompanyCandidate(PersistenceContract):
    name: NonBlankText = Field(max_length=200)
    domain: str | None = Field(default=None, max_length=253)
    evidence: list[EvidenceSpan] = Field(min_length=1, max_length=5)


class ContactCandidate(PersistenceContract):
    email: EmailAddress | None = None
    display_name: str | None = Field(default=None, max_length=300)
    evidence: list[EvidenceSpan] = Field(min_length=1, max_length=5)

    _email_domain_lower = field_validator("email")(_normalize_optional_email_domain)


class StatedNeed(PersistenceContract):
    text: NonBlankText = Field(max_length=1000)
    evidence: list[EvidenceSpan] = Field(min_length=1, max_length=5)


class EmailInterpretation(PersistenceContract):
    relevance: EmailRelevance
    company_candidates: list[CompanyCandidate] = Field(max_length=10)
    contact_candidates: list[ContactCandidate] = Field(max_length=10)
    stated_needs: list[StatedNeed] = Field(max_length=20)
    ambiguity_reasons: list[NonBlankText] = Field(max_length=10)
    unknowns: list[NonBlankText] = Field(max_length=20)

    @model_validator(mode="after")
    def irrelevant_has_no_stated_need(self) -> Self:
        if self.relevance is EmailRelevance.IRRELEVANT and self.stated_needs:
            raise ValueError("irrelevant input cannot contain stated business needs")
        return self

    def validate_evidence_against(self, payload: NormalizedEmailInput) -> None:
        spans = [
            span for candidate in self.company_candidates for span in candidate.evidence
        ]
        spans.extend(
            span for candidate in self.contact_candidates for span in candidate.evidence
        )
        spans.extend(span for need in self.stated_needs for span in need.evidence)
        for span in spans:
            span.validate_against(payload)


def _input_text(payload: NormalizedEmailInput, field: InputField) -> str | None:
    if field is InputField.SENDER_NAME:
        return payload.sender_display_name
    if field is InputField.EMAIL_SUBJECT:
        return payload.subject
    if field is InputField.EMAIL_BODY:
        return payload.body
    if payload.meeting is None:
        return None
    if field is InputField.MEETING_TITLE:
        return payload.meeting.title
    return payload.meeting.description


__all__ = [
    "CompanyCandidate",
    "CompanyCorrectionRequest",
    "CompanyIdentityStatus",
    "ContactCandidate",
    "EmailInterpretation",
    "EmailRelevance",
    "EvidenceSpan",
    "InputField",
    "InputOriginKind",
    "IdentitySnapshot",
    "MeetingState",
    "NormalizedEmailInput",
    "NormalizedInputCreate",
    "NormalizedInputRecord",
    "NormalizedMeeting",
    "ProviderSourceKind",
    "ProviderSourceReference",
    "StatedNeed",
]
