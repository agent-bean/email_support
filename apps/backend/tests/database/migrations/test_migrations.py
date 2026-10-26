import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from email_support.storage.postgres.persistence.core import (
    get_briefing_version,
    get_company,
    get_contact,
    get_evidence,
    get_mail_message,
    get_meeting,
    get_provider_account,
)
from email_support.storage.postgres.persistence.database import (
    create_database_engine,
    dispose_database_engine,
)
from scripts.test_database import (
    DatabaseLifecycle,
    check_migration_drift,
    run_migrations,
)


@pytest.mark.asyncio
async def test_empty_database_installs_through_real_alembic_revision(
    database_engine: AsyncEngine,
    database_url: str,
) -> None:
    async with database_engine.connect() as connection:
        tables = await connection.run_sync(
            lambda sync_connection: set(inspect(sync_connection).get_table_names())
        )
        revision = await connection.scalar(
            text("SELECT version_num FROM alembic_version")
        )

    assert {
        "provider_accounts",
        "companies",
        "contacts",
        "mail_messages",
        "meetings",
        "evidence",
        "briefings",
        "briefing_versions",
        "briefing_version_evidence",
        "approvals",
        "actions",
        "knowledge",
        "knowledge_evidence",
        "preferences",
        "projection_metadata",
        "oauth_attempts",
        "owner_sessions",
        "google_connections",
    } <= tables
    assert revision == "3c0f6a9b21e8"
    await asyncio.to_thread(check_migration_drift, database_url)


@pytest.mark.asyncio
async def test_guarded_restore_recovers_revision_and_committed_core_rows(
    database_engine: AsyncEngine,
    database_url: str,
    database_lifecycle: DatabaseLifecycle,
) -> None:
    account_id = uuid4()
    source_database = database_url.rsplit("/", maxsplit=1)[-1]
    async with database_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO provider_accounts "
                "(id, provider, external_account_id) "
                "VALUES (:id, 'gmail', 'restore-account')"
            ),
            {"id": account_id},
        )

    archive = await asyncio.to_thread(
        database_lifecycle.backup_database,
        source_database,
        "restore-source",
    )
    restored_database = await asyncio.to_thread(
        database_lifecycle.restore_target,
        archive,
        "restore-verification",
    )
    restored_engine = create_database_engine(
        database_lifecycle.target_url(restored_database)
    )
    try:
        async with restored_engine.connect() as connection:
            restored_id = await connection.scalar(
                text(
                    "SELECT id FROM provider_accounts "
                    "WHERE provider = 'gmail' "
                    "AND external_account_id = 'restore-account'"
                )
            )
            revision = await connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
        with pytest.raises(DBAPIError) as duplicate_error:
            async with restored_engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO provider_accounts "
                        "(id, provider, external_account_id) "
                        "VALUES (:id, 'gmail', 'restore-account')"
                    ),
                    {"id": uuid4()},
                )
        assert getattr(duplicate_error.value.orig, "sqlstate", None) == "23505"
        assert restored_id == account_id
        assert revision == "3c0f6a9b21e8"
    finally:
        await dispose_database_engine(restored_engine)
        await asyncio.to_thread(database_lifecycle.drop_target, restored_database)


