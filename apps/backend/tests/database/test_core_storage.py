import asyncio
from datetime import UTC, date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import AnyHttpUrl, TypeAdapter
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from email_support.models.persistence import (
    AllDayMeetingTime,
    BriefingCreate,
    BriefingVersionCreate,
    BriefingVersionRecord,
    CompanyCreate,
    ContactCreate,
    EvidenceCreate,
    EvidenceKind,
    MailMessageCreate,
    MeetingCreate,
    ProviderAccountCreate,
    ProviderAccountRecord,
    TimedMeetingTime,
)
from email_support.storage.postgres.core import (
    PersistenceConflict,
    create_briefing,
    create_briefing_version,
    create_company,
    create_contact,
    create_evidence,
    create_mail_message,
    create_meeting,
    create_provider_account,
    get_briefing_version,
    get_company,
    get_contact,
    get_evidence,
    get_mail_message,
    get_meeting,
    get_provider_account,
)

HTTP_URL_ADAPTER: TypeAdapter[AnyHttpUrl] = TypeAdapter(AnyHttpUrl)


def _http_url(value: str) -> AnyHttpUrl:
    return HTTP_URL_ADAPTER.validate_python(value)


async def _wait_until_database_session_is_blocked(
    database_sessions: async_sessionmaker[AsyncSession], application_name: str
) -> None:
    async def wait() -> None:
        async with database_sessions() as observer:
            while True:
                await observer.execute(text("SELECT pg_stat_clear_snapshot()"))
                activity = (
                    await observer.execute(
                        text(
                            "SELECT state, wait_event_type, wait_event, "
                            "cardinality(pg_blocking_pids(pid)) "
                            "FROM pg_stat_activity WHERE application_name = :name"
                        ),
                        {"name": application_name},
                    )
                ).one_or_none()
                if activity is not None and activity[3] and activity[3] > 0:
                    return

    try:
        await asyncio.wait_for(wait(), timeout=10)
    except TimeoutError as error:
        async with database_sessions() as observer:
            activities = list(
                await observer.execute(
                    text(
                        "SELECT state, wait_event_type, wait_event, "
                        "cardinality(pg_blocking_pids(pid)) "
                        "FROM pg_stat_activity WHERE application_name = :name"
                    ),
                    {"name": application_name},
                )
            )
        raise AssertionError(
            f"database session {application_name!r} did not reach a lock wait: "
            f"{activities!r}"
        ) from error


