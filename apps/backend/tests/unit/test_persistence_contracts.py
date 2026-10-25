from datetime import UTC, date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from email_support.models.persistence import (
    ActionKind,
    AllDayMeetingTime,
    ApprovalCreate,
    BriefingVersionRecord,
    ContactCreate,
    EvidenceCreate,
    EvidenceKind,
    KnowledgeCreate,
    MeetingCreate,
    MeetingTimeKind,
    PreferenceCreate,
    ProjectionKind,
    ProjectionMetadataCreate,
    TimedMeetingTime,
)


def test_contact_requires_explicit_nullable_display_name() -> None:
    with pytest.raises(ValidationError):
        ContactCreate.model_validate({"email": "owner@example.com", "company_id": None})

    contact = ContactCreate(
        email="owner@example.com", display_name=None, company_id=None
    )
    assert contact.display_name is None


def test_contact_validates_email_and_lowercases_only_domain() -> None:
    contact = ContactCreate(
        email="LocalPart@EXAMPLE.COM", display_name="Owner", company_id=None
    )

    assert contact.email == "LocalPart@example.com"
    with pytest.raises(ValidationError):
        ContactCreate(email="not-an-email", display_name=None, company_id=None)
    with pytest.raises(ValidationError):
        ContactCreate.model_validate(
            {"email": "owner@example.com", "display_name": None, "company_id": "bad-id"}
        )


def test_contracts_reject_unknown_fields_and_finite_identifiers() -> None:
    with pytest.raises(ValidationError):
        ContactCreate.model_validate(
            {
                "email": "owner@example.com",
                "display_name": None,
                "company_id": None,
                "is_owner": True,
            }
        )

    with pytest.raises(ValidationError):
        EvidenceCreate.model_validate(
            {
                "kind": "calendar",
                "mail_message_id": None,
                "meeting_id": None,
                "source_url": None,
                "source_text": "snapshot",
                "retrieved_at": datetime.now(UTC),
            }
        )

    assert EvidenceKind.MAIL.value == "mail"
    assert MeetingTimeKind.TIMED.value == "timed"

    with pytest.raises(ValidationError):
        EvidenceCreate.model_validate(
            {
                "kind": EvidenceKind.WEB,
                "mail_message_id": None,
                "meeting_id": None,
                "source_url": "file:///etc/passwd",
                "source_text": "snapshot",
                "retrieved_at": datetime.now(UTC),
            }
        )


def test_meeting_time_variants_require_consistent_fields() -> None:
    starts_at = datetime(2026, 10, 25, 10, tzinfo=UTC)
    with pytest.raises(ValidationError):
        TimedMeetingTime(starts_at=starts_at, ends_at=starts_at)
    with pytest.raises(ValidationError):
        AllDayMeetingTime(start_date=date(2026, 10, 26), end_date=date(2026, 10, 26))

    timed = TimedMeetingTime(
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
    )
    all_day = AllDayMeetingTime(
        start_date=date(2026, 10, 25), end_date=date(2026, 10, 26)
    )
    assert timed.starts_at.tzinfo == UTC
    assert all_day.end_date > all_day.start_date


def test_meeting_instants_must_be_aware_and_are_normalized_to_utc() -> None:
    with pytest.raises(ValidationError):
        TimedMeetingTime(
            starts_at=datetime(2026, 10, 25, 10),
            ends_at=datetime(2026, 10, 25, 11),
        )

    offset_time = datetime(2026, 10, 25, 17, tzinfo=timezone(timedelta(hours=7)))
    meeting_time = TimedMeetingTime(
        starts_at=offset_time,
        ends_at=offset_time + timedelta(hours=1),
    )
    assert meeting_time.starts_at == datetime(2026, 10, 25, 10, tzinfo=UTC)
    assert meeting_time.starts_at.utcoffset() == timedelta(0)


def test_meeting_rejects_mixed_or_missing_time_variant() -> None:
    common = {
        "account_id": uuid4(),
        "external_calendar_id": "primary",
        "external_event_id": "evt-1",
        "title": None,
        "description": None,
        "organizer_email": None,
        "attendee_emails": None,
        "company_id": None,
    }
    with pytest.raises(ValidationError):
        MeetingCreate.model_validate(common)

    with pytest.raises(ValidationError):
        MeetingCreate.model_validate(
            {
                **common,
                "time": {
                    "kind": "all_day",
                    "start_date": "2026-10-25",
                    "end_date": "2026-10-26",
                    "starts_at": "2026-10-25T10:00:00Z",
                },
            }
        )


