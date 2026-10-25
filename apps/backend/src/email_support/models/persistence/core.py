"""Typed contracts for canonical input and briefing records."""

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AnyHttpUrl, Field, PositiveInt, field_validator, model_validator

from .common import (
    EmailAddress,
    ExactText,
    NonBlankText,
    PersistenceContract,
    _normalize_email_domain,
    _normalize_optional_email_domain,
    _normalize_utc,
)


class EvidenceKind(StrEnum):
    MAIL = "mail"
    MEETING = "meeting"
    WEB = "web"


class MeetingTimeKind(StrEnum):
    TIMED = "timed"
    ALL_DAY = "all_day"


class ProviderAccountCreate(PersistenceContract):
    provider: NonBlankText
    external_account_id: NonBlankText


class ProviderAccountRecord(ProviderAccountCreate):
    id: UUID
    created_at: datetime

    _created_at_utc = field_validator("created_at")(_normalize_utc)


class CompanyCreate(PersistenceContract):
    name: NonBlankText
    domain: NonBlankText | None


class CompanyRecord(CompanyCreate):
    id: UUID
    created_at: datetime

    _created_at_utc = field_validator("created_at")(_normalize_utc)


class ContactCreate(PersistenceContract):
    company_id: UUID | None
    email: EmailAddress
    display_name: NonBlankText | None

    _email_domain_lower = field_validator("email")(_normalize_email_domain)


class ContactRecord(ContactCreate):
    id: UUID
    company_id: UUID | None
    created_at: datetime

    _created_at_utc = field_validator("created_at")(_normalize_utc)


class MailMessageCreate(PersistenceContract):
    account_id: UUID
    external_message_id: NonBlankText
    external_thread_id: NonBlankText | None
    sender_email: EmailAddress
    recipient_emails: list[EmailAddress] | None
    subject: str | None
    body_text: str | None
    received_at: datetime
    company_id: UUID | None
    contact_id: UUID | None

    _sender_domain_lower = field_validator("sender_email")(_normalize_email_domain)
    _received_at_utc = field_validator("received_at")(_normalize_utc)

    @field_validator("recipient_emails")
    @classmethod
    def normalize_recipient_domains(
        cls, value: list[EmailAddress] | None
    ) -> list[EmailAddress] | None:
        if value is None:
            return None
        return [_normalize_email_domain(address) for address in value]


class MailMessageRecord(MailMessageCreate):
    id: UUID
    created_at: datetime

    _created_at_utc = field_validator("created_at")(_normalize_utc)


class TimedMeetingTime(PersistenceContract):
    kind: Literal["timed"] = "timed"
    starts_at: datetime
    ends_at: datetime

    _instants_utc = field_validator("starts_at", "ends_at")(_normalize_utc)

    @model_validator(mode="after")
    def require_positive_duration(self) -> Self:
        if self.ends_at <= self.starts_at:
            raise ValueError("meeting end must follow start")
        return self


class AllDayMeetingTime(PersistenceContract):
    kind: Literal["all_day"] = "all_day"
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def require_positive_duration(self) -> Self:
        if self.end_date <= self.start_date:
            raise ValueError("all-day meeting end date must follow start date")
        return self


type MeetingTime = Annotated[
    TimedMeetingTime | AllDayMeetingTime,
    Field(discriminator="kind"),
]


class MeetingCreate(PersistenceContract):
    account_id: UUID
    external_calendar_id: NonBlankText
    external_event_id: NonBlankText
    title: str | None
    description: str | None
    organizer_email: EmailAddress | None
    attendee_emails: list[EmailAddress] | None
    company_id: UUID | None
    time: MeetingTime

    _organizer_domain_lower = field_validator("organizer_email")(
        _normalize_optional_email_domain
    )

    @field_validator("attendee_emails")
    @classmethod
    def normalize_attendee_domains(
        cls, value: list[EmailAddress] | None
    ) -> list[EmailAddress] | None:
        if value is None:
            return None
        return [_normalize_email_domain(address) for address in value]


class MeetingRecord(MeetingCreate):
    id: UUID
    created_at: datetime

    _created_at_utc = field_validator("created_at")(_normalize_utc)


class EvidenceCreate(PersistenceContract):
    kind: EvidenceKind
    mail_message_id: UUID | None
    meeting_id: UUID | None
    source_url: AnyHttpUrl | None
    source_text: ExactText
    retrieved_at: datetime

    _retrieved_at_utc = field_validator("retrieved_at")(_normalize_utc)

    @field_validator("source_text")
    @classmethod
    def require_nonblank_snapshot(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source snapshot must not be blank")
        return value

    @model_validator(mode="after")
    def require_matching_source(self) -> Self:
        sources = {
            EvidenceKind.MAIL: (self.mail_message_id is not None)
            and self.meeting_id is None
            and self.source_url is None,
            EvidenceKind.MEETING: (self.meeting_id is not None)
            and self.mail_message_id is None
            and self.source_url is None,
            EvidenceKind.WEB: self.source_url is not None
            and self.mail_message_id is None
            and self.meeting_id is None,
        }
        if not sources[self.kind]:
            raise ValueError("evidence source fields must match its kind")
        return self


class EvidenceRecord(EvidenceCreate):
    id: UUID
    created_at: datetime

    _created_at_utc = field_validator("created_at")(_normalize_utc)


class BriefingCreate(PersistenceContract):
    company_id: UUID | None


class BriefingRecord(BriefingCreate):
    id: UUID
    created_at: datetime

    _created_at_utc = field_validator("created_at")(_normalize_utc)


class BriefingVersionCreate(PersistenceContract):
    briefing_id: UUID
    markdown: ExactText
    evidence_ids: list[UUID]

    @field_validator("markdown")
    @classmethod
    def require_nonblank_markdown(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("briefing markdown must not be blank")
        return value


class BriefingVersionRecord(PersistenceContract):
    id: UUID
    briefing_id: UUID
    version_number: PositiveInt
    markdown: ExactText
    sealed: bool
    created_at: datetime
    evidence_ids: list[UUID]

    _created_at_utc = field_validator("created_at")(_normalize_utc)