@pytest.mark.asyncio
async def test_core_records_round_trip_from_an_independent_connection(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with database_sessions() as session, session.begin():
        account = await create_provider_account(
            session,
            ProviderAccountCreate(provider="gmail", external_account_id="acct-1"),
        )
        company = await create_company(
            session, CompanyCreate(name="Acme", domain="acme.example")
        )
        contact = await create_contact(
            session,
            ContactCreate(
                email="Sales@EXAMPLE.COM",
                display_name=None,
                company_id=company.id,
            ),
        )
        mail = await create_mail_message(
            session,
            MailMessageCreate(
                account_id=account.id,
                external_message_id="mail-1",
                external_thread_id=None,
                sender_email="sender@example.com",
                recipient_emails=["owner@example.com"],
                subject=None,
                body_text=None,
                received_at=datetime(2026, 10, 25, 10, tzinfo=UTC),
                company_id=company.id,
                contact_id=contact.id,
            ),
        )
        meeting = await create_meeting(
            session,
            MeetingCreate(
                account_id=account.id,
                external_calendar_id="primary",
                external_event_id="event-1",
                title=None,
                description=None,
                organizer_email=None,
                attendee_emails=None,
                company_id=company.id,
                time=AllDayMeetingTime(
                    start_date=date(2026, 10, 25), end_date=date(2026, 10, 26)
                ),
            ),
        )
        evidence = await create_evidence(
            session,
            EvidenceCreate(
                kind=EvidenceKind.MAIL,
                mail_message_id=mail.id,
                meeting_id=None,
                source_url=None,
                source_text="Exact source snapshot",
                retrieved_at=datetime(
                    2026, 10, 25, 17, tzinfo=timezone(timedelta(hours=7))
                ),
            ),
        )
        briefing = await create_briefing(session, BriefingCreate(company_id=company.id))
        version = await create_briefing_version(
            session,
            BriefingVersionCreate(
                briefing_id=briefing.id,
                markdown="# Acme",
                evidence_ids=[evidence.id],
            ),
        )

    async with database_sessions() as independent_session:
        stored_account = await get_provider_account(independent_session, account.id)
        stored_company = await get_company(independent_session, company.id)
        stored_contact = await get_contact(independent_session, contact.id)
        stored_mail = await get_mail_message(independent_session, mail.id)
        stored_meeting = await get_meeting(independent_session, meeting.id)
        stored_evidence = await get_evidence(independent_session, evidence.id)
        stored_version = await get_briefing_version(
            independent_session, briefing.id, version.version_number
        )

    assert stored_account.id == account.id
    assert stored_company.name == "Acme"
    assert stored_contact.email == "Sales@example.com"
    assert stored_mail.subject is None and stored_mail.body_text is None
    assert stored_mail.received_at == datetime(2026, 10, 25, 10, tzinfo=UTC)
    assert stored_meeting.time == AllDayMeetingTime(
        start_date=date(2026, 10, 25), end_date=date(2026, 10, 26)
    )
    assert stored_evidence.source_text == "Exact source snapshot"
    assert stored_version.markdown == "# Acme"
    assert stored_version.sealed is True
    assert stored_version.evidence_ids == [evidence.id]


@pytest.mark.asyncio
async def test_timed_meeting_round_trip_preserves_the_instant_in_utc(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    local_start = datetime(2026, 10, 25, 17, tzinfo=timezone(timedelta(hours=7)))
    async with database_sessions() as session, session.begin():
        account = await create_provider_account(
            session,
            ProviderAccountCreate(provider="calendar", external_account_id="acct-2"),
        )
        meeting = await create_meeting(
            session,
            MeetingCreate(
                account_id=account.id,
                external_calendar_id="work",
                external_event_id="event-timed",
                title="Review",
                description=None,
                organizer_email="owner@example.com",
                attendee_emails=[],
                company_id=None,
                time=TimedMeetingTime(
                    starts_at=local_start,
                    ends_at=local_start + timedelta(hours=1),
                ),
            ),
        )

    async with database_sessions() as independent_session:
        stored = await get_meeting(independent_session, meeting.id)

    assert isinstance(stored.time, TimedMeetingTime)
    assert stored.time.starts_at == datetime(2026, 10, 25, 10, tzinfo=UTC)
    assert stored.time.ends_at == datetime(2026, 10, 25, 11, tzinfo=UTC)


@pytest.mark.asyncio
async def test_duplicate_provider_key_returns_named_conflict(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with database_sessions() as session, session.begin():
        await create_provider_account(
            session,
            ProviderAccountCreate(provider="gmail", external_account_id="shared"),
        )

    with pytest.raises(PersistenceConflict):
        async with database_sessions() as session, session.begin():
            await create_provider_account(
                session,
                ProviderAccountCreate(provider="gmail", external_account_id="shared"),
            )


@pytest.mark.asyncio
async def test_orphan_foreign_key_is_rejected(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(IntegrityError):
        async with database_sessions() as session, session.begin():
            await create_mail_message(
                session,
                MailMessageCreate(
                    account_id=uuid4(),
                    external_message_id="orphan",
                    external_thread_id=None,
                    sender_email="sender@example.com",
                    recipient_emails=None,
                    subject=None,
                    body_text=None,
                    received_at=datetime.now(UTC),
                    company_id=None,
                    contact_id=None,
                ),
            )


@pytest.mark.asyncio
async def test_version_creation_seals_history_and_rejects_raw_mutation(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with database_sessions() as session, session.begin():
        briefing = await create_briefing(session, BriefingCreate(company_id=None))
        version = await create_briefing_version(
            session,
            BriefingVersionCreate(
                briefing_id=briefing.id, markdown="original", evidence_ids=[]
            ),
        )
        assert version.version_number == 1

    with pytest.raises(DBAPIError) as error:
        async with database_sessions() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE briefing_versions SET markdown = 'changed' WHERE id = :id"
                ),
                {"id": version.id},
            )
    assert getattr(error.value.orig, "sqlstate", None) == "P0001"

    async with database_sessions() as independent_session:
        stored = await get_briefing_version(
            independent_session, briefing.id, version.version_number
        )
    assert stored.markdown == "original"


@pytest.mark.asyncio
async def test_external_keys_are_scoped_to_their_provider_account_and_calendar(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with database_sessions() as session, session.begin():
        first_account = await create_provider_account(
            session,
            ProviderAccountCreate(provider="gmail", external_account_id="first"),
        )
        second_account = await create_provider_account(
            session,
            ProviderAccountCreate(provider="gmail", external_account_id="second"),
        )
        first_message = await create_mail_message(
            session,
            MailMessageCreate(
                account_id=first_account.id,
                external_message_id="same-message-id",
                external_thread_id=None,
                sender_email="owner@example.com",
                recipient_emails=None,
                subject=None,
                body_text=None,
                received_at=datetime(2026, 10, 25, 10, tzinfo=UTC),
                company_id=None,
                contact_id=None,
            ),
        )
        second_message = await create_mail_message(
            session,
            MailMessageCreate(
                account_id=second_account.id,
                external_message_id="same-message-id",
                external_thread_id=None,
                sender_email="owner@example.com",
                recipient_emails=None,
                subject=None,
                body_text=None,
                received_at=datetime(2026, 10, 25, 10, tzinfo=UTC),
                company_id=None,
                contact_id=None,
            ),
        )
        primary_event = await create_meeting(
            session,
            MeetingCreate(
                account_id=first_account.id,
                external_calendar_id="primary",
                external_event_id="same-event-id",
                title=None,
                description=None,
                organizer_email=None,
                attendee_emails=None,
                company_id=None,
                time=AllDayMeetingTime(
                    start_date=date(2026, 10, 25), end_date=date(2026, 10, 26)
                ),
            ),
        )
        shared_calendar_event = await create_meeting(
            session,
            MeetingCreate(
                account_id=first_account.id,
                external_calendar_id="shared",
                external_event_id="same-event-id",
                title=None,
                description=None,
                organizer_email=None,
                attendee_emails=None,
                company_id=None,
                time=AllDayMeetingTime(
                    start_date=date(2026, 10, 25), end_date=date(2026, 10, 26)
                ),
            ),
        )

    assert first_message.id != second_message.id
    assert primary_event.id != shared_calendar_event.id
    with pytest.raises(PersistenceConflict):
        async with database_sessions() as session, session.begin():
            await create_mail_message(
                session,
                MailMessageCreate(
                    account_id=first_account.id,
                    external_message_id="same-message-id",
                    external_thread_id=None,
                    sender_email="owner@example.com",
                    recipient_emails=None,
                    subject=None,
                    body_text=None,
                    received_at=datetime(2026, 10, 25, 10, tzinfo=UTC),
                    company_id=None,
                    contact_id=None,
                ),
            )
    with pytest.raises(PersistenceConflict):
        async with database_sessions() as session, session.begin():
            await create_meeting(
                session,
                MeetingCreate(
                    account_id=first_account.id,
                    external_calendar_id="primary",
                    external_event_id="same-event-id",
                    title=None,
                    description=None,
                    organizer_email=None,
                    attendee_emails=None,
                    company_id=None,
                    time=AllDayMeetingTime(
                        start_date=date(2026, 10, 25), end_date=date(2026, 10, 26)
                    ),
                ),
            )


@pytest.mark.asyncio
async def test_contact_uniqueness_preserves_local_part_case(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with database_sessions() as session, session.begin():
        first = await create_contact(
            session,
            ContactCreate(
                email="Sales@EXAMPLE.COM", display_name=None, company_id=None
            ),
        )

    assert first.email == "Sales@example.com"
    with pytest.raises(PersistenceConflict):
        async with database_sessions() as session, session.begin():
            await create_contact(
                session,
                ContactCreate(
                    email="Sales@example.com", display_name=None, company_id=None
                ),
            )
    async with database_sessions() as session, session.begin():
        lower_local = await create_contact(
            session,
            ContactCreate(
                email="sales@example.com", display_name=None, company_id=None
            ),
        )
    assert lower_local.email == "sales@example.com"


@pytest.mark.asyncio
async def test_raw_sql_cannot_store_a_mixed_meeting_time_shape(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with database_sessions() as session, session.begin():
        account = await create_provider_account(
            session,
            ProviderAccountCreate(provider="calendar", external_account_id="acct"),
        )

    with pytest.raises(IntegrityError) as error:
        async with database_sessions() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO meetings (id, account_id, external_calendar_id, "
                    "external_event_id, time_kind, starts_at, ends_at, start_date, "
                    "end_date) VALUES (:id, :account_id, 'primary', 'bad-shape', "
                    "'timed', '2026-10-25T10:00:00Z', '2026-10-25T11:00:00Z', "
                    "'2026-10-25', NULL)"
                ),
                {"id": uuid4(), "account_id": account.id},
            )
    assert getattr(error.value.orig, "sqlstate", None) == "23514"


@pytest.mark.asyncio
async def test_unsealed_version_cannot_commit(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with database_sessions() as session, session.begin():
        briefing = await create_briefing(session, BriefingCreate(company_id=None))

    version_id = uuid4()
    with pytest.raises(DBAPIError) as error:
        async with database_sessions() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO briefing_versions "
                    "(id, briefing_id, version_number, markdown, sealed) "
                    "VALUES (:id, :briefing_id, 1, 'unsealed', false)"
                ),
                {"id": version_id, "briefing_id": briefing.id},
            )
    assert getattr(error.value.orig, "sqlstate", None) == "P0001"

    async with database_sessions() as session:
        count = await session.scalar(
            text("SELECT count(*) FROM briefing_versions WHERE id = :id"),
            {"id": version_id},
        )
    assert count == 0


@pytest.mark.asyncio
async def test_caller_rollback_removes_flushed_core_records(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(RuntimeError, match="caller rollback"):
        async with database_sessions() as session, session.begin():
            await create_provider_account(
                session,
                ProviderAccountCreate(
                    provider="gmail", external_account_id="rolled-back"
                ),
            )
            raise RuntimeError("caller rollback")

    async with database_sessions() as session:
        count = await session.scalar(
            text(
                "SELECT count(*) FROM provider_accounts "
                "WHERE provider = 'gmail' AND external_account_id = 'rolled-back'"
            )
        )
    assert count == 0


@pytest.mark.asyncio
async def test_concurrent_duplicate_provider_insert_has_one_named_conflict(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    first_inserted = asyncio.Event()
    release_first = asyncio.Event()
    application_name = f"duplicate-{uuid4().hex}"

    async def insert_first() -> ProviderAccountRecord:
        async with database_sessions() as session, session.begin():
            record = await create_provider_account(
                session,
                ProviderAccountCreate(provider="gmail", external_account_id="race"),
            )
            first_inserted.set()
            await release_first.wait()
            return record

    async def insert_competitor() -> PersistenceConflict | None:
        try:
            async with database_sessions() as session, session.begin():
                await session.execute(
                    text("SELECT set_config('application_name', :name, false)"),
                    {"name": application_name},
                )
                await create_provider_account(
                    session,
                    ProviderAccountCreate(provider="gmail", external_account_id="race"),
                )
        except PersistenceConflict as error:
            return error
        return None

    first_task = asyncio.create_task(insert_first())
    competitor_task: asyncio.Task[PersistenceConflict | None] | None = None
    try:
        await asyncio.wait_for(first_inserted.wait(), timeout=10)
        competitor_task = asyncio.create_task(insert_competitor())
        await _wait_until_database_session_is_blocked(
            database_sessions, application_name
        )
    finally:
        release_first.set()
    await first_task
    assert competitor_task is not None
    competitor_result = await competitor_task

    assert isinstance(competitor_result, PersistenceConflict)
    async with database_sessions() as session:
        count = await session.scalar(
            text(
                "SELECT count(*) FROM provider_accounts "
                "WHERE provider = 'gmail' AND external_account_id = 'race'"
            )
        )
    assert count == 1


@pytest.mark.asyncio
async def test_concurrent_briefing_appends_lock_and_number_versions(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with database_sessions() as session, session.begin():
        briefing = await create_briefing(session, BriefingCreate(company_id=None))

    first_created = asyncio.Event()
    release_first = asyncio.Event()
    application_name = f"version-{uuid4().hex}"

    async def append_first() -> BriefingVersionRecord:
        async with database_sessions() as session, session.begin():
            version = await create_briefing_version(
                session,
                BriefingVersionCreate(
                    briefing_id=briefing.id, markdown="first", evidence_ids=[]
                ),
            )
            first_created.set()
            await release_first.wait()
            return version

    async def append_second() -> BriefingVersionRecord:
        async with database_sessions() as session, session.begin():
            await session.execute(
                text("SELECT set_config('application_name', :name, false)"),
                {"name": application_name},
            )
            return await create_briefing_version(
                session,
                BriefingVersionCreate(
                    briefing_id=briefing.id, markdown="second", evidence_ids=[]
                ),
            )

    first_task = asyncio.create_task(append_first())
    second_task: asyncio.Task[BriefingVersionRecord] | None = None
    try:
        await asyncio.wait_for(first_created.wait(), timeout=10)
        second_task = asyncio.create_task(append_second())
        await _wait_until_database_session_is_blocked(
            database_sessions, application_name
        )
    finally:
        release_first.set()
    first_version = await first_task
    assert second_task is not None
    second_version = await second_task

    assert {
        first_version.version_number,
        second_version.version_number,
    } == {1, 2}
    async with database_sessions() as session:
        rows = list(
            await session.scalars(
                text(
                    "SELECT version_number FROM briefing_versions "
                    "WHERE briefing_id = :briefing_id ORDER BY version_number"
                ),
                {"briefing_id": briefing.id},
            )
        )
    assert rows == [1, 2]


@pytest.mark.asyncio
async def test_citation_waits_for_locked_sealed_parent_then_is_rejected(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with database_sessions() as session, session.begin():
        evidence = await create_evidence(
            session,
            EvidenceCreate(
                kind=EvidenceKind.WEB,
                mail_message_id=None,
                meeting_id=None,
                source_url=_http_url("https://example.com/race-one"),
                source_text="source",
                retrieved_at=datetime(2026, 10, 25, 10, tzinfo=UTC),
            ),
        )
        other_evidence = await create_evidence(
            session,
            EvidenceCreate(
                kind=EvidenceKind.WEB,
                mail_message_id=None,
                meeting_id=None,
                source_url=_http_url("https://example.com/race-one-other"),
                source_text="other source",
                retrieved_at=datetime(2026, 10, 25, 11, tzinfo=UTC),
            ),
        )
        briefing = await create_briefing(session, BriefingCreate(company_id=None))
        version = await create_briefing_version(
            session,
            BriefingVersionCreate(
                briefing_id=briefing.id,
                markdown="sealed before competing citation",
                evidence_ids=[evidence.id],
            ),
        )

    lock_acquired = asyncio.Event()
    release_lock = asyncio.Event()
    application_name = f"citation-{uuid4().hex}"

    async def hold_parent_lock() -> None:
        async with database_sessions() as session, session.begin():
            await session.execute(
                text("SELECT id FROM briefing_versions WHERE id = :id FOR UPDATE"),
                {"id": version.id},
            )
            lock_acquired.set()
            await release_lock.wait()

    async def add_late_citation() -> str | None:
        try:
            async with database_sessions() as session, session.begin():
                await session.execute(
                    text("SELECT set_config('application_name', :name, false)"),
                    {"name": application_name},
                )
                await session.execute(
                    text(
                        "INSERT INTO briefing_version_evidence "
                        "(briefing_version_id, evidence_id) "
                        "VALUES (:version_id, :evidence_id)"
                    ),
                    {"version_id": version.id, "evidence_id": other_evidence.id},
                )
        except DBAPIError as error:
            return getattr(error.orig, "sqlstate", None)
        return None

    lock_task = asyncio.create_task(hold_parent_lock())
    citation_task: asyncio.Task[str | None] | None = None
    try:
        await asyncio.wait_for(lock_acquired.wait(), timeout=10)
        citation_task = asyncio.create_task(add_late_citation())
        await _wait_until_database_session_is_blocked(
            database_sessions, application_name
        )
    finally:
        release_lock.set()
    await lock_task
    assert citation_task is not None
    assert await citation_task == "P0001"

    async with database_sessions() as session:
        stored = await get_briefing_version(
            session, briefing.id, version.version_number
        )
    assert stored.sealed is True
    assert stored.evidence_ids == [evidence.id]


@pytest.mark.asyncio
async def test_evidence_and_citation_history_rejects_sql_mutation_and_truncate(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with database_sessions() as session, session.begin():
        first_evidence = await create_evidence(
            session,
            EvidenceCreate(
                kind=EvidenceKind.WEB,
                mail_message_id=None,
                meeting_id=None,
                source_url=_http_url("https://example.com/source"),
                source_text="original source",
                retrieved_at=datetime(2026, 10, 25, 10, tzinfo=UTC),
            ),
        )
        second_evidence = await create_evidence(
            session,
            EvidenceCreate(
                kind=EvidenceKind.WEB,
                mail_message_id=None,
                meeting_id=None,
                source_url=_http_url("https://example.com/other"),
                source_text="other source",
                retrieved_at=datetime(2026, 10, 25, 11, tzinfo=UTC),
            ),
        )
        briefing = await create_briefing(session, BriefingCreate(company_id=None))
        version = await create_briefing_version(
            session,
            BriefingVersionCreate(
                briefing_id=briefing.id,
                markdown="version one",
                evidence_ids=[first_evidence.id],
            ),
        )

    async def rejected(statement: str, params: dict[str, object] | None = None) -> None:
        with pytest.raises(DBAPIError) as error:
            async with database_sessions() as session, session.begin():
                await session.execute(text(statement), params or {})
        assert getattr(error.value.orig, "sqlstate", None) == "P0001"

    await rejected(
        "UPDATE evidence SET source_text = 'changed' WHERE id = :id",
        {"id": first_evidence.id},
    )
    await rejected("DELETE FROM evidence WHERE id = :id", {"id": first_evidence.id})
    await rejected(
        "INSERT INTO briefing_version_evidence (briefing_version_id, evidence_id) "
        "VALUES (:version_id, :evidence_id)",
        {"version_id": version.id, "evidence_id": second_evidence.id},
    )
    await rejected(
        "UPDATE briefing_version_evidence SET evidence_id = :replacement "
        "WHERE briefing_version_id = :version_id",
        {"replacement": second_evidence.id, "version_id": version.id},
    )
    await rejected(
        "DELETE FROM briefing_version_evidence WHERE briefing_version_id = :id",
        {"id": version.id},
    )
    await rejected("DELETE FROM briefing_versions WHERE id = :id", {"id": version.id})
    await rejected("TRUNCATE evidence CASCADE")
    await rejected("TRUNCATE briefing_versions CASCADE")
    await rejected("TRUNCATE briefing_version_evidence")
    await rejected("TRUNCATE briefings CASCADE")

    async with database_sessions() as session:
        stored_evidence = await get_evidence(session, first_evidence.id)
        stored_version = await get_briefing_version(
            session, briefing.id, version.version_number
        )
    assert stored_evidence.source_text == "original source"
    assert stored_version.evidence_ids == [first_evidence.id]
