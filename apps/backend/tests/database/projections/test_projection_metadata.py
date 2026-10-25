from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from email_support.models.persistence import (
    ActionKind,
    ApprovalCreate,
    KnowledgeCreate,
    ProjectionKind,
    ProjectionMetadataCreate,
)
from email_support.storage.postgres.persistence.decisions import (
    create_knowledge,
    invalidate_knowledge,
    list_eligible_knowledge,
    record_approval_and_action,
)
from email_support.storage.postgres.persistence.projections import (
    get_projection_metadata,
    set_projection_metadata,
)
from tests.database.support import CanonicalSource


@pytest.mark.asyncio
async def test_projection_metadata_is_bound_to_exact_source_and_invalidation_wins(
    database_sessions: async_sessionmaker[AsyncSession],
    canonical_source: CanonicalSource,
) -> None:
    async with database_sessions() as session, session.begin():
        approval, _ = await record_approval_and_action(
            session,
            ApprovalCreate(
                briefing_id=canonical_source.briefing.id,
                briefing_version_id=canonical_source.version.id,
                action_kind=ActionKind.SAVE_KNOWLEDGE,
                recipient_emails=[],
                selected_knowledge=["Approved knowledge."],
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
        never_projected = await set_projection_metadata(
            session,
            ProjectionMetadataCreate(
                projection_kind=ProjectionKind.NEO4J,
                knowledge_id=knowledge.id,
                source_version_id=canonical_source.version.id,
                projected_version_id=None,
                embedding_version=None,
            ),
        )
        graph = await set_projection_metadata(
            session,
            ProjectionMetadataCreate(
                projection_kind=ProjectionKind.NEO4J,
                knowledge_id=knowledge.id,
                source_version_id=canonical_source.version.id,
                projected_version_id=canonical_source.version.id,
                embedding_version=None,
            ),
        )
        vector = await set_projection_metadata(
            session,
            ProjectionMetadataCreate(
                projection_kind=ProjectionKind.QDRANT,
                knowledge_id=knowledge.id,
                source_version_id=canonical_source.version.id,
                projected_version_id=canonical_source.version.id,
                embedding_version="embedding-v2",
            ),
        )

    assert never_projected.projected_version_id is None
    assert never_projected.embedding_version is None
    assert graph.projected_version_id == canonical_source.version.id
    async with database_sessions() as session:
        assert (
            await get_projection_metadata(session, ProjectionKind.NEO4J, knowledge.id)
        ) == graph
        assert (
            await get_projection_metadata(session, ProjectionKind.QDRANT, knowledge.id)
        ) == vector
        assert len(await list_eligible_knowledge(session)) == 1

    async with database_sessions() as session, session.begin():
        await invalidate_knowledge(session, knowledge.id)

    async with database_sessions() as session:
        assert await list_eligible_knowledge(session) == []
        assert (
            await get_projection_metadata(session, ProjectionKind.QDRANT, knowledge.id)
        ) == vector


@pytest.mark.asyncio
async def test_projection_rejects_invalid_versions_and_embedding_states(
    database_sessions: async_sessionmaker[AsyncSession],
    canonical_source: CanonicalSource,
) -> None:
    async with database_sessions() as session, session.begin():
        approval, _ = await record_approval_and_action(
            session,
            ApprovalCreate(
                briefing_id=canonical_source.briefing.id,
                briefing_version_id=canonical_source.version.id,
                action_kind=ActionKind.SAVE_KNOWLEDGE,
                recipient_emails=[],
                selected_knowledge=["Approved knowledge."],
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

    invalid_rows = (
        {
            "kind": "neo4j",
            "source": canonical_source.version.id,
            "projected": canonical_source.version.id,
            "embedding": "unexpected",
        },
        {
            "kind": "qdrant",
            "source": canonical_source.version.id,
            "projected": canonical_source.version.id,
            "embedding": None,
        },
        {
            "kind": "qdrant",
            "source": canonical_source.version.id,
            "projected": None,
            "embedding": "unexpected",
        },
        {
            "kind": "neo4j",
            "source": canonical_source.version.id,
            "projected": uuid4(),
            "embedding": None,
        },
    )
    for invalid in invalid_rows:
        with pytest.raises(DBAPIError) as error:
            async with database_sessions() as session, session.begin():
                await session.execute(
                    text(
                        "INSERT INTO projection_metadata "
                        "(id, projection_kind, knowledge_id, source_version_id, "
                        "projected_version_id, embedding_version) "
                        "VALUES (gen_random_uuid(), :kind, :knowledge_id, :source, "
                        ":projected, :embedding)"
                    ),
                    {
                        "kind": invalid["kind"],
                        "knowledge_id": knowledge.id,
                        "source": invalid["source"],
                        "projected": invalid["projected"],
                        "embedding": invalid["embedding"],
                    },
                )
        assert getattr(error.value.orig, "sqlstate", None) == "23514"

    with pytest.raises(DBAPIError) as blank_embedding_error:
        async with database_sessions() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO projection_metadata "
                    "(id, projection_kind, knowledge_id, source_version_id, "
                    "projected_version_id, embedding_version) "
                    "VALUES (gen_random_uuid(), 'qdrant', :knowledge_id, "
                    ":source, :source, :embedding)"
                ),
                {
                    "knowledge_id": knowledge.id,
                    "source": canonical_source.version.id,
                    "embedding": "\t\n",
                },
            )
    assert getattr(blank_embedding_error.value.orig, "sqlstate", None) == "23514"

    with pytest.raises(DBAPIError) as error:
        async with database_sessions() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO projection_metadata "
                    "(id, projection_kind, knowledge_id, source_version_id, "
                    "projected_version_id, embedding_version) "
                    "VALUES (gen_random_uuid(), 'neo4j', :knowledge_id, "
                    "gen_random_uuid(), NULL, NULL)"
                ),
                {"knowledge_id": knowledge.id},
            )
    assert getattr(error.value.orig, "sqlstate", None) == "23503"
