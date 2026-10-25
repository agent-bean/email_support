"""Concrete caller-session operations for core canonical records."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from email_support.models.persistence import (
    AllDayMeetingTime,
    BriefingCreate,
    BriefingRecord,
    BriefingVersionCreate,
    BriefingVersionRecord,
    CompanyCreate,
    CompanyRecord,
    ContactCreate,
    ContactRecord,
    EvidenceCreate,
    EvidenceRecord,
    MailMessageCreate,
    MailMessageRecord,
    MeetingCreate,
    MeetingRecord,
    ProviderAccountCreate,
    ProviderAccountRecord,
    TimedMeetingTime,
)
from email_support.storage.postgres.tables import (
    BriefingRow,
    BriefingVersionEvidenceRow,
    BriefingVersionRow,
    CompanyRow,
    ContactRow,
    EvidenceRow,
    MailMessageRow,
    MeetingRow,
    ProviderAccountRow,
)


class PersistenceConflict(RuntimeError):
    """A canonical unique key already belongs to a persisted record."""


class PersistenceNotFound(LookupError):
    """A requested canonical record does not exist or is not published."""


async def _flush(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as error:
        if getattr(error.orig, "sqlstate", None) == "23505":
            raise PersistenceConflict("canonical unique key already exists") from error
        raise


async def create_provider_account(
    session: AsyncSession, value: ProviderAccountCreate
) -> ProviderAccountRecord:
    row = ProviderAccountRow(
        provider=value.provider,
        external_account_id=value.external_account_id,
    )
    session.add(row)
    await _flush(session)
    return ProviderAccountRecord(
        id=row.id,
        provider=row.provider,
        external_account_id=row.external_account_id,
        created_at=row.created_at,
    )


async def get_provider_account(
    session: AsyncSession, account_id: UUID
) -> ProviderAccountRecord:
    row = await session.get(ProviderAccountRow, account_id)
    if row is None:
        raise PersistenceNotFound("provider account not found")
    return ProviderAccountRecord(
        id=row.id,
        provider=row.provider,
        external_account_id=row.external_account_id,
        created_at=row.created_at,
    )


async def create_company(session: AsyncSession, value: CompanyCreate) -> CompanyRecord:
    row = CompanyRow(name=value.name, domain=value.domain)
    session.add(row)
    await _flush(session)
    return CompanyRecord(
        id=row.id,
        name=row.name,
        domain=row.domain,
        created_at=row.created_at,
    )


async def get_company(session: AsyncSession, company_id: UUID) -> CompanyRecord:
    row = await session.get(CompanyRow, company_id)
    if row is None:
        raise PersistenceNotFound("company not found")
    return CompanyRecord(
        id=row.id,
        name=row.name,
        domain=row.domain,
        created_at=row.created_at,
    )


async def create_contact(session: AsyncSession, value: ContactCreate) -> ContactRecord:
    row = ContactRow(
        company_id=value.company_id,
        email=str(value.email),
        display_name=value.display_name,
    )
    session.add(row)
    await _flush(session)
    return ContactRecord(
        id=row.id,
        company_id=row.company_id,
        email=row.email,
        display_name=row.display_name,
        created_at=row.created_at,
    )


async def get_contact(session: AsyncSession, contact_id: UUID) -> ContactRecord:
    row = await session.get(ContactRow, contact_id)
    if row is None:
        raise PersistenceNotFound("contact not found")
    return ContactRecord(
        id=row.id,
        company_id=row.company_id,
        email=row.email,
        display_name=row.display_name,
        created_at=row.created_at,
    )


async def create_mail_message(
    session: AsyncSession, value: MailMessageCreate
) -> MailMessageRecord:
    row = MailMessageRow(
        account_id=value.account_id,
        external_message_id=value.external_message_id,
        external_thread_id=value.external_thread_id,
        sender_email=str(value.sender_email),
        recipient_emails=(
            [str(address) for address in value.recipient_emails]
            if value.recipient_emails is not None
            else None
        ),
        subject=value.subject,
        body_text=value.body_text,
        received_at=value.received_at,
        company_id=value.company_id,
        contact_id=value.contact_id,
    )
    session.add(row)
    await _flush(session)
    return MailMessageRecord(
        id=row.id,
        account_id=row.account_id,
        external_message_id=row.external_message_id,
        external_thread_id=row.external_thread_id,
        sender_email=row.sender_email,
        recipient_emails=row.recipient_emails,
        subject=row.subject,
        body_text=row.body_text,
        received_at=row.received_at,
        company_id=row.company_id,
        contact_id=row.contact_id,
        created_at=row.created_at,
    )


async def get_mail_message(
    session: AsyncSession, message_id: UUID
) -> MailMessageRecord:
    row = await session.get(MailMessageRow, message_id)
    if row is None:
        raise PersistenceNotFound("mail message not found")
    return MailMessageRecord(
        id=row.id,
        account_id=row.account_id,
        external_message_id=row.external_message_id,
        external_thread_id=row.external_thread_id,
        sender_email=row.sender_email,
        recipient_emails=row.recipient_emails,
        subject=row.subject,
        body_text=row.body_text,
        received_at=row.received_at,
        company_id=row.company_id,
        contact_id=row.contact_id,
        created_at=row.created_at,
    )


def _meeting_time(row: MeetingRow) -> TimedMeetingTime | AllDayMeetingTime:
    if row.time_kind == "timed":
        if row.starts_at is None or row.ends_at is None:
            raise RuntimeError("timed meeting is missing its instants")
        return TimedMeetingTime(starts_at=row.starts_at, ends_at=row.ends_at)
    if row.time_kind == "all_day":
        if row.start_date is None or row.end_date is None:
            raise RuntimeError("all-day meeting is missing its dates")
        return AllDayMeetingTime(start_date=row.start_date, end_date=row.end_date)
    raise RuntimeError("meeting has an unknown time kind")


def _meeting_record(row: MeetingRow) -> MeetingRecord:
    return MeetingRecord(
        id=row.id,
        account_id=row.account_id,
        external_calendar_id=row.external_calendar_id,
        external_event_id=row.external_event_id,
        title=row.title,
        description=row.description,
        organizer_email=row.organizer_email,
        attendee_emails=row.attendee_emails,
        company_id=row.company_id,
        time=_meeting_time(row),
        created_at=row.created_at,
    )


async def create_meeting(session: AsyncSession, value: MeetingCreate) -> MeetingRecord:
    if isinstance(value.time, TimedMeetingTime):
        time_fields: dict[str, str | datetime | date | None] = {
            "time_kind": "timed",
            "starts_at": value.time.starts_at,
            "ends_at": value.time.ends_at,
            "start_date": None,
            "end_date": None,
        }
    else:
        time_fields = {
            "time_kind": "all_day",
            "starts_at": None,
            "ends_at": None,
            "start_date": value.time.start_date,
            "end_date": value.time.end_date,
        }
    row = MeetingRow(
        account_id=value.account_id,
        external_calendar_id=value.external_calendar_id,
        external_event_id=value.external_event_id,
        title=value.title,
        description=value.description,
        organizer_email=(
            str(value.organizer_email) if value.organizer_email is not None else None
        ),
        attendee_emails=(
            [str(address) for address in value.attendee_emails]
            if value.attendee_emails is not None
            else None
        ),
        company_id=value.company_id,
        **time_fields,
    )
    session.add(row)
    await _flush(session)
    return _meeting_record(row)


async def get_meeting(session: AsyncSession, meeting_id: UUID) -> MeetingRecord:
    row = await session.get(MeetingRow, meeting_id)
    if row is None:
        raise PersistenceNotFound("meeting not found")
    return _meeting_record(row)


async def create_evidence(
    session: AsyncSession, value: EvidenceCreate
) -> EvidenceRecord:
    row = EvidenceRow(
        kind=value.kind.value,
        mail_message_id=value.mail_message_id,
        meeting_id=value.meeting_id,
        source_url=str(value.source_url) if value.source_url is not None else None,
        source_text=value.source_text,
        retrieved_at=value.retrieved_at,
    )
    session.add(row)
    await _flush(session)
    return _evidence_record(row)


def _evidence_record(row: EvidenceRow) -> EvidenceRecord:
    return EvidenceRecord.model_validate(
        {
            "id": row.id,
            "kind": row.kind,
            "mail_message_id": row.mail_message_id,
            "meeting_id": row.meeting_id,
            "source_url": row.source_url,
            "source_text": row.source_text,
            "retrieved_at": row.retrieved_at,
            "created_at": row.created_at,
        }
    )


async def get_evidence(session: AsyncSession, evidence_id: UUID) -> EvidenceRecord:
    row = await session.get(EvidenceRow, evidence_id)
    if row is None:
        raise PersistenceNotFound("evidence not found")
    return _evidence_record(row)


async def create_briefing(
    session: AsyncSession, value: BriefingCreate
) -> BriefingRecord:
    row = BriefingRow(company_id=value.company_id)
    session.add(row)
    await _flush(session)
    return BriefingRecord(
        id=row.id,
        company_id=row.company_id,
        created_at=row.created_at,
    )


async def create_briefing_version(
    session: AsyncSession, value: BriefingVersionCreate
) -> BriefingVersionRecord:
    briefing = await session.scalar(
        select(BriefingRow).where(BriefingRow.id == value.briefing_id).with_for_update()
    )
    if briefing is None:
        raise PersistenceNotFound("briefing not found")

    latest_number = await session.scalar(
        select(func.max(BriefingVersionRow.version_number)).where(
            BriefingVersionRow.briefing_id == value.briefing_id
        )
    )
    row = BriefingVersionRow(
        briefing_id=value.briefing_id,
        version_number=(latest_number or 0) + 1,
        markdown=value.markdown,
        sealed=False,
    )
    session.add(row)
    await _flush(session)

    links = [
        BriefingVersionEvidenceRow(briefing_version_id=row.id, evidence_id=evidence_id)
        for evidence_id in value.evidence_ids
    ]
    session.add_all(links)
    await _flush(session)

    row.sealed = True
    await _flush(session)
    return BriefingVersionRecord(
        id=row.id,
        briefing_id=row.briefing_id,
        version_number=row.version_number,
        markdown=row.markdown,
        sealed=row.sealed,
        created_at=row.created_at,
        evidence_ids=list(value.evidence_ids),
    )


async def get_briefing_version(
    session: AsyncSession, briefing_id: UUID, version_number: int
) -> BriefingVersionRecord:
    row = await session.scalar(
        select(BriefingVersionRow).where(
            BriefingVersionRow.briefing_id == briefing_id,
            BriefingVersionRow.version_number == version_number,
            BriefingVersionRow.sealed.is_(True),
        )
    )
    if row is None:
        raise PersistenceNotFound("sealed briefing version not found")
    evidence_ids = list(
        await session.scalars(
            select(BriefingVersionEvidenceRow.evidence_id)
            .where(BriefingVersionEvidenceRow.briefing_version_id == row.id)
            .order_by(BriefingVersionEvidenceRow.evidence_id)
        )
    )
    return BriefingVersionRecord(
        id=row.id,
        briefing_id=row.briefing_id,
        version_number=row.version_number,
        markdown=row.markdown,
        sealed=row.sealed,
        created_at=row.created_at,
        evidence_ids=evidence_ids,
    )
