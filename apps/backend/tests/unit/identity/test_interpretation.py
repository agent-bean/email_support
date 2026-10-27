from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx2
import pytest
from pydantic import ValidationError

from email_support.agents.email_interpretation import EmailInterpretationAgent
from email_support.integrations.llm_gateway import GatewayClient
from email_support.integrations.provider_http import ProviderCallError
from email_support.models.email_interpretation import (
    CompanyCandidate,
    EmailInterpretation,
    EmailRelevance,
    EvidenceSpan,
    FollowUpIntent,
    InputField,
    InputOriginKind,
    NormalizedEmailInput,
    NormalizedInputCreate,
    StatedNeed,
)
from email_support.models.research import ProviderErrorCategory, ToolExecutionEvent
from email_support.research_config import ResearchSettings
from email_support.tools.execution import RunBudget, ToolExecutor


def _input(**overrides: object) -> NormalizedInputCreate:
    payload: dict[str, object] = {
        "sender_email": "Sales@EXAMPLE.COM",
        "sender_display_name": "Alex",
        "subject": "Meeting preparation",
        "body": "Please prepare for a discussion about Microsoft.",
        "received_at": datetime(2026, 10, 27, 8, tzinfo=UTC),
        "meeting_state": "absent",
        "meeting": None,
    }
    payload.update(overrides)
    return NormalizedInputCreate(
        origin_kind=InputOriginKind.LOCAL_IMPORT,
        origin_key="local:email-1",
        payload=NormalizedEmailInput.model_validate(payload),
    )


def _settings() -> ResearchSettings:
    return ResearchSettings.from_environment(
        {
            "RESEARCH_GATEWAY_URL": "https://gateway.example/v1",
            "RESEARCH_GATEWAY_API_KEY": "gateway-secret",
            "RESEARCH_GATEWAY_MODEL": "configured-chat-model",
            "OPENROUTER_API_KEY": "router-secret",
            "OPENROUTER_EMBEDDING_MODEL": "embedding-model",
            "TAVILY_API_KEY": "search-secret",
        }
    )


def test_normalized_input_preserves_local_part_and_hashes_canonical_content() -> None:
    first = _input()
    repeated = _input()
    changed = _input(body="Please prepare for a discussion about Salesforce.")

    assert first.payload.sender_email == "Sales@example.com"
    assert first.content_hash == repeated.content_hash
    assert first.content_hash != changed.content_hash


def test_contact_evidence_can_anchor_to_the_actual_sender_address() -> None:
    payload = _input().payload
    span = EvidenceSpan.model_validate(
        {"field": "sender_email", "start": 0, "end": 17, "quote": "Sales@example.com"}
    )
    assert span.validate_against(payload) == payload.sender_email
    with pytest.raises(ValueError):
        span.validate_against(_input(sender_email=None).payload)


def test_normalized_meeting_absence_and_cancellation_are_explicit() -> None:
    with pytest.raises(ValidationError):
        NormalizedEmailInput.model_validate(
            {
                "sender_email": "alex@example.com",
                "subject": "Meeting",
                "body": "Prepare.",
                "received_at": datetime(2026, 10, 27, tzinfo=UTC),
                "meeting_state": "scheduled",
                "meeting": None,
            }
        )
    cancelled = NormalizedEmailInput.model_validate(
        {
            "sender_email": "alex@example.com",
            "subject": "Cancelled",
            "body": "The meeting is cancelled.",
            "received_at": datetime(2026, 10, 27, tzinfo=UTC),
            "meeting_state": "cancelled",
            "meeting": None,
        }
    )
    assert cancelled.meeting_state.value == "cancelled"


def test_normalized_input_preserves_all_day_meeting_dates() -> None:
    value = _input(
        meeting_state="scheduled",
        meeting={
            "title": "Annual planning",
            "description": "Synthetic planning meeting.",
            "time": {
                "kind": "all_day",
                "start_date": "2026-11-01",
                "end_date": "2026-11-03",
            },
            "attendees": ["Sales@example.com"],
        },
    )
    assert value.payload.meeting is not None
    assert value.payload.meeting.time.kind == "all_day"


def test_interpretation_requires_source_spans_for_needs_and_company_candidates() -> (
    None
):
    content = "Please prepare for a discussion about Microsoft."
    start = content.index("Microsoft")
    interpretation = EmailInterpretation(
        relevance=EmailRelevance.RELEVANT,
        company_candidates=[
            CompanyCandidate(
                name="Microsoft",
                domain="microsoft.com",
                evidence=[
                    EvidenceSpan(
                        field=InputField.EMAIL_BODY,
                        start=start,
                        end=start + len("Microsoft"),
                        quote="Microsoft",
                    )
                ],
            )
        ],
        contact_candidates=[],
        stated_needs=[
            StatedNeed(
                text="Prepare for a discussion",
                evidence=[
                    EvidenceSpan(
                        field=InputField.EMAIL_BODY,
                        start=0,
                        end=content.index(" about"),
                        quote="Please prepare for a discussion",
                    )
                ],
            )
        ],
        ambiguity_reasons=[],
        unknowns=[],
    )

    interpretation.validate_evidence_against(_input().payload)
    with pytest.raises(ValueError, match="does not match input"):
        EvidenceSpan(
            field=InputField.EMAIL_BODY,
            start=start,
            end=start + len("Microsoft"),
            quote="invented",
        ).validate_against(_input().payload)
    with pytest.raises(ValidationError):
        EmailInterpretation.model_validate(
            {
                **interpretation.model_dump(),
                "verified_company_id": str(uuid4()),
            }
        )


