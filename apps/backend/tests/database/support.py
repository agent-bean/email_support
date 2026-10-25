"""Shared records used by real-database persistence scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from email_support.models.persistence import (
        BriefingRecord,
        BriefingVersionRecord,
        CompanyRecord,
        EvidenceRecord,
    )


@dataclass(frozen=True)
class CanonicalSource:
    company: CompanyRecord
    evidence: EvidenceRecord
    briefing: BriefingRecord
    version: BriefingVersionRecord
