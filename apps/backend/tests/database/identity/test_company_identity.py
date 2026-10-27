from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from email_support.models.email_interpretation import (
    CompanyCandidate,
    CompanyCorrectionRequest,
    CompanyIdentityStatus,
    EmailInterpretation,
    EmailRelevance,
    EvidenceSpan,
    InputField,
    InputOriginKind,
    MeetingState,
    NormalizedEmailInput,
    NormalizedInputCreate,
    ProviderSourceKind,
    ProviderSourceReference,
)
from email_support.models.persistence import (
    CompanyCreate,
    ContactCreate,
    ContactRecord,
    EvidenceCreate,
    EvidenceKind,
    MailMessageCreate,
    ProviderAccountCreate,
)
from email_support.services.company_identity import resolve_company_identity
from email_support.storage.postgres.persistence.core import (
    PersistenceConflict,
    PersistenceNotFound,
    create_company,
    create_evidence,
    create_mail_message,
    create_provider_account,
    get_evidence,
)
from email_support.storage.postgres.persistence.identity import (
    correct_contact_company,
    create_normalized_input,
    get_or_create_contact_by_email,
    list_eligible_mail_history,
)


def _input(
    *,
    origin_key: str | None = None,
    sender_email: str | None = "Sales@EXAMPLE.COM",
    body: str = "Please prepare for our discussion.",
) -> NormalizedInputCreate:
    return NormalizedInputCreate(
        origin_kind=InputOriginKind.LOCAL_IMPORT,
        origin_key=origin_key or f"local:{uuid4()}",
        payload=NormalizedEmailInput(
            sender_email=sender_email,
            sender_display_name="Alex",
            subject="Preparation",
            body=body,
            received_at=datetime(2026, 10, 27, 8, tzinfo=UTC),
            meeting_state=MeetingState.ABSENT,
            meeting=None,
        ),
    )


def _candidate(name: str, *, domain: str | None = None) -> EmailInterpretation:
    return EmailInterpretation(
        relevance=EmailRelevance.RELEVANT,
        company_candidates=[
            CompanyCandidate(
                name=name,
                domain=domain,
                evidence=[
                    EvidenceSpan(
                        field=InputField.EMAIL_BODY,
                        start=0,
                        end=7,
                        quote="Please ",
                    )
                ],
            )
        ],
        contact_candidates=[],
        stated_needs=[],
        ambiguity_reasons=[],
        unknowns=[],
    )


