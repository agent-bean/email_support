"""Typed contracts for canonical projection metadata."""

from datetime import datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import field_validator, model_validator

from .common import NonBlankText, PersistenceContract, _normalize_utc


class ProjectionKind(StrEnum):
    NEO4J = "neo4j"
    QDRANT = "qdrant"


class ProjectionMetadataCreate(PersistenceContract):
    projection_kind: ProjectionKind
    knowledge_id: UUID
    source_version_id: UUID
    projected_version_id: UUID | None
    embedding_version: NonBlankText | None

    @model_validator(mode="after")
    def require_consistent_projection(self) -> Self:
        if self.projected_version_id not in (None, self.source_version_id):
            raise ValueError("projection must reference the canonical source version")
        if self.projection_kind is ProjectionKind.NEO4J:
            if self.embedding_version is not None:
                raise ValueError("graph projections do not have an embedding version")
        elif (self.projected_version_id is None) != (self.embedding_version is None):
            raise ValueError(
                "vector projection version and embedding version must agree"
            )
        return self


class ProjectionMetadataRecord(ProjectionMetadataCreate):
    id: UUID
    updated_at: datetime

    _updated_at_utc = field_validator("updated_at")(_normalize_utc)
