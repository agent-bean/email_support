from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from email_support.models.persistence import (
    ActionKind,
    ApprovalCreate,
    BriefingVersionCreate,
    PreferenceCreate,
)
from email_support.storage.postgres.persistence.core import (
    PersistenceConflict,
    create_briefing_version,
)
from email_support.storage.postgres.persistence.decisions import (
    get_action,
    get_approval,
    get_preference,
    record_approval_and_action,
    set_preference,
)
from tests.database.support import CanonicalSource


def _approval(source: CanonicalSource) -> ApprovalCreate:
    return ApprovalCreate(
        briefing_id=source.briefing.id,
        briefing_version_id=source.version.id,
        action_kind=ActionKind.SAVE_KNOWLEDGE,
        recipient_emails=[],
        selected_knowledge=["  Exact approved text.\nKeep spacing.  "],
    )


@pytest.mark.asyncio
async def test_approval_and_action_commit_as_one_exact_historical_binding(
    database_sessions: async_sessionmaker[AsyncSession],
    canonical_source: CanonicalSource,
) -> None:
    async with database_sessions() as session, session.begin():
        approval, action = await record_approval_and_action(
            session, _approval(canonical_source)
        )
        newer_version = await create_briefing_version(
            session,
            BriefingVersionCreate(
                briefing_id=canonical_source.briefing.id,
                markdown="# Newer briefing content",
                evidence_ids=[canonical_source.evidence.id],
            ),
        )
        assert newer_version.id != approval.briefing_version_id

    async with database_sessions() as independent_session:
        stored_approval = await get_approval(independent_session, approval.id)
        stored_action = await get_action(independent_session, approval.id)

    assert stored_approval == approval
    assert stored_action == action
    assert stored_approval.selected_knowledge == [
        "  Exact approved text.\nKeep spacing.  "
    ]


@pytest.mark.asyncio
async def test_caller_rollback_removes_approval_and_action(
    database_sessions: async_sessionmaker[AsyncSession],
    canonical_source: CanonicalSource,
) -> None:
    with pytest.raises(RuntimeError, match="caller rollback"):
        async with database_sessions() as session, session.begin():
            await record_approval_and_action(session, _approval(canonical_source))
            raise RuntimeError("caller rollback")

    async with database_sessions() as session:
        assert await session.scalar(text("SELECT count(*) FROM approvals")) == 0
        assert await session.scalar(text("SELECT count(*) FROM actions")) == 0


@pytest.mark.asyncio
async def test_action_insert_failure_rolls_back_the_previously_flushed_approval(
    database_sessions: async_sessionmaker[AsyncSession],
    canonical_source: CanonicalSource,
) -> None:
    with pytest.raises(PersistenceConflict):
        async with database_sessions() as session, session.begin():
            await session.execute(
                text(
                    "CREATE FUNCTION reject_test_action() RETURNS trigger "
                    "LANGUAGE plpgsql AS $$ BEGIN "
                    "RAISE EXCEPTION 'forced action insert failure'; END $$"
                )
            )
            await session.execute(
                text(
                    "CREATE TRIGGER reject_test_action_before_insert "
                    "BEFORE INSERT ON actions FOR EACH ROW "
                    "EXECUTE FUNCTION reject_test_action()"
                )
            )
            await record_approval_and_action(session, _approval(canonical_source))

    async with database_sessions() as session:
        assert await session.scalar(text("SELECT count(*) FROM approvals")) == 0
        assert await session.scalar(text("SELECT count(*) FROM actions")) == 0


@pytest.mark.asyncio
async def test_approval_requires_an_existing_version_from_the_same_briefing(
    database_sessions: async_sessionmaker[AsyncSession],
    canonical_source: CanonicalSource,
) -> None:
    for briefing_id, version_id in (
        (canonical_source.briefing.id, canonical_source.version.id),
        (canonical_source.version.id, canonical_source.version.id),
        (canonical_source.briefing.id, canonical_source.briefing.id),
    ):
        if (
            briefing_id == canonical_source.briefing.id
            and version_id == canonical_source.version.id
        ):
            continue
        with pytest.raises(PersistenceConflict):
            async with database_sessions() as session, session.begin():
                await record_approval_and_action(
                    session,
                    ApprovalCreate(
                        briefing_id=briefing_id,
                        briefing_version_id=version_id,
                        action_kind=ActionKind.SAVE_KNOWLEDGE,
                        recipient_emails=[],
                        selected_knowledge=["Selected text"],
                    ),
                )

    async with database_sessions() as session:
        assert await session.scalar(text("SELECT count(*) FROM approvals")) == 0


