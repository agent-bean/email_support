from pathlib import Path

import pytest

from email_support.models.email_interpretation import NormalizedInputCreate
from evals.live_graph import verify_input
from evals.runner import EvaluationInputError, load_dataset


def test_live_case_requires_exact_email_and_meeting_from_dataset() -> None:
    dataset = load_dataset(Path("evals/datasets/briefing-v1"))
    case = dataset.cases[0]
    assert case.meeting is not None and case.meeting.ends_at is not None
    value = NormalizedInputCreate.model_validate(
        {
            "origin_kind": "evaluation",
            "origin_key": "case-1",
            "payload": {
                "sender_email": str(case.email.from_address),
                "subject": case.email.subject,
                "body": case.email.body,
                "received_at": case.clock,
                "meeting_state": "scheduled",
                "meeting": {
                    "title": case.meeting.title,
                    "description": case.meeting.description,
                    "time": {
                        "kind": "timed",
                        "starts_at": case.meeting.starts_at,
                        "ends_at": case.meeting.ends_at,
                    },
                    "attendees": case.meeting.attendees,
                },
            },
        }
    )
    verify_input(case, value)
    changed = value.model_copy(
        update={"payload": value.payload.model_copy(update={"body": "different"})}
    )
    with pytest.raises(EvaluationInputError):
        verify_input(case, changed)
