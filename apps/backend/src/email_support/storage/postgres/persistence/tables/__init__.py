"""Public PostgreSQL mappings grouped by canonical data scope."""

from .auth import OAuthAttemptRow, OwnerSessionRow
from .base import Base
from .core import (
    BriefingRow,
    BriefingVersionEvidenceRow,
    BriefingVersionRow,
    CompanyRow,
    ContactRow,
    EvidenceRow,
    MailMessageRow,
    MeetingRow,
    ProviderAccountRow,
)
from .decisions import (
    ActionRow,
    ApprovalRow,
    KnowledgeEvidenceRow,
    KnowledgeRow,
    PreferenceRow,
)
from .google_connection import GoogleConnectionRow
from .identity import NormalizedInputRow
from .projections import ProjectionMetadataRow

__all__ = [
    "ActionRow",
    "ApprovalRow",
    "Base",
    "BriefingRow",
    "BriefingVersionEvidenceRow",
    "BriefingVersionRow",
    "CompanyRow",
    "GoogleConnectionRow",
    "ContactRow",
    "EvidenceRow",
    "KnowledgeEvidenceRow",
    "KnowledgeRow",
    "MailMessageRow",
    "OAuthAttemptRow",
    "OwnerSessionRow",
    "MeetingRow",
    "NormalizedInputRow",
    "PreferenceRow",
    "ProjectionMetadataRow",
    "ProviderAccountRow",
]