def test_briefing_version_records_require_positive_numbers_and_aware_time() -> None:
    base = {
        "id": uuid4(),
        "briefing_id": uuid4(),
        "markdown": "# Briefing",
        "sealed": True,
        "created_at": datetime.now(UTC),
    }
    with pytest.raises(ValidationError):
        BriefingVersionRecord.model_validate({**base, "version_number": 0})
    with pytest.raises(ValidationError):
        BriefingVersionRecord.model_validate(
            {**base, "created_at": datetime.now(), "version_number": 1}
        )


def test_approval_contract_normalizes_recipients_and_preserves_selected_text() -> None:
    version_id = uuid4()
    approval = ApprovalCreate.model_validate(
        {
            "briefing_id": uuid4(),
            "briefing_version_id": version_id,
            "action_kind": ActionKind.SAVE_KNOWLEDGE,
            "recipient_emails": [],
            "selected_knowledge": ["  Keep this exact text.  ", "第二条\n"],
        }
    )
    assert approval.selected_knowledge == ["  Keep this exact text.  ", "第二条\n"]

    send = ApprovalCreate.model_validate(
        {
            "briefing_id": uuid4(),
            "briefing_version_id": version_id,
            "action_kind": "send_email",
            "recipient_emails": [
                "Bob@EXAMPLE.COM",
                "alice@example.org",
                "Bob@example.com",
            ],
            "selected_knowledge": [],
        }
    )
    assert send.recipient_emails == ["Bob@example.com", "alice@example.org"]


def test_approval_contract_rejects_inconsistent_actions_and_missing_arrays() -> None:
    base = {
        "briefing_id": uuid4(),
        "briefing_version_id": uuid4(),
        "recipient_emails": [],
        "selected_knowledge": [],
    }
    with pytest.raises(ValidationError):
        ApprovalCreate.model_validate({**base, "action_kind": "send_email"})
    with pytest.raises(ValidationError):
        ApprovalCreate.model_validate(
            {
                **base,
                "action_kind": "save_knowledge",
                "selected_knowledge": ["  \n"],
            }
        )
    with pytest.raises(ValidationError):
        ApprovalCreate.model_validate(
            {
                **base,
                "action_kind": "save_knowledge",
                "recipient_emails": ["owner@example.com"],
                "selected_knowledge": ["text"],
            }
        )
    with pytest.raises(ValidationError):
        ApprovalCreate.model_validate(
            {
                "briefing_id": uuid4(),
                "briefing_version_id": uuid4(),
                "action_kind": "execute",
                "recipient_emails": [],
                "selected_knowledge": [],
            }
        )
    with pytest.raises(ValidationError):
        ApprovalCreate.model_validate(
            {
                "briefing_id": uuid4(),
                "briefing_version_id": uuid4(),
                "action_kind": "send_email",
                "recipient_emails": ["owner@example.com"],
            }
        )


def test_knowledge_content_is_not_replaceable_and_preference_accepts_json_null() -> (
    None
):
    with pytest.raises(ValidationError):
        KnowledgeCreate.model_validate(
            {
                "approval_id": uuid4(),
                "selection_index": 0,
                "company_id": None,
                "evidence_ids": [],
                "content": "replacement text",
            }
        )

    preference = PreferenceCreate.model_validate({"key": "tone", "value": None})
    assert preference.value is None
    with pytest.raises(ValidationError):
        PreferenceCreate.model_validate({"key": "tone"})


def test_projection_contract_rejects_unknown_projection_kind_and_fields() -> None:
    values = {
        "knowledge_id": uuid4(),
        "source_version_id": uuid4(),
        "projected_version_id": None,
        "embedding_version": None,
    }
    with pytest.raises(ValidationError):
        ProjectionMetadataCreate.model_validate(
            {**values, "projection_kind": "neo_graph"}
        )
    valid = ProjectionMetadataCreate.model_validate(
        {**values, "projection_kind": ProjectionKind.NEO4J}
    )
    assert valid.embedding_version is None
    with pytest.raises(ValidationError):
        ProjectionMetadataCreate.model_validate(
            {**values, "projection_kind": ProjectionKind.NEO4J, "job_id": uuid4()}
        )
    with pytest.raises(ValidationError):
        ProjectionMetadataCreate.model_validate(
            {
                **values,
                "projection_kind": ProjectionKind.NEO4J,
                "embedding_version": "embedding-v1",
            }
        )
    with pytest.raises(ValidationError):
        ProjectionMetadataCreate.model_validate(
            {
                **values,
                "projection_kind": ProjectionKind.QDRANT,
                "projected_version_id": uuid4(),
                "embedding_version": "embedding-v1",
            }
        )
    with pytest.raises(ValidationError):
        ProjectionMetadataCreate.model_validate(
            {
                **values,
                "projection_kind": ProjectionKind.QDRANT,
                "embedding_version": "embedding-v1",
            }
        )
