"""Persistence operations for normalized input and contact identity."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from email_support.models.email_interpretation import (
    CompanyCorrectionRequest,
    InputOriginKind,
    NormalizedInputCreate,
    NormalizedInputRecord,
    ProviderSourceKind,
)
from email_support.models.persistence import (
    AllDayMeetingTime,
    ContactCreate,
    ContactRecord,
    MailMessageRecord,
    MeetingTime,
    TimedMeetingTime,
)
from email_support.storage.postgres.persistence.core import (
    PersistenceConflict,
    PersistenceNotFound,
)
from email_support.storage.postgres.persistence.tables import (
    CompanyRow,
    ContactRow,
    MailMessageRow,
    MeetingRow,
    NormalizedInputRow,
)


def _normalized_input_record(row: NormalizedInputRow) -> NormalizedInputRecord:
    return NormalizedInputRecord.model_validate(
        {
            "id": row.id,
            "origin_kind": row.origin_kind,
            "origin_key": row.origin_key,
            "content_hash": row.content_hash,
            "payload": row.payload,
            "provider_source": row.provider_source,
            "created_at": row.created_at,
        }
    )


async def create_normalized_input(
    session: AsyncSession, value: NormalizedInputCreate
) -> NormalizedInputRecord:
    """Insert immutable input provenance, returning the same row for exact replay."""
    if value.origin_kind is InputOriginKind.PROVIDER:
        await _validate_provider_source(session, value)
    source = (
        value.provider_source.model_dump(mode="json")
        if value.provider_source is not None
        else None
    )
    statement = (
        pg_insert(NormalizedInputRow)
        .values(
            origin_kind=value.origin_kind.value,
            origin_key=value.origin_key,
            content_hash=value.content_hash,
            payload=value.payload.model_dump(mode="json"),
            provider_source=source,
        )
        .on_conflict_do_nothing(
            index_elements=[
                NormalizedInputRow.origin_kind,
                NormalizedInputRow.origin_key,
            ]
        )
        .returning(NormalizedInputRow)
    )
    row = await session.scalar(statement)
    if row is None:
        row = await session.scalar(
            select(NormalizedInputRow).where(
                NormalizedInputRow.origin_kind == value.origin_kind.value,
                NormalizedInputRow.origin_key == value.origin_key,
            )
        )
        if row is None:
            raise PersistenceConflict("normalized input origin already exists")
        if row.content_hash != value.content_hash:
            raise PersistenceConflict("normalized input content changed for its origin")
    return _normalized_input_record(row)


async def get_normalized_input(
    session: AsyncSession, input_id: UUID
) -> NormalizedInputRecord:
    row = await session.get(NormalizedInputRow, input_id)
    if row is None:
        raise PersistenceNotFound("normalized input not found")
    return _normalized_input_record(row)


async def get_or_create_contact_by_email(
    session: AsyncSession, value: ContactCreate
) -> ContactRecord:
    """Resolve the existing exact-local-part/lowercase-domain unique identity."""
    normalized_email = str(value.email)
    statement = (
        pg_insert(ContactRow)
        .values(
            company_id=value.company_id,
            email=normalized_email,
            display_name=value.display_name,
        )
        .on_conflict_do_nothing()
        .returning(ContactRow)
    )
    row = await session.scalar(statement)
    if row is None:
        local_part, domain = normalized_email.rsplit("@", maxsplit=1)
        row = await session.scalar(
            select(ContactRow).where(
                func.split_part(ContactRow.email, "@", 1) == local_part,
                func.lower(func.split_part(ContactRow.email, "@", 2)) == domain,
            )
        )
        if row is None:
            raise PersistenceConflict("contact email already belongs to another record")
    return _contact_record(row)


async def correct_contact_company(
    session: AsyncSession, request: CompanyCorrectionRequest
) -> ContactRecord:
    """Compare-and-set a durable company mapping; identical repeats are no-ops."""
    contact = await session.scalar(
        select(ContactRow).where(ContactRow.id == request.contact_id).with_for_update()
    )
    if contact is None:
        raise PersistenceNotFound("contact not found")
    if contact.company_id == request.company_id:
        return _contact_record(contact)
    if (
        request.company_id is not None
        and await session.get(CompanyRow, request.company_id) is None
    ):
        raise PersistenceNotFound("company not found")
    statement = (
        update(ContactRow)
        .where(
            ContactRow.id == request.contact_id,
            ContactRow.identity_revision == request.expected_revision,
        )
        .values(
            company_id=request.company_id,
            identity_revision=ContactRow.identity_revision + 1,
        )
        .returning(ContactRow)
    )
    updated = await session.scalar(statement)
    if updated is None:
        raise PersistenceConflict("contact identity revision changed")
    return _contact_record(updated)


async def list_eligible_mail_history(
    session: AsyncSession,
    *,
    contact_id: UUID,
    company_id: UUID | None,
    identity_revision: int,
) -> list[MailMessageRecord]:
    """Return only history still associated with this exact current identity."""
    if company_id is None:
        return []
    contact = await session.scalar(
        select(ContactRow).where(ContactRow.id == contact_id).with_for_update(read=True)
    )
    if contact is None:
        raise PersistenceNotFound("contact not found")
    if (
        contact.identity_revision != identity_revision
        or contact.company_id != company_id
    ):
        raise PersistenceConflict("contact identity snapshot is stale")
    rows = (
        await session.scalars(
            select(MailMessageRow)
            .where(
                MailMessageRow.contact_id == contact_id,
                MailMessageRow.company_id == company_id,
            )
            .order_by(MailMessageRow.received_at.desc(), MailMessageRow.id)
        )
    ).all()
    return [
        MailMessageRecord.model_validate(
            {
                "id": row.id,
                "account_id": row.account_id,
                "external_message_id": row.external_message_id,
                "external_thread_id": row.external_thread_id,
                "sender_email": row.sender_email,
                "recipient_emails": row.recipient_emails,
                "subject": row.subject,
                "body_text": row.body_text,
                "received_at": row.received_at,
                "company_id": row.company_id,
                "contact_id": row.contact_id,
                "created_at": row.created_at,
            }
        )
        for row in rows
    ]


def _contact_record(row: ContactRow) -> ContactRecord:
    return ContactRecord(
        id=row.id,
        company_id=row.company_id,
        identity_revision=row.identity_revision,
        email=row.email,
        display_name=row.display_name,
        created_at=row.created_at,
    )


async def _validate_provider_source(
    session: AsyncSession, value: NormalizedInputCreate
) -> None:
    source = value.provider_source
    if source is None:
        raise PersistenceConflict("provider input has no canonical source")
    expected_key = f"{source.kind.value}:{source.record_id}:{source.external_id}"
    if value.origin_key != expected_key:
        raise PersistenceConflict("provider input key does not match its source")
    if source.kind is ProviderSourceKind.MAIL:
        row = await session.get(MailMessageRow, source.record_id)
        if row is None or row.external_message_id != source.external_id:
            raise PersistenceNotFound("provider mail source not found")
        if (
            value.payload.sender_email != row.sender_email
            or value.payload.subject != row.subject
            or value.payload.body != (row.body_text or "")
            or value.payload.received_at != row.received_at
        ):
            raise PersistenceConflict("normalized mail input does not match its source")
        return
    row = await session.scalar(
        select(MeetingRow).where(MeetingRow.id == source.record_id)
    )
    if row is None or row.external_event_id != source.external_id:
        raise PersistenceNotFound("provider meeting source not found")
    meeting = value.payload.meeting
    if (
        row.time_kind == "timed"
        and row.starts_at is not None
        and row.ends_at is not None
    ):
        source_time: MeetingTime = TimedMeetingTime(
            starts_at=row.starts_at, ends_at=row.ends_at
        )
    elif (
        row.time_kind == "all_day"
        and row.start_date is not None
        and row.end_date is not None
    ):
        source_time = AllDayMeetingTime(
            start_date=row.start_date, end_date=row.end_date
        )
    else:
        raise PersistenceConflict("canonical meeting time is invalid")
    if (
        meeting is None
        or value.payload.meeting_state.value != "scheduled"
        or meeting.title != row.title
        or meeting.description != (row.description or "")
        or meeting.time != source_time
        or meeting.attendees != (row.attendee_emails or [])
    ):
        raise PersistenceConflict("normalized meeting input does not match its source")


__all__ = [
    "correct_contact_company",
    "create_normalized_input",
    "get_normalized_input",
    "get_or_create_contact_by_email",
    "list_eligible_mail_history",
]
