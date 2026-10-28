"""Deterministic contact identity resolution and owner correction operations."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from email_support.models.email_interpretation import (
    CompanyCorrectionRequest,
    CompanyIdentityStatus,
    EmailInterpretation,
    EmailRelevance,
    IdentitySnapshot,
    NormalizedInputRecord,
)
from email_support.models.persistence import (
    ContactCreate,
    ContactRecord,
    MailMessageRecord,
)
from email_support.storage.postgres.persistence.core import PersistenceNotFound
from email_support.storage.postgres.persistence.identity import (
    correct_contact_company,
    get_or_create_contact_by_email,
    list_eligible_mail_history,
)
from email_support.storage.postgres.persistence.tables import CompanyRow


async def resolve_company_identity(
    session: AsyncSession,
    normalized_input: NormalizedInputRecord,
    interpretation: EmailInterpretation,
) -> IdentitySnapshot:
    """Use only exact sender mapping for identity; model claims remain candidates."""
    if interpretation.relevance is EmailRelevance.IRRELEVANT:
        return IdentitySnapshot(
            status=CompanyIdentityStatus.NONE,
            contact_id=None,
            company_id=None,
            identity_revision=None,
            candidate_company_ids=[],
        )

    candidates = await _candidate_companies(session, interpretation)
    candidate_ids = [company.id for company in candidates]
    email = normalized_input.payload.sender_email
    if email is None or interpretation.relevance is EmailRelevance.UNCERTAIN:
        status = (
            CompanyIdentityStatus.AMBIGUOUS
            if len(candidate_ids) > 1
            else CompanyIdentityStatus.UNRESOLVED
        )
        return IdentitySnapshot(
            status=status,
            contact_id=None,
            company_id=None,
            identity_revision=None,
            candidate_company_ids=candidate_ids,
        )

    contact = await get_or_create_contact_by_email(
        session,
        ContactCreate(
            company_id=None,
            email=email,
            display_name=normalized_input.payload.sender_display_name,
        ),
    )
    if contact.company_id is None:
        status = (
            CompanyIdentityStatus.AMBIGUOUS
            if len(candidate_ids) > 1
            else CompanyIdentityStatus.UNRESOLVED
        )
        return IdentitySnapshot(
            status=status,
            contact_id=contact.id,
            company_id=None,
            identity_revision=contact.identity_revision,
            candidate_company_ids=candidate_ids,
        )

    company = await session.get(CompanyRow, contact.company_id)
    if company is None:
        raise PersistenceNotFound("contact company not found")
    assertions_match = all(
        _candidate_matches_company(candidate.name, candidate.domain, company)
        for candidate in interpretation.company_candidates
    )
    if not assertions_match or (candidate_ids and set(candidate_ids) != {company.id}):
        return IdentitySnapshot(
            status=CompanyIdentityStatus.AMBIGUOUS,
            contact_id=contact.id,
            company_id=None,
            identity_revision=contact.identity_revision,
            candidate_company_ids=sorted({company.id, *candidate_ids}, key=str),
        )
    return IdentitySnapshot(
        status=CompanyIdentityStatus.RESOLVED,
        contact_id=contact.id,
        company_id=company.id,
        identity_revision=contact.identity_revision,
        candidate_company_ids=[],
    )


async def _candidate_companies(
    session: AsyncSession, interpretation: EmailInterpretation
) -> list[CompanyRow]:
    if not interpretation.company_candidates:
        return []
    conditions = []
    for candidate in interpretation.company_candidates:
        conditions.append(func.lower(CompanyRow.name) == candidate.name.lower())
        if candidate.domain:
            conditions.append(func.lower(CompanyRow.domain) == candidate.domain.lower())
    return list(
        (
            await session.scalars(
                select(CompanyRow).where(or_(*conditions)).order_by(CompanyRow.id)
            )
        ).all()
    )


def _candidate_matches_company(
    candidate_name: str, candidate_domain: str | None, company: CompanyRow
) -> bool:
    if candidate_name.casefold() == company.name.casefold():
        return True
    return bool(
        candidate_domain
        and company.domain
        and candidate_domain.casefold() == company.domain.casefold()
    )


class CompanyIdentityService:
    """Small typed facade used by local owner operations and later workflows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve(
        self,
        normalized_input: NormalizedInputRecord,
        interpretation: EmailInterpretation,
    ) -> IdentitySnapshot:
        return await resolve_company_identity(
            self._session, normalized_input, interpretation
        )

    async def correct(self, request: CompanyCorrectionRequest) -> ContactRecord:
        return await correct_contact_company(self._session, request)

    async def eligible_history(
        self, snapshot: IdentitySnapshot
    ) -> list[MailMessageRecord]:
        if snapshot.status is not CompanyIdentityStatus.RESOLVED:
            return []
        assert snapshot.contact_id is not None
        assert snapshot.company_id is not None
        assert snapshot.identity_revision is not None
        return await list_eligible_mail_history(
            self._session,
            contact_id=snapshot.contact_id,
            company_id=snapshot.company_id,
            identity_revision=snapshot.identity_revision,
        )


__all__ = [
    "CompanyIdentityService",
    "resolve_company_identity",
]