@pytest.mark.asyncio
async def test_explicit_json_null_preference_is_persisted_as_json_not_sql_null(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with database_sessions() as session, session.begin():
        created = await set_preference(
            session, PreferenceCreate(key="response_style", value=None)
        )

    async with database_sessions() as session:
        stored = await get_preference(session, "response_style")
        json_kind = await session.scalar(
            text("SELECT jsonb_typeof(value) FROM preferences WHERE key = :key"),
            {"key": "response_style"},
        )

    assert stored == created
    assert stored.value is None
    assert json_kind == "null"

    async with database_sessions() as session, session.begin():
        updated = await set_preference(
            session,
            PreferenceCreate(key="response_style", value={"tone": "concise"}),
        )
    assert updated.id == created.id
    assert updated.value == {"tone": "concise"}


@pytest.mark.asyncio
async def test_approval_action_bindings_reject_sql_mutation_and_truncate(
    database_sessions: async_sessionmaker[AsyncSession],
    canonical_source: CanonicalSource,
) -> None:
    async with database_sessions() as session, session.begin():
        approval, action = await record_approval_and_action(
            session, _approval(canonical_source)
        )

    for statement, params in (
        (
            "UPDATE approvals SET briefing_version_id = :version_id WHERE id = :id",
            {"version_id": canonical_source.version.id, "id": approval.id},
        ),
        ("DELETE FROM actions WHERE id = :id", {"id": action.id}),
        ("TRUNCATE actions", {}),
        ("TRUNCATE approvals CASCADE", {}),
    ):
        with pytest.raises(DBAPIError) as error:
            async with database_sessions() as session, session.begin():
                await session.execute(text(statement), params)
        assert getattr(error.value.orig, "sqlstate", None) == "P0001"

    with pytest.raises(DBAPIError) as duplicate_error:
        async with database_sessions() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO actions (id, approval_id) VALUES (:id, :approval_id)"
                ),
                {"id": uuid4(), "approval_id": approval.id},
            )
    assert getattr(duplicate_error.value.orig, "sqlstate", None) == "23505"

    async with database_sessions() as session:
        assert (await get_approval(session, approval.id)) == approval
        assert (await get_action(session, approval.id)) == action


@pytest.mark.asyncio
async def test_direct_sql_rejects_noncanonical_approval_arrays(
    database_sessions: async_sessionmaker[AsyncSession],
    canonical_source: CanonicalSource,
) -> None:
    recipient_arrays = (
        '["z@example.com", "a@example.com"]',
        '["owner@example.com", "owner@example.com"]',
        '["Owner@EXAMPLE.com"]',
        '["owner @example.com"]',
    )
    for recipients in recipient_arrays:
        with pytest.raises(DBAPIError) as error:
            async with database_sessions() as session, session.begin():
                await session.execute(
                    text(
                        "INSERT INTO approvals "
                        "(id, briefing_id, briefing_version_id, action_kind, "
                        "recipient_emails, selected_knowledge) VALUES "
                        "(:id, :briefing_id, :version_id, 'send_email', "
                        "CAST(:recipients AS jsonb), '[]'::jsonb)"
                    ),
                    {
                        "id": uuid4(),
                        "briefing_id": canonical_source.briefing.id,
                        "version_id": canonical_source.version.id,
                        "recipients": recipients,
                    },
                )
        assert getattr(error.value.orig, "sqlstate", None) == "P0001"

    for selected in ('["   "]', '["\\t\\n"]'):
        with pytest.raises(DBAPIError) as error:
            async with database_sessions() as session, session.begin():
                await session.execute(
                    text(
                        "INSERT INTO approvals "
                        "(id, briefing_id, briefing_version_id, action_kind, "
                        "recipient_emails, selected_knowledge) VALUES "
                        "(:id, :briefing_id, :version_id, 'save_knowledge', "
                        "'[]'::jsonb, CAST(:selected AS jsonb))"
                    ),
                    {
                        "id": uuid4(),
                        "briefing_id": canonical_source.briefing.id,
                        "version_id": canonical_source.version.id,
                        "selected": selected,
                    },
                )
        assert getattr(error.value.orig, "sqlstate", None) == "P0001"