@pytest.mark.asyncio
async def test_additive_upgrade_preserves_seeded_first_revision_records(
    database_lifecycle: DatabaseLifecycle,
) -> None:
    database_name = database_lifecycle.create_target("upgrade-preservation")
    database_url = database_lifecycle.target_url(database_name)
    account_id = uuid4()
    company_id = uuid4()
    contact_id = uuid4()
    message_id = uuid4()
    meeting_id = uuid4()
    evidence_id = uuid4()
    briefing_id = uuid4()
    version_id = uuid4()
    received_at = datetime(2026, 10, 25, 10, tzinfo=UTC)
    row_snapshot_query = text(
        "SELECT 'provider_accounts'::text, to_jsonb(source) "
        "FROM provider_accounts AS source UNION ALL "
        "SELECT 'companies', to_jsonb(source) FROM companies AS source UNION ALL "
        "SELECT 'briefings', to_jsonb(source) FROM briefings AS source UNION ALL "
        "SELECT 'contacts', to_jsonb(source) FROM contacts AS source UNION ALL "
        "SELECT 'mail_messages', to_jsonb(source) "
        "FROM mail_messages AS source UNION ALL "
        "SELECT 'meetings', to_jsonb(source) FROM meetings AS source UNION ALL "
        "SELECT 'evidence', to_jsonb(source) FROM evidence AS source UNION ALL "
        "SELECT 'briefing_versions', to_jsonb(source) "
        "FROM briefing_versions AS source UNION ALL "
        "SELECT 'briefing_version_evidence', to_jsonb(source) "
        "FROM briefing_version_evidence AS source"
    )
    try:
        await asyncio.to_thread(run_migrations, database_url, "a31f5e702c84")
        await asyncio.to_thread(
            database_lifecycle.backup_database,
            database_name,
            "before-phase-1-seed",
        )
        seed_engine = create_database_engine(database_url)
        try:
            async with seed_engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO provider_accounts "
                        "(id, provider, external_account_id) "
                        "VALUES (:id, 'gmail', 'preserved-account')"
                    ),
                    {"id": account_id},
                )
                await connection.execute(
                    text(
                        "INSERT INTO companies (id, name, domain) "
                        "VALUES (:id, 'Preserved Company', NULL)"
                    ),
                    {"id": company_id},
                )
                await connection.execute(
                    text(
                        "INSERT INTO contacts "
                        "(id, company_id, email, display_name) "
                        "VALUES (:id, :company_id, 'Owner@Example.com', NULL)"
                    ),
                    {"id": contact_id, "company_id": company_id},
                )
                await connection.execute(
                    text(
                        "INSERT INTO mail_messages "
                        "(id, account_id, external_message_id, external_thread_id, "
                        "sender_email, recipient_emails, subject, body_text, "
                        "received_at, company_id, contact_id) VALUES "
                        "(:id, :account_id, 'message-1', NULL, 'owner@example.com', "
                        "NULL, NULL, NULL, :received_at, :company_id, :contact_id)"
                    ),
                    {
                        "id": message_id,
                        "account_id": account_id,
                        "received_at": received_at,
                        "company_id": company_id,
                        "contact_id": contact_id,
                    },
                )
                await connection.execute(
                    text(
                        "INSERT INTO meetings "
                        "(id, account_id, external_calendar_id, external_event_id, "
                        "title, description, organizer_email, attendee_emails, "
                        "time_kind, starts_at, ends_at, start_date, end_date, "
                        "company_id) "
                        "VALUES (:id, :account_id, 'primary', 'event-1', 'Planning', "
                        "NULL, NULL, '[]'::jsonb, 'timed', :starts_at, :ends_at, "
                        "NULL, NULL, :company_id)"
                    ),
                    {
                        "id": meeting_id,
                        "account_id": account_id,
                        "starts_at": received_at,
                        "ends_at": datetime(2026, 10, 25, 11, tzinfo=UTC),
                        "company_id": company_id,
                    },
                )
                await connection.execute(
                    text(
                        "INSERT INTO evidence "
                        "(id, kind, mail_message_id, meeting_id, source_url, "
                        "source_text, retrieved_at) VALUES "
                        "(:id, 'mail', :message_id, NULL, NULL, 'Original source', "
                        ":retrieved_at)"
                    ),
                    {
                        "id": evidence_id,
                        "message_id": message_id,
                        "retrieved_at": received_at,
                    },
                )
                await connection.execute(
                    text(
                        "INSERT INTO briefings (id, company_id) "
                        "VALUES (:id, :company_id)"
                    ),
                    {"id": briefing_id, "company_id": company_id},
                )
                await connection.execute(
                    text(
                        "INSERT INTO briefing_versions "
                        "(id, briefing_id, version_number, markdown, sealed) "
                        "VALUES (:id, :briefing_id, 7, :markdown, false)"
                    ),
                    {
                        "id": version_id,
                        "briefing_id": briefing_id,
                        "markdown": "# Preserved\n\nContent",
                    },
                )
                await connection.execute(
                    text(
                        "INSERT INTO briefing_version_evidence "
                        "(briefing_version_id, evidence_id) "
                        "VALUES (:version_id, :evidence_id)"
                    ),
                    {"version_id": version_id, "evidence_id": evidence_id},
                )
                await connection.execute(
                    text("UPDATE briefing_versions SET sealed = true WHERE id = :id"),
                    {"id": version_id},
                )
                before_rows = sorted(
                    (table_name, json.dumps(row_data, sort_keys=True))
                    for table_name, row_data in (
                        await connection.execute(row_snapshot_query)
                    )
                )
        finally:
            await dispose_database_engine(seed_engine)

        await asyncio.to_thread(
            database_lifecycle.backup_database,
            database_name,
            "before-additive-upgrade",
        )
        await asyncio.to_thread(run_migrations, database_url)

        upgraded_engine = create_database_engine(database_url)
        try:
            async with upgraded_engine.connect() as connection:
                revision = await connection.scalar(
                    text("SELECT version_num FROM alembic_version")
                )
                preserved_email = await connection.scalar(
                    text("SELECT email FROM contacts WHERE id = :id"),
                    {"id": contact_id},
                )
                after_rows = sorted(
                    (table_name, json.dumps(row_data, sort_keys=True))
                    for table_name, row_data in (
                        await connection.execute(row_snapshot_query)
                    )
                )
            sessions = async_sessionmaker(
                bind=upgraded_engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            async with sessions() as session:
                account = await get_provider_account(session, account_id)
                company = await get_company(session, company_id)
                contact = await get_contact(session, contact_id)
                message = await get_mail_message(session, message_id)
                meeting = await get_meeting(session, meeting_id)
                evidence = await get_evidence(session, evidence_id)
                version = await get_briefing_version(session, briefing_id, 7)
        finally:
            await dispose_database_engine(upgraded_engine)

        assert revision == "3c0f6a9b21e8"
        assert preserved_email == "Owner@Example.com"
        assert after_rows == before_rows
        assert account.id == account_id
        assert company.id == company_id and company.domain is None
        assert contact.id == contact_id and contact.display_name is None
        assert message.id == message_id
        assert message.recipient_emails is None
        assert message.subject is None and message.body_text is None
        assert message.received_at == received_at
        assert meeting.id == meeting_id
        assert meeting.attendee_emails == []
        assert evidence.id == evidence_id and evidence.source_text == "Original source"
        assert version.id == version_id
        assert version.markdown == "# Preserved\n\nContent"
        assert version.evidence_ids == [evidence_id]
    finally:
        await asyncio.to_thread(database_lifecycle.drop_target, database_name)


@pytest.mark.asyncio
async def test_owner_access_migration_preserves_existing_decision_and_knowledge_rows(
    database_lifecycle: DatabaseLifecycle,
) -> None:
    database_name = database_lifecycle.create_target("access-upgrade-preservation")
    database_url = database_lifecycle.target_url(database_name)
    company_id, briefing_id, version_id = uuid4(), uuid4(), uuid4()
    approval_id, knowledge_id, preference_id = uuid4(), uuid4(), uuid4()
    snapshot_query = text(
        "SELECT 'approvals'::text, to_jsonb(source) FROM approvals AS source "
        "UNION ALL SELECT 'knowledge', to_jsonb(source) FROM knowledge AS source "
        "UNION ALL SELECT 'preferences', to_jsonb(preferences) FROM preferences"
    )
    try:
        await asyncio.to_thread(run_migrations, database_url, "da3c8e14f627")
        await asyncio.to_thread(
            database_lifecycle.backup_database,
            database_name,
            "before-access-preservation-seed",
        )
        engine = create_database_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text("INSERT INTO companies (id, name) VALUES (:id, 'Kept Co')"),
                    {"id": company_id},
                )
                await connection.execute(
                    text(
                        "INSERT INTO briefings (id, company_id) "
                        "VALUES (:id, :company_id)"
                    ),
                    {"id": briefing_id, "company_id": company_id},
                )
                await connection.execute(
                    text(
                        "INSERT INTO briefing_versions "
                        "(id, briefing_id, version_number, markdown, sealed) "
                        "VALUES (:id, :briefing_id, 1, 'Kept', true)"
                    ),
                    {"id": version_id, "briefing_id": briefing_id},
                )
                await connection.execute(
                    text(
                        "INSERT INTO approvals "
                        "(id, briefing_id, briefing_version_id, action_kind, "
                        "recipient_emails, selected_knowledge) VALUES "
                        "(:id, :briefing_id, :version_id, 'save_knowledge', "
                        "'[]'::jsonb, '[\"kept note\"]'::jsonb)"
                    ),
                    {
                        "id": approval_id,
                        "briefing_id": briefing_id,
                        "version_id": version_id,
                    },
                )
                await connection.execute(
                    text(
                        "INSERT INTO knowledge "
                        "(id, company_id, approval_id, selection_index, "
                        "briefing_version_id, sealed) VALUES "
                        "(:id, :company_id, :approval_id, 0, :version_id, false)"
                    ),
                    {
                        "id": knowledge_id,
                        "company_id": company_id,
                        "approval_id": approval_id,
                        "version_id": version_id,
                    },
                )
                await connection.execute(
                    text("UPDATE knowledge SET sealed = true WHERE id = :id"),
                    {"id": knowledge_id},
                )
                await connection.execute(
                    text(
                        "INSERT INTO preferences (id, key, value) "
                        "VALUES (:id, 'reply_tone', '\"clear\"'::jsonb)"
                    ),
                    {"id": preference_id},
                )
                before_rows = sorted(
                    (name, json.dumps(row, sort_keys=True))
                    for name, row in await connection.execute(snapshot_query)
                )
        finally:
            await dispose_database_engine(engine)

        await asyncio.to_thread(
            database_lifecycle.backup_database,
            database_name,
            "before-owner-access-upgrade",
        )
        await asyncio.to_thread(run_migrations, database_url)
        upgraded_engine = create_database_engine(database_url)
        try:
            async with upgraded_engine.connect() as connection:
                after_rows = sorted(
                    (name, json.dumps(row, sort_keys=True))
                    for name, row in await connection.execute(snapshot_query)
                )
                revision = await connection.scalar(
                    text("SELECT version_num FROM alembic_version")
                )
        finally:
            await dispose_database_engine(upgraded_engine)

        assert after_rows == before_rows
        assert revision == "3c0f6a9b21e8"
    finally:
        await asyncio.to_thread(database_lifecycle.drop_target, database_name)


