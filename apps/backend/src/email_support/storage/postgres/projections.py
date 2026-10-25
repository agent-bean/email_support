"""Canonical projection metadata only; no graph or vector execution."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from email_support.models.persistence import (
    ProjectionKind,
    ProjectionMetadataCreate,
    ProjectionMetadataRecord,
)
from email_support.storage.postgres.core import PersistenceNotFound
from email_support.storage.postgres.tables import ProjectionMetadataRow


def _projection_record(row: ProjectionMetadataRow) -> ProjectionMetadataRecord:
    return ProjectionMetadataRecord.model_validate(
        {
            "id": row.id,
            "projection_kind": row.projection_kind,
            "knowledge_id": row.knowledge_id,
            "source_version_id": row.source_version_id,
            "projected_version_id": row.projected_version_id,
            "embedding_version": row.embedding_version,
            "updated_at": row.updated_at,
        }
    )


async def set_projection_metadata(
    session: AsyncSession, value: ProjectionMetadataCreate
) -> ProjectionMetadataRecord:
    statement = (
        insert(ProjectionMetadataRow)
        .values(
            projection_kind=value.projection_kind.value,
            knowledge_id=value.knowledge_id,
            source_version_id=value.source_version_id,
            projected_version_id=value.projected_version_id,
            embedding_version=value.embedding_version,
        )
        .on_conflict_do_update(
            index_elements=[
                ProjectionMetadataRow.projection_kind,
                ProjectionMetadataRow.knowledge_id,
            ],
            set_={
                "source_version_id": value.source_version_id,
                "projected_version_id": value.projected_version_id,
                "embedding_version": value.embedding_version,
                "updated_at": func.now(),
            },
        )
        .returning(ProjectionMetadataRow)
    )
    row = await session.scalar(statement)
    if row is None:
        raise RuntimeError("projection metadata upsert returned no row")
    return _projection_record(row)


async def get_projection_metadata(
    session: AsyncSession, projection_kind: ProjectionKind, knowledge_id: UUID
) -> ProjectionMetadataRecord:
    row = await session.scalar(
        select(ProjectionMetadataRow).where(
            ProjectionMetadataRow.projection_kind == projection_kind.value,
            ProjectionMetadataRow.knowledge_id == knowledge_id,
        )
    )
    if row is None:
        raise PersistenceNotFound("projection metadata not found")
    return _projection_record(row)
