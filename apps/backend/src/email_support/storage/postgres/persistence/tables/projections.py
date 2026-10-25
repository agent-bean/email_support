"""SQLAlchemy mapping for canonical projection metadata."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ProjectionMetadataRow(Base):
    __tablename__ = "projection_metadata"
    __table_args__ = (
        ForeignKeyConstraint(
            ["knowledge_id", "source_version_id"],
            ["knowledge.id", "knowledge.briefing_version_id"],
            name="fk_projection_metadata_knowledge_source",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "projection_kind",
            "knowledge_id",
            name="uq_projection_metadata_kind_knowledge",
        ),
        CheckConstraint(
            "projection_kind IN ('neo4j', 'qdrant')",
            name="ck_projection_metadata_kind",
        ),
        CheckConstraint(
            "projected_version_id IS NULL OR projected_version_id = source_version_id",
            name="ck_projection_metadata_exact_version",
        ),
        CheckConstraint(
            "(projection_kind = 'neo4j' AND embedding_version IS NULL) OR "
            "(projection_kind = 'qdrant' AND "
            "((projected_version_id IS NULL AND embedding_version IS NULL) OR "
            "(projected_version_id IS NOT NULL AND embedding_version IS NOT NULL "
            "AND length(regexp_replace(embedding_version, "
            "'[[:space:]]', '', 'g')) > 0)))",
            name="ck_projection_metadata_embedding_state",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    projection_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    knowledge_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    projected_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    embedding_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
