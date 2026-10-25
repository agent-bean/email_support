import asyncio
from uuid import uuid4

import pytest
from pydantic import AnyHttpUrl, TypeAdapter
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from email_support.models.persistence import (
    ActionKind,
    ApprovalCreate,
    BriefingCreate,
    BriefingVersionCreate,
    EvidenceCreate,
    EvidenceKind,
    KnowledgeCreate,
)
from email_support.storage.postgres.core import (
    PersistenceConflict,
    create_briefing,
    create_briefing_version,
    create_evidence,
)
from email_support.storage.postgres.decisions import (
    create_knowledge,
    get_knowledge,
    invalidate_knowledge,
    list_eligible_knowledge,
    record_approval_and_action,
)
from tests.database.support import CanonicalSource

HTTP_URL_ADAPTER: TypeAdapter[AnyHttpUrl] = TypeAdapter(AnyHttpUrl)


def _knowledge_approval(source: CanonicalSource) -> ApprovalCreate:
    return ApprovalCreate(
        briefing_id=source.briefing.id,
        briefing_version_id=source.version.id,
        action_kind=ActionKind.SAVE_KNOWLEDGE,
        recipient_emails=[],
        selected_knowledge=["  Exact approved text.\nKeep spacing.  "],
    )


@pytest.mark.asyncio
async def test_knowledge_reads_exact_approved_entry_and_invalidation_is_immediate(
    database_sessions: async_sessionmaker[AsyncSession],
    canonical_source: CanonicalSource,
) -> None:
    async with database_sessions() as session, session.begin():
        approval, _ = await record_approval_and_action(
            session, _knowledge_approval(canonical_source)
        )
        knowledge = await create_knowledge(
            session,
            KnowledgeCreate(
                approval_id=approval.id,
                selection_index=0,
                evidence_ids=[canonical_source.evidence.id],
            ),
        )

    async with database_sessions() as session:
        stored = await get_knowledge(session, knowledge.id)
        eligible_before = await list_eligible_knowledge(session)
    assert stored.content == "  Exact approved text.\nKeep spacing.  "
    assert stored.company_id == canonical_source.company.id
    assert stored.briefing_version_id == canonical_source.version.id
    assert stored.evidence_ids == [canonical_source.evidence.id]
    assert [item.id for item in eligible_before] == [knowledge.id]

    async with database_sessions() as session, session.begin():
        invalidated = await invalidate_knowledge(session, knowledge.id)
        assert invalidated.invalidated_at is not None

    async with database_sessions() as session:
        eligible_after = await list_eligible_knowledge(session)
        stored_after = await get_knowledge(session, knowledge.id)
    assert eligible_after == []
    assert stored_after.content == stored.content
    assert stored_after.invalidated_at is not None


@pytest.mark.asyncio
async def test_knowledge_rejects_bad_selection_and_evidence_from_another_version(
    database_sessions: async_sessionmaker[AsyncSession],
    canonical_source: CanonicalSource,
) -> None:
    async with database_sessions() as session, session.begin():
        approval, _ = await record_approval_and_action(
            session, _knowledge_approval(canonical_source)
        )
        other_evidence = await create_evidence(
            session,
            EvidenceCreate(
                kind=EvidenceKind.WEB,
                mail_message_id=None,
                meeting_id=None,
                source_url=HTTP_URL_ADAPTER.validate_python(
                    "https://example.org/other"
                ),
                source_text="Other version source.",
                retrieved_at=canonical_source.version.created_at,
            ),
        )
        other_briefing = await create_briefing(session, BriefingCreate(company_id=None))
        await create_briefing_version(
            session,
            BriefingVersionCreate(
                briefing_id=other_briefing.id,
                markdown="# Unrelated source",
                evidence_ids=[other_evidence.id],
            ),
        )
    async with database_sessions() as session, session.begin():
        send_approval, _ = await record_approval_and_action(
            session,
            ApprovalCreate(
                briefing_id=canonical_source.briefing.id,
                briefing_version_id=canonical_source.version.id,
                action_kind=ActionKind.SEND_EMAIL,
                recipient_emails=["owner@example.com"],
                selected_knowledge=[],
            ),
        )

    with pytest.raises(PersistenceConflict):
        async with database_sessions() as session, session.begin():
            await create_knowledge(
                session,
                KnowledgeCreate(
                    approval_id=approval.id, selection_index=5, evidence_ids=[]
                ),
            )

    with pytest.raises(PersistenceConflict):
        async with database_sessions() as session, session.begin():
            await create_knowledge(
                session,
                KnowledgeCreate(
                    approval_id=approval.id,
                    selection_index=0,
                    evidence_ids=[other_evidence.id],
                ),
            )

    with pytest.raises(PersistenceConflict):
        async with database_sessions() as session, session.begin():
            await create_knowledge(
                session,
                KnowledgeCreate(
                    approval_id=send_approval.id, selection_index=0, evidence_ids=[]
                ),
            )

    for approval_id, selection_index in (
        (approval.id, 5),
        (send_approval.id, 0),
    ):
        with pytest.raises(DBAPIError) as error:
            async with database_sessions() as session, session.begin():
                await session.execute(
                    text(
                        "INSERT INTO knowledge "
                        "(id, company_id, approval_id, selection_index, "
                        "briefing_version_id) VALUES "
                        "(:id, :company_id, :approval_id, "
                        ":selection_index, :version_id)"
                    ),
                    {
                        "id": uuid4(),
                        "company_id": canonical_source.company.id,
                        "approval_id": approval_id,
                        "selection_index": selection_index,
                        "version_id": canonical_source.version.id,
                    },
                )
        assert getattr(error.value.orig, "sqlstate", None) == "P0001"

    async with database_sessions() as session:
        assert await session.scalar(text("SELECT count(*) FROM knowledge")) == 0

    async with database_sessions() as session, session.begin():
        await create_knowledge(
            session,
            KnowledgeCreate(
                approval_id=approval.id,
                selection_index=0,
                evidence_ids=[canonical_source.evidence.id],
            ),
        )
    with pytest.raises(PersistenceConflict):
        async with database_sessions() as session, session.begin():
            await create_knowledge(
                session,
                KnowledgeCreate(
                    approval_id=approval.id,
                    selection_index=0,
                    evidence_ids=[canonical_source.evidence.id],
                ),
            )
    async with database_sessions() as session:
        assert await session.scalar(text("SELECT count(*) FROM knowledge")) == 1