def test_interpretation_reanchors_wrong_offsets_only_for_unique_exact_quotes() -> None:
    content = "Please prepare for a discussion about Microsoft."
    correct_start = content.index("Microsoft")
    payload = _input().payload
    interpretation = EmailInterpretation(
        relevance=EmailRelevance.RELEVANT,
        company_candidates=[
            CompanyCandidate(
                name="Microsoft",
                evidence=[
                    EvidenceSpan(
                        field=InputField.EMAIL_BODY,
                        start=correct_start + 1,
                        end=correct_start + 10,
                        quote="Microsoft",
                    )
                ],
            )
        ],
        contact_candidates=[],
        stated_needs=[],
        ambiguity_reasons=[],
        unknowns=[],
    )

    anchored = interpretation.anchor_evidence_against(payload)
    anchored.validate_evidence_against(payload)
    assert anchored.company_candidates[0].evidence[0].start == correct_start

    repeated = _input(body="Microsoft met Microsoft.").payload
    with pytest.raises(ValueError, match="not unique"):
        interpretation.anchor_evidence_against(repeated)


@pytest.mark.asyncio
async def test_email_interpreter_uses_strict_output_without_any_tools() -> None:
    requested: list[dict[str, object]] = []

    async def handler(request: httpx2.Request) -> httpx2.Response:
        payload = json.loads(request.content)
        requested.append(payload)
        response_schema = payload["response_format"]["json_schema"]["schema"]
        assert response_schema["additionalProperties"] is False
        assert (
            json.dumps(response_schema, ensure_ascii=False)
            in payload["messages"][0]["content"]
        )
        assert "quote occurs exactly once" in payload["messages"][0]["content"]
        assert "tools" not in payload
        assert "stated_needs must be empty" in payload["messages"][0]["content"]
        assert "past meeting" in payload["messages"][0]["content"]
        assert "must not be stated business needs" in payload["messages"][0]["content"]
        assert "PRIVATE-EMAIL-CONTENT" in payload["messages"][1]["content"]
        return httpx2.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {
                                    "relevance": "irrelevant",
                                    "company_candidates": [],
                                    "contact_candidates": [],
                                    "stated_needs": [],
                                    "ambiguity_reasons": [],
                                    "unknowns": [],
                                }
                            ),
                            "tool_calls": [],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 8},
            },
        )

    payload = _input(body="PRIVATE-EMAIL-CONTENT")
    events: list[ToolExecutionEvent] = []
    budget = RunBudget(
        max_calls=2,
        max_attempts=1,
        max_concurrency=1,
        deadline_seconds=5,
    )
    executor = ToolExecutor([], budget, events=events)
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        agent = EmailInterpretationAgent(
            GatewayClient(_settings(), client),
            "configured-chat-model",
            executor,
        )
        result = await agent.interpret(payload, run_id=uuid4())

    assert result.relevance is EmailRelevance.IRRELEVANT
    assert len(requested) == 1
    assert budget.calls_used == 1
    assert events[0].tool is None
    assert events[0].provider == "gateway"


@pytest.mark.asyncio
async def test_interpreter_rejects_malformed_or_unanchored_evidence() -> None:
    async def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {
                                    "relevance": "relevant",
                                    "company_candidates": [
                                        {
                                            "name": "Invented Corp",
                                            "domain": None,
                                            "evidence": [
                                                {
                                                    "field": "email_body",
                                                    "start": 0,
                                                    "end": 8,
                                                    "quote": "Invented",
                                                }
                                            ],
                                        }
                                    ],
                                    "contact_candidates": [],
                                    "stated_needs": [],
                                    "ambiguity_reasons": [],
                                    "unknowns": [],
                                }
                            ),
                            "tool_calls": [],
                        },
                    }
                ]
            },
        )

    payload = _input(body="No company named here.")
    executor = ToolExecutor(
        [],
        RunBudget(
            max_calls=2,
            max_attempts=1,
            max_concurrency=1,
            deadline_seconds=5,
        ),
    )
    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        agent = EmailInterpretationAgent(
            GatewayClient(_settings(), client),
            "configured-chat-model",
            executor,
        )
        with pytest.raises(ProviderCallError):
            await agent.interpret(payload, run_id=uuid4())


@pytest.mark.asyncio
async def test_interpreter_rejects_oversized_input_before_provider_call() -> None:
    budget = RunBudget(
        max_calls=1,
        max_attempts=1,
        max_concurrency=1,
        deadline_seconds=5,
    )
    executor = ToolExecutor([], budget)
    async with httpx2.AsyncClient() as client:
        agent = EmailInterpretationAgent(
            GatewayClient(_settings(), client), "configured-chat-model", executor
        )
        with pytest.raises(ProviderCallError) as error:
            await agent.interpret(_input(body="x" * 60_000), run_id=uuid4())
    assert error.value.category is ProviderErrorCategory.INVALID_REQUEST
    assert budget.calls_used == 0


def test_follow_up_intent_is_separate_from_meeting_relevance() -> None:
    interpretation = EmailInterpretation(
        relevance=EmailRelevance.UNCERTAIN,
        follow_up_intent=FollowUpIntent.REPLY,
        company_candidates=[],
        contact_candidates=[],
        stated_needs=[],
        ambiguity_reasons=[],
        unknowns=[],
    )
    assert interpretation.relevance is EmailRelevance.UNCERTAIN
    assert interpretation.follow_up_intent is FollowUpIntent.REPLY
    old = interpretation.model_dump()
    old.pop("follow_up_intent")
    assert EmailInterpretation.model_validate(old).follow_up_intent is None
