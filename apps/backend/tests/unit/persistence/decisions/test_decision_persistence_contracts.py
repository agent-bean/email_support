from uuid import uuid4

import pytest
from pydantic import ValidationError

from email_support.models.persistence import (
    ActionKind,
    ApprovalCreate,
    KnowledgeCreate,
    PreferenceCreate,
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
