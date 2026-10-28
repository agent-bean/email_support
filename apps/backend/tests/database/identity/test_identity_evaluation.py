"""Synthetic identity evaluation against the production resolver and real PostgreSQL."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from email_support.models.email_interpretation import (
    CompanyCandidate,
    CompanyCorrectionRequest,
    CompanyIdentityStatus,
    EmailInterpretation,
    EmailRelevance,
    EvidenceSpan,
    IdentitySnapshot,
    InputField,
    InputOriginKind,
    MeetingState,
    NormalizedEmailInput,
    NormalizedInputCreate,
)
from email_support.models.persistence import CompanyCreate, ContactCreate
from email_support.services.company_identity import CompanyIdentityService
from email_support.storage.postgres.persistence.core import create_company
from email_support.storage.postgres.persistence.identity import (
    create_normalized_input,
    get_or_create_contact_by_email,
)


@pytest.mark.asyncio
async def test_synthetic_identity_resolution_and_owner_correction(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with database_sessions() as session, session.begin():
        alpha = await create_company(
            session, CompanyCreate(name="Alpha", domain="shared.example")
        )
        beta = await create_company(
            session, CompanyCreate(name="Beta", domain="shared.example")
        )
        twin_a = await create_company(
            session, CompanyCreate(name="Twin", domain="twin-a.example")
        )
        twin_b = await create_company(
            session, CompanyCreate(name="Twin", domain="twin-b.example")
        )
        mapped = await get_or_create_contact_by_email(
            session,
            ContactCreate(
                company_id=alpha.id, email="mapped@example.com", display_name="Alex"
            ),
        )

        async def resolve(
            email: str, name: str | None = None, domain: str | None = None
        ) -> IdentitySnapshot:
            body = "Please discuss the proposal."
            if name:
                body += f" Company: {name}."
            if domain:
                body += f" Website: {domain}."
            normalized = await create_normalized_input(
                session,
                NormalizedInputCreate(
                    origin_kind=InputOriginKind.LOCAL_IMPORT,
                    origin_key=f"local:{uuid4()}",
                    payload=NormalizedEmailInput(
                        sender_email=email,
                        sender_display_name="Alex",
                        subject="Proposal",
                        body=body,
                        received_at=datetime(2026, 10, 27, tzinfo=UTC),
                        meeting_state=MeetingState.ABSENT,
                        meeting=None,
                    ),
                ),
            )
            candidates = (
                []
                if name is None
                else [
                    CompanyCandidate(
                        name=name,
                        domain=domain,
                        evidence=[
                            EvidenceSpan(
                                field=InputField.EMAIL_BODY,
                                start=body.index(name),
                                end=body.index(name) + len(name),
                                quote=name,
                            )
                        ],
                    )
                ]
            )
            interpretation = EmailInterpretation(
                relevance=EmailRelevance.RELEVANT,
                company_candidates=candidates,
                contact_candidates=[],
                stated_needs=[],
                ambiguity_reasons=[],
                unknowns=[],
            )
            return await CompanyIdentityService(session).resolve(
                normalized, interpretation
            )

        # Each tuple records the expected status, selected company, and candidate set.
        cases = [
            (
                "mapped",
                "mapped@example.com",
                None,
                None,
                CompanyIdentityStatus.RESOLVED,
                alpha.id,
                set(),
            ),
            (
                "new",
                "new@example.com",
                "Alpha",
                None,
                CompanyIdentityStatus.UNRESOLVED,
                None,
                {alpha.id},
            ),
            (
                "conflict",
                "mapped@example.com",
                "Beta",
                None,
                CompanyIdentityStatus.AMBIGUOUS,
                None,
                {alpha.id, beta.id},
            ),
            (
                "shared-domain",
                "shared@example.com",
                "Alpha",
                "shared.example",
                CompanyIdentityStatus.AMBIGUOUS,
                None,
                {alpha.id, beta.id},
            ),
            (
                "same-name",
                "twin@example.com",
                "Twin",
                None,
                CompanyIdentityStatus.AMBIGUOUS,
                None,
                {twin_a.id, twin_b.id},
            ),
            (
                "same-display-name",
                "other@example.com",
                None,
                None,
                CompanyIdentityStatus.UNRESOLVED,
                None,
                set(),
            ),
        ]
        for label, email, name, domain, status, company, candidate_ids in cases:
            actual = await resolve(email, name, domain)
            assert (
                actual.status,
                actual.company_id,
                set(actual.candidate_company_ids),
            ) == (status, company, candidate_ids), label
            if email != "mapped@example.com":
                assert actual.contact_id != mapped.id, label
                assert actual.company_id is None, label

        corrected = await CompanyIdentityService(session).correct(
            CompanyCorrectionRequest(
                contact_id=mapped.id, company_id=beta.id, expected_revision=1
            )
        )
        actual = await resolve("mapped@example.com")
        assert (corrected.company_id, corrected.identity_revision) == (beta.id, 2)
        assert (actual.status, actual.company_id, actual.identity_revision) == (
            CompanyIdentityStatus.RESOLVED,
            beta.id,
            2,
        )
        assert await CompanyIdentityService(session).eligible_history(actual) == []
