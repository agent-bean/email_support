"""Contracts for canonical briefing run identity and dependencies."""

from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class KnowledgeDependency(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    knowledge_id: UUID
    briefing_version_id: UUID
    approval_id: UUID


class BriefingRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    input_id: UUID
    company_id: UUID
    contact_id: UUID
    identity_revision: int = Field(gt=0)
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    dependencies: tuple[KnowledgeDependency, ...] = Field(max_length=100)

    @model_validator(mode="after")
    def unique_dependencies(self) -> Self:
        ids = [item.knowledge_id for item in self.dependencies]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate knowledge dependency")
        return self