@pytest.mark.asyncio
async def test_knowledge_and_citations_reject_mutation_delete_and_truncate(
    database_sessions: async_sessionmaker[AsyncSession],
    canonical_source: CanonicalSource,
) -> None:
    async with database_sessions() as session, session.begin():
        approval, _ = await record_approval_and_action(
            session, _knowledge_approval(canonical_source)
        )
        knowledge = await create_knowledge(
            session,
            KnowledgeCreate(
                approval_id=approval.id,
                selection_index=0,
                evidence_ids=[canonical_source.evidence.id],
            ),
        )

    attempts: tuple[tuple[str, dict[str, object]], ...] = (
        (
            "UPDATE knowledge SET selection_index = 9 WHERE id = :id",
            {"id": knowledge.id},
        ),
        ("DELETE FROM knowledge WHERE id = :id", {"id": knowledge.id}),
        (
            "DELETE FROM knowledge_evidence WHERE knowledge_id = :id",
            {"id": knowledge.id},
        ),
        ("TRUNCATE knowledge_evidence", {}),
        ("TRUNCATE knowledge CASCADE", {}),
    )
    for statement, params in attempts:
        with pytest.raises(DBAPIError) as error:
            async with database_sessions() as session, session.begin():
                await session.execute(text(statement), params)
        assert getattr(error.value.orig, "sqlstate", None) == "P0001"

    async with database_sessions() as session:
        stored = await get_knowledge(session, knowledge.id)
    assert stored.content == "  Exact approved text.\nKeep spacing.  "
    assert stored.evidence_ids == [canonical_source.evidence.id]


@pytest.mark.asyncio
async def test_late_knowledge_citation_waits_for_sealed_parent_then_is_rejected(
    database_sessions: async_sessionmaker[AsyncSession],
    canonical_source: CanonicalSource,
) -> None:
    async with database_sessions() as session, session.begin():
        approval, _ = await record_approval_and_action(
            session, _knowledge_approval(canonical_source)
        )
        knowledge = await create_knowledge(
            session,
            KnowledgeCreate(
                approval_id=approval.id,
                selection_index=0,
                evidence_ids=[canonical_source.evidence.id],
            ),
        )

    acquired = asyncio.Event()
    release = asyncio.Event()
    application_name = f"knowledge-citation-{uuid4().hex}"

    async def hold_parent_lock() -> None:
        async with database_sessions() as session, session.begin():
            await session.execute(
                text("SELECT id FROM knowledge WHERE id = :id FOR UPDATE"),
                {"id": knowledge.id},
            )
            acquired.set()
            await release.wait()

    async def insert_late_citation() -> str | None:
        try:
            async with database_sessions() as session, session.begin():
                await session.execute(
                    text("SELECT set_config('application_name', :name, false)"),
                    {"name": application_name},
                )
                await session.execute(
                    text(
                        "INSERT INTO knowledge_evidence (knowledge_id, evidence_id) "
                        "VALUES (:knowledge_id, :evidence_id)"
                    ),
                    {
                        "knowledge_id": knowledge.id,
                        "evidence_id": canonical_source.evidence.id,
                    },
                )
        except DBAPIError as error:
            return getattr(error.orig, "sqlstate", None)
        return None

    async def wait_for_lock_wait() -> None:
        async with database_sessions() as observer:
            while True:
                await observer.execute(text("SELECT pg_stat_clear_snapshot()"))
                waiting = await observer.scalar(
                    text(
                        "SELECT cardinality(pg_blocking_pids(pid)) "
                        "FROM pg_stat_activity WHERE application_name = :name"
                    ),
                    {"name": application_name},
                )
                if waiting is not None and waiting > 0:
                    return

    lock_task = asyncio.create_task(hold_parent_lock())
    citation_task: asyncio.Task[str | None] | None = None
    try:
        await asyncio.wait_for(acquired.wait(), timeout=10)
        citation_task = asyncio.create_task(insert_late_citation())
        await asyncio.wait_for(wait_for_lock_wait(), timeout=10)
    finally:
        release.set()
    await lock_task
    assert citation_task is not None
    assert await citation_task == "P0001"