@pytest.mark.asyncio
async def test_normalized_inputs_are_idempotent_and_origin_content_is_immutable(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    first_value = _input(origin_key="local:stable-1")
    same_value = _input(origin_key="local:stable-1")
    changed_value = _input(origin_key="local:stable-1", body="Changed after import.")
    async with database_sessions() as session, session.begin():
        first = await create_normalized_input(session, first_value)
        repeated = await create_normalized_input(session, same_value)

    assert first.id == repeated.id
    assert first.content_hash == same_value.content_hash
    with pytest.raises(PersistenceConflict):
        async with database_sessions() as session, session.begin():
            await create_normalized_input(session, changed_value)


@pytest.mark.asyncio
async def test_normalized_input_is_a_valid_exactly_one_evidence_source(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with database_sessions() as session, session.begin():
        normalized = await create_normalized_input(session, _input())
        evidence = await create_evidence(
            session,
            EvidenceCreate(
                kind=EvidenceKind.NORMALIZED_INPUT,
                mail_message_id=None,
                meeting_id=None,
                source_url=None,
                normalized_input_id=normalized.id,
                source_text="Source text imported from the normalized email.",
                retrieved_at=datetime(2026, 10, 27, 8, tzinfo=UTC),
            ),
        )
        loaded = await get_evidence(session, evidence.id)
    assert loaded.kind is EvidenceKind.NORMALIZED_INPUT
    assert loaded.normalized_input_id == normalized.id


@pytest.mark.asyncio
async def test_provider_origin_requires_an_existing_canonical_record(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    source_id = uuid4()
    value = NormalizedInputCreate(
        origin_kind=InputOriginKind.PROVIDER,
        origin_key=f"mail:{source_id}:external-1",
        payload=_input().payload,
        provider_source=ProviderSourceReference(
            kind=ProviderSourceKind.MAIL,
            record_id=source_id,
            external_id="external-1",
        ),
    )
    with pytest.raises(PersistenceNotFound):
        async with database_sessions() as session, session.begin():
            await create_normalized_input(session, value)


@pytest.mark.asyncio
async def test_contact_get_or_create_is_stable_under_concurrent_normalized_email(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async def resolve(display_name: str) -> ContactRecord:
        async with database_sessions() as session, session.begin():
            return await get_or_create_contact_by_email(
                session,
                ContactCreate(
                    company_id=None,
                    email="Sales@EXAMPLE.COM",
                    display_name=display_name,
                ),
            )

    first, second = await asyncio.gather(resolve("Alex One"), resolve("Alex Two"))
    assert first.id == second.id
    assert first.email == "Sales@example.com"
    assert first.identity_revision == second.identity_revision == 1
    assert first.company_id is None and second.company_id is None


@pytest.mark.asyncio
async def test_owner_correction_is_revision_checked_idempotent_and_clearable(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with database_sessions() as session, session.begin():
        company_a = await create_company(
            session, CompanyCreate(name="Company A", domain="a.example")
        )
        company_b = await create_company(
            session, CompanyCreate(name="Company B", domain="b.example")
        )
        contact = await get_or_create_contact_by_email(
            session,
            ContactCreate(
                company_id=company_a.id,
                email="sales@example.com",
                display_name="Sales",
            ),
        )

    async with database_sessions() as session, session.begin():
        corrected = await correct_contact_company(
            session,
            CompanyCorrectionRequest(
                contact_id=contact.id,
                company_id=company_b.id,
                expected_revision=1,
            ),
        )
    assert corrected.company_id == company_b.id
    assert corrected.identity_revision == 2

    async with database_sessions() as session, session.begin():
        repeated = await correct_contact_company(
            session,
            CompanyCorrectionRequest(
                contact_id=contact.id,
                company_id=company_b.id,
                expected_revision=1,
            ),
        )
    assert repeated.company_id == company_b.id
    assert repeated.identity_revision == 2

    with pytest.raises(PersistenceConflict):
        async with database_sessions() as session, session.begin():
            await correct_contact_company(
                session,
                CompanyCorrectionRequest(
                    contact_id=contact.id,
                    company_id=company_a.id,
                    expected_revision=1,
                ),
            )

    async with database_sessions() as session, session.begin():
        cleared = await correct_contact_company(
            session,
            CompanyCorrectionRequest(
                contact_id=contact.id,
                company_id=None,
                expected_revision=2,
            ),
        )
    assert cleared.company_id is None
    assert cleared.identity_revision == 3


@pytest.mark.asyncio
async def test_concurrent_corrections_cannot_overwrite_the_same_revision(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with database_sessions() as session, session.begin():
        company_a = await create_company(
            session, CompanyCreate(name="Company A", domain="a.example")
        )
        company_b = await create_company(
            session, CompanyCreate(name="Company B", domain="b.example")
        )
        contact = await get_or_create_contact_by_email(
            session,
            ContactCreate(
                company_id=None,
                email="sales@example.com",
                display_name="Sales",
            ),
        )

    async def correct(company_id: UUID) -> ContactRecord:
        async with database_sessions() as session, session.begin():
            return await correct_contact_company(
                session,
                CompanyCorrectionRequest(
                    contact_id=contact.id,
                    company_id=company_id,
                    expected_revision=1,
                ),
            )

    first, second = await asyncio.gather(
        correct(company_a.id), correct(company_b.id), return_exceptions=True
    )
    successes = [item for item in (first, second) if isinstance(item, ContactRecord)]
    failures = [
        item for item in (first, second) if isinstance(item, PersistenceConflict)
    ]
    assert len(successes) == len(failures) == 1
    assert successes[0].identity_revision == 2


@pytest.mark.asyncio
async def test_correction_does_not_move_old_mail_into_new_company_history(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with database_sessions() as session, session.begin():
        company_a = await create_company(
            session, CompanyCreate(name="Company A", domain="a.example")
        )
        company_b = await create_company(
            session, CompanyCreate(name="Company B", domain="b.example")
        )
        contact = await get_or_create_contact_by_email(
            session,
            ContactCreate(
                company_id=company_a.id,
                email="sales@example.com",
                display_name="Sales",
            ),
        )
        account = await create_provider_account(
            session,
            ProviderAccountCreate(provider="google", external_account_id="owner"),
        )
        message = await create_mail_message(
            session,
            MailMessageCreate(
                account_id=account.id,
                external_message_id=f"message-{uuid4()}",
                external_thread_id=None,
                sender_email="sales@example.com",
                recipient_emails=None,
                subject="Previous company history",
                body_text="Previously linked to Company A.",
                received_at=datetime(2026, 10, 1, tzinfo=UTC),
                company_id=company_a.id,
                contact_id=contact.id,
            ),
        )
        eligible_before_correction = await list_eligible_mail_history(
            session,
            contact_id=contact.id,
            company_id=company_a.id,
            identity_revision=contact.identity_revision,
        )
        corrected = await correct_contact_company(
            session,
            CompanyCorrectionRequest(
                contact_id=contact.id,
                company_id=company_b.id,
                expected_revision=1,
            ),
        )
    async with database_sessions() as session, session.begin():
        history = await list_eligible_mail_history(
            session,
            contact_id=contact.id,
            company_id=corrected.company_id,
            identity_revision=corrected.identity_revision,
        )
    assert message.company_id == company_a.id
    assert [item.id for item in eligible_before_correction] == [message.id]
    assert history == []


@pytest.mark.asyncio
async def test_candidate_names_and_shared_domains_never_create_company_mapping(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    input_value = _input()
    async with database_sessions() as session, session.begin():
        company_a = await create_company(
            session, CompanyCreate(name="Example Holdings", domain="shared.example")
        )
        company_b = await create_company(
            session,
            CompanyCreate(name="Example Holdings Group", domain="shared.example"),
        )
        persisted_input = await create_normalized_input(session, input_value)

    async with database_sessions() as session, session.begin():
        result = await resolve_company_identity(
            session,
            persisted_input,
            _candidate("Example Holdings", domain="shared.example"),
        )
    assert result.status is CompanyIdentityStatus.AMBIGUOUS
    assert result.contact_id is not None
    assert result.company_id is None
    assert set(result.candidate_company_ids) == {company_a.id, company_b.id}
    async with database_sessions() as session:
        contact_row = await session.execute(
            text("SELECT company_id FROM contacts WHERE id = :id"),
            {"id": result.contact_id},
        )
    assert contact_row.scalar_one() is None


@pytest.mark.asyncio
async def test_contradictory_candidate_blocks_context_and_null_never_lists_history(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    input_value = _input()
    async with database_sessions() as session, session.begin():
        company_a = await create_company(
            session, CompanyCreate(name="Company A", domain="a.example")
        )
        company_b = await create_company(
            session, CompanyCreate(name="Company B", domain="b.example")
        )
        contact = await get_or_create_contact_by_email(
            session,
            ContactCreate(
                company_id=company_a.id,
                email="Sales@example.com",
                display_name="Alex",
            ),
        )
        persisted_input = await create_normalized_input(session, input_value)

    async with database_sessions() as session, session.begin():
        result = await resolve_company_identity(
            session, persisted_input, _candidate("Company B", domain="b.example")
        )
        with pytest.raises(PersistenceConflict):
            await list_eligible_mail_history(
                session,
                contact_id=contact.id,
                company_id=company_b.id,
                identity_revision=1,
            )
        empty = await list_eligible_mail_history(
            session,
            contact_id=contact.id,
            company_id=None,
            identity_revision=1,
        )
    assert result.status is CompanyIdentityStatus.AMBIGUOUS
    assert result.company_id is None
    assert empty == []
