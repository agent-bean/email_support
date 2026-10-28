"""Deterministic Company Info role backed by owner-controlled identity state."""

from __future__ import annotations

from email_support.models.email_interpretation import (
    EmailInterpretation,
    IdentitySnapshot,
    NormalizedInputRecord,
)
from email_support.services.company_identity import CompanyIdentityService


class CompanyInfoAgent:
    """Resolve typed interpretation output without model-controlled mapping."""

    def __init__(self, identity: CompanyIdentityService) -> None:
        self._identity = identity

    async def resolve(
        self,
        normalized_input: NormalizedInputRecord,
        interpretation: EmailInterpretation,
    ) -> IdentitySnapshot:
        return await self._identity.resolve(normalized_input, interpretation)


__all__ = ["CompanyInfoAgent"]
