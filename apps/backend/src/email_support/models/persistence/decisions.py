"""Typed contracts for approvals, actions, knowledge and preferences."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import Field, JsonValue, field_validator, model_validator

from .common import (
    EmailAddress,
    ExactText,
    NonBlankText,
    PersistenceContract,
    _normalize_email_domain,
    _normalize_optional_utc,
    _normalize_utc,
)


class ActionKind(StrEnum):
    SEND_EMAIL = "send_email"
    SAVE_KNOWLEDGE = "save_knowledge"


class ApprovalCreate(PersistenceContract):
    briefing_id: UUID
    briefing_version_id: UUID
    action_kind: ActionKind
    recipient_emails: list[EmailAddress]
    selected_knowledge: list[ExactText]

    @field_validator("recipient_emails")
    @classmethod
    def normalize_recipients(cls, value: list[EmailAddress]) -> list[EmailAddress]:
        normalized = {_normalize_email_domain(address) for address in value}
        return sorted(normalized)

    @field_validator("selected_knowledge")
    @classmethod
    def preserve_nonblank_selected_text(cls, value: list[str]) -> list[str]:
        if any(not text.strip() for text in value):
            raise ValueError("selected knowledge text must not be blank")
        return value

    @model_validator(mode="after")
    def require_action_payload(self) -> Self:
        if self.action_kind is ActionKind.SEND_EMAIL:
            if not self.recipient_emails or self.selected_knowledge:
                raise ValueError("send approvals require recipients and no knowledge")
        elif self.recipient_emails or not self.selected_knowledge:
            raise ValueError(
                "knowledge approvals require selected text and no recipients"
            )
        return self


class ApprovalRecord(ApprovalCreate):
    id: UUID
    approved_at: datetime

    _approved_at_utc = field_validator("approved_at")(_normalize_utc)


class ActionRecord(PersistenceContract):
    id: UUID
    approval_id: UUID
    created_at: datetime

    _created_at_utc = field_validator("created_at")(_normalize_utc)


class KnowledgeCreate(PersistenceContract):
    approval_id: UUID
    selection_index: Annotated[int, Field(ge=0)]
    evidence_ids: list[UUID]


class KnowledgeRecord(PersistenceContract):
    id: UUID
    company_id: UUID | None
    approval_id: UUID
    selection_index: Annotated[int, Field(ge=0)]
    briefing_version_id: UUID
    content: ExactText
    created_at: datetime
    invalidated_at: datetime | None
    evidence_ids: list[UUID]

    _created_at_utc = field_validator("created_at")(_normalize_utc)
    _invalidated_at_utc = field_validator("invalidated_at")(_normalize_optional_utc)


class PreferenceCreate(PersistenceContract):
    key: NonBlankText
    value: JsonValue


class PreferenceRecord(PreferenceCreate):
    id: UUID
    updated_at: datetime

    _updated_at_utc = field_validator("updated_at")(_normalize_utc)
