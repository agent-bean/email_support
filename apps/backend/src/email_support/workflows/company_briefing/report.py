"""Source-referenced briefing report contracts and deterministic rendering."""

import re
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from email_support.models.briefing import BriefingClaim, ClaimKind


def _markdown_text(value: str) -> str:
    """Keep model-supplied text from creating markup or external links."""
    single_line = " ".join(value.splitlines())
    return re.sub(r"([\\`*_{}\[\]<>#!|])", r"\\\1", single_line)


class BriefingReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    claims: list[BriefingClaim] = Field(max_length=100)
    available_evidence_ids: list[str] = Field(max_length=200)

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        if len({claim.id for claim in self.claims}) != len(self.claims):
            raise ValueError("duplicate claim ID")
        available = set(self.available_evidence_ids)
        if len(available) != len(self.available_evidence_ids):
            raise ValueError("duplicate evidence ID")
        for claim in self.claims:
            if not set(claim.evidence_ids) <= available:
                raise ValueError("unknown evidence reference")
            if (
                claim.kind
                in {ClaimKind.FACT, ClaimKind.NEED, ClaimKind.MEETING_STATEMENT}
                and not claim.evidence_ids
            ):
                raise ValueError("factual claim requires evidence")
        return self

    def render(self) -> str:
        sections = {
            ClaimKind.FACT: "Company facts",
            ClaimKind.NEED: "Stated needs",
            ClaimKind.MEETING_STATEMENT: "Meeting context",
            ClaimKind.SUGGESTION: "Suggestions",
            ClaimKind.QUESTION: "Preparation questions",
            ClaimKind.UNKNOWN: "Unknowns",
        }
        lines = ["# Meeting briefing"]
        for kind, title in sections.items():
            values = [claim for claim in self.claims if claim.kind == kind]
            lines.extend(["", f"## {title}"])
            if not values:
                lines.append("- No information available.")
            for claim in values:
                refs = " ".join(f"[{ref}]" for ref in claim.evidence_ids)
                lines.append(
                    f"- {_markdown_text(claim.text)}" + (f" {refs}" if refs else "")
                )
        return "\n".join(lines) + "\n"
