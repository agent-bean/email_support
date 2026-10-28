import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from email_support.models.email_interpretation import (
    InputOriginKind,
    MeetingState,
    NormalizedEmailInput,
    NormalizedInputCreate,
)
from email_support.models.persistence import CompanyCreate, ContactCreate
from email_support.models.persistence.briefing_runs import BriefingRunCreate
from email_support.storage.postgres.persistence.briefing_runs import (
    begin_run,
    bind_briefing,
    complete_attempt,
    reserve_attempt,
    resolve_run,
)
from email_support.storage.postgres.persistence.core import (
    PersistenceConflict,
    create_company,
    create_contact,
)
from email_support.storage.postgres.persistence.identity import create_normalized_input
from email_support.storage.postgres.persistence.tables import (
    BriefingVersionRow,
    ContactRow,
)


@pytest.mark.asyncio
async def test_binding_is_idempotent_and_stale_identity_fails(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with database_sessions() as session, session.begin():
        company = await create_company(
            session, CompanyCreate(name="Test company", domain="example.com")
        )
        contact = await create_contact(
            session,
            ContactCreate(
                email="owner@example.com", company_id=company.id, display_name=None
            ),
        )
        source = await create_normalized_input(
            session,
            NormalizedInputCreate(
                origin_kind=InputOriginKind.EVALUATION,
                origin_key=str(uuid4()),
                payload=NormalizedEmailInput(
                    sender_email="owner@example.com",
                    sender_display_name=None,
                    subject="Topic",
                    body="Discuss topic",
                    received_at=datetime.now(UTC),
                    meeting_state=MeetingState.ABSENT,
                    meeting=None,
                ),
            ),
        )
        request = BriefingRunCreate(
            id=uuid4(),
            input_id=source.id,
            company_id=company.id,
            contact_id=contact.id,
            identity_revision=contact.identity_revision,
            input_hash=source.content_hash,
            config_hash="a" * 64,
            dependencies=(),
        )
        await begin_run(
            session, request.id, source.id, source.content_hash, request.config_hash
        )
        attempt_id = uuid4()
        await reserve_attempt(session, request.id, attempt_id, 1, "research")
    async with database_sessions() as session, session.begin():
        stored = await resolve_run(session, request)
        assert stored.attempts[0]["outcome"] == "unknown"
        with pytest.raises(PersistenceConflict, match="budget"):
            await reserve_attempt(session, request.id, uuid4(), 1, "research")
        await complete_attempt(session, request.id, attempt_id, "succeeded", None)
        first = await bind_briefing(session, request.id, "# Draft", [])
        version_id = first.briefing_version_id
        again = await bind_briefing(session, request.id, "# Different", [])
        assert again.briefing_version_id == version_id
        assert (
            await session.scalar(select(func.count()).select_from(BriefingVersionRow))
            == 1
        )
    async with database_sessions() as session, session.begin():
        row = await session.get(ContactRow, contact.id)
        assert row is not None
        row.identity_revision += 1
    async with database_sessions() as session, session.begin():
        with pytest.raises(PersistenceConflict, match="stale"):
            await bind_briefing(session, request.id, "# Draft", [])


@pytest.mark.asyncio
async def test_invalidated_knowledge_blocks_binding_and_marks_existing_binding_stale(
    database_sessions: async_sessionmaker[AsyncSession],
    canonical_source: object,
) -> None:
    from email_support.models.persistence import (
        ActionKind,
        ApprovalCreate,
        KnowledgeCreate,
    )
    from email_support.models.persistence.briefing_runs import KnowledgeDependency
    from email_support.storage.postgres.persistence.briefing_runs import current_run
    from email_support.storage.postgres.persistence.decisions import (
        create_knowledge,
        invalidate_knowledge,
        record_approval_and_action,
    )
    from tests.database.support import CanonicalSource

    assert isinstance(canonical_source, CanonicalSource)
    invalidation_started = asyncio.Event()

    async def invalidate_concurrently() -> None:
        async with database_sessions() as other, other.begin():
            invalidation_started.set()
            await invalidate_knowledge(other, knowledge.id)

    async with database_sessions() as session, session.begin():
        approval, _ = await record_approval_and_action(
            session,
            ApprovalCreate(
                briefing_id=canonical_source.briefing.id,
                briefing_version_id=canonical_source.version.id,
                action_kind=ActionKind.SAVE_KNOWLEDGE,
                recipient_emails=[],
                selected_knowledge=["Previously approved context"],
            ),
        )
        knowledge = await create_knowledge(
            session,
            KnowledgeCreate(
                approval_id=approval.id,
                selection_index=0,
                evidence_ids=[canonical_source.evidence.id],
            ),
        )
        contact = await create_contact(
            session,
            ContactCreate(
                email="history@example.com",
                company_id=canonical_source.company.id,
                display_name=None,
            ),
        )
        source = await create_normalized_input(
            session,
            NormalizedInputCreate(
                origin_kind=InputOriginKind.EVALUATION,
                origin_key=str(uuid4()),
                payload=NormalizedEmailInput(
                    sender_email="history@example.com",
                    sender_display_name=None,
                    subject="Topic",
                    body="Discuss topic",
                    received_at=datetime.now(UTC),
                    meeting_state=MeetingState.ABSENT,
                    meeting=None,
                ),
            ),
        )
        dependencies = (
            KnowledgeDependency(
                knowledge_id=knowledge.id,
                briefing_version_id=knowledge.briefing_version_id,
                approval_id=knowledge.approval_id,
            ),
        )
        requests = [
            BriefingRunCreate(
                id=uuid4(),
                input_id=source.id,
                company_id=canonical_source.company.id,
                contact_id=contact.id,
                identity_revision=contact.identity_revision,
                input_hash=source.content_hash,
                config_hash="b" * 64,
                dependencies=dependencies,
            )
            for _ in range(2)
        ]
        for request in requests:
            await begin_run(
                session, request.id, source.id, source.content_hash, request.config_hash
            )
            await resolve_run(session, request)
    async with database_sessions() as session, session.begin():
        bound = await bind_briefing(session, requests[0].id, "# Historical", [])
        version_id = bound.briefing_version_id
        invalidation = asyncio.create_task(invalidate_concurrently())
        await invalidation_started.wait()
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(invalidation), timeout=0.2)
    await invalidation
    async with database_sessions() as session, session.begin():
        with pytest.raises(PersistenceConflict, match="knowledge dependency"):
            await bind_briefing(session, requests[1].id, "# Must not bind", [])
        with pytest.raises(PersistenceConflict, match="knowledge dependency"):
            await current_run(session, requests[0].id)
        assert await session.get(BriefingVersionRow, version_id) is not None


@pytest.mark.asyncio
async def test_stopped_run_keeps_explicit_reason(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    from email_support.storage.postgres.persistence.briefing_runs import stop_run
    from email_support.storage.postgres.persistence.tables import BriefingRunRow

    run_id = uuid4()
    async with database_sessions() as session, session.begin():
        source = await create_normalized_input(
            session,
            NormalizedInputCreate(
                origin_kind=InputOriginKind.EVALUATION,
                origin_key=str(run_id),
                payload=NormalizedEmailInput(
                    sender_email=None,
                    sender_display_name=None,
                    subject="Unknown",
                    body="Hello",
                    received_at=datetime.now(UTC),
                    meeting_state=MeetingState.ABSENT,
                    meeting=None,
                ),
            ),
        )
        await begin_run(session, run_id, source.id, source.content_hash, "c" * 64)
        await stop_run(session, run_id, "uncertain")
    async with database_sessions() as session:
        row = await session.get(BriefingRunRow, run_id)
        assert (
            row is not None
            and row.status == "stopped"
            and row.stop_reason == "uncertain"
        )
