"""Shared claim and evidence contracts for briefing production and evaluation."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ClaimKind(StrEnum):
    FACT = "fact"
    NEED = "need"
    MEETING_STATEMENT = "meeting_statement"
    SUGGESTION = "suggestion"
    QUESTION = "question"
    UNKNOWN = "unknown"


class BriefingClaim(BaseModel):
    """A claim's kind and evidence references, without model-authored support labels."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=100)
    kind: ClaimKind
    text: str = Field(min_length=1, max_length=4000)
    evidence_ids: list[str] = Field(max_length=20)

    @model_validator(mode="after")
    def evidence_ids_are_unique(self) -> BriefingClaim:
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("evidence IDs must be unique")
        return self
