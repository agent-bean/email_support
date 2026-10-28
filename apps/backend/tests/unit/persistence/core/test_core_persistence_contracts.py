from datetime import UTC, date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from email_support.models.persistence import (
    AllDayMeetingTime,
    BriefingVersionRecord,
    ContactCreate,
    EvidenceCreate,
    EvidenceKind,
    MeetingCreate,
    MeetingTimeKind,
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


def test_normalized_input_evidence_requires_only_its_own_source() -> None:
    from email_support.models.email_interpretation import InputOriginKind
    from email_support.models.persistence.core import EvidenceKind

    source_id = uuid4()
    record = EvidenceCreate(
        kind=EvidenceKind.NORMALIZED_INPUT,
        mail_message_id=None,
        meeting_id=None,
        source_url=None,
        normalized_input_id=source_id,
        source_text="Imported email source",
        retrieved_at=datetime.now(UTC),
    )
    assert record.normalized_input_id == source_id
    assert InputOriginKind.EVALUATION.value == "evaluation"

    with pytest.raises(ValidationError):
        EvidenceCreate(
            kind=EvidenceKind.NORMALIZED_INPUT,
            mail_message_id=uuid4(),
            meeting_id=None,
            source_url=None,
            normalized_input_id=source_id,
            source_text="Conflicting source fields",
            retrieved_at=datetime.now(UTC),
        )

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
        "evidence_ids": [],
    }
    with pytest.raises(ValidationError):
        BriefingVersionRecord.model_validate({**base, "version_number": 0})
    with pytest.raises(ValidationError):
        BriefingVersionRecord.model_validate(
            {**base, "created_at": datetime.now(), "version_number": 1}
        )