@pytest.mark.asyncio
async def test_google_connection_upgrade_preserves_owner_session_and_canonical_account(
    database_lifecycle: DatabaseLifecycle,
) -> None:
    database_name = database_lifecycle.create_target("google-upgrade-preservation")
    database_url = database_lifecycle.target_url(database_name)
    account_id = uuid4()
    token_digest = b"s" * 32
    created_at = datetime(2026, 10, 26, 10, tzinfo=UTC)
    expires_at = datetime(2026, 10, 27, 10, tzinfo=UTC)
    try:
        await asyncio.to_thread(run_migrations, database_url, "b17e9a4d2c61")
        engine = create_database_engine(database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO provider_accounts "
                        "(id, provider, external_account_id) "
                        "VALUES (:id, 'gmail', 'kept-google-account')"
                    ),
                    {"id": account_id},
                )
                await connection.execute(
                    text(
                        "INSERT INTO owner_sessions "
                        "(token_digest, owner_sub, created_at, expires_at, "
                        "csrf_secret) VALUES (:digest, 'configured-owner', "
                        ":created, :expires, 'kept-csrf')"
                    ),
                    {
                        "digest": token_digest,
                        "created": created_at,
                        "expires": expires_at,
                    },
                )
        finally:
            await dispose_database_engine(engine)

        await asyncio.to_thread(
            database_lifecycle.backup_database,
            database_name,
            "before-google-connection-upgrade",
        )
        await asyncio.to_thread(run_migrations, database_url)

        upgraded_engine = create_database_engine(database_url)
        try:
            async with upgraded_engine.connect() as connection:
                revision = await connection.scalar(
                    text("SELECT version_num FROM alembic_version")
                )
                session = (
                    await connection.execute(
                        text(
                            "SELECT token_digest, owner_sub, created_at, expires_at, "
                            "csrf_secret FROM owner_sessions "
                            "WHERE token_digest = :digest"
                        ),
                        {"digest": token_digest},
                    )
                ).one()
                account = (
                    await connection.execute(
                        text(
                            "SELECT provider, external_account_id "
                            "FROM provider_accounts "
                            "WHERE id = :id"
                        ),
                        {"id": account_id},
                    )
                ).one()
                connection_count = await connection.scalar(
                    text("SELECT count(*) FROM google_connections")
                )
        finally:
            await dispose_database_engine(upgraded_engine)

        assert revision == "3c0f6a9b21e8"
        assert tuple(session) == (
            token_digest,
            "configured-owner",
            created_at,
            expires_at,
            "kept-csrf",
        )
        assert tuple(account) == ("gmail", "kept-google-account")
        assert connection_count == 0
    finally:
        await asyncio.to_thread(database_lifecycle.drop_target, database_name)
