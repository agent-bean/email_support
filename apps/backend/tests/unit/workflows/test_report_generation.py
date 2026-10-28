import json
from uuid import uuid4

import pytest

from email_support.agents.report_generation import (
    SynthesisEvidence,
    SynthesisInput,
    generate_report,
)
from email_support.integrations.provider_http import ProviderCallError
from email_support.models.research import (
    ChatCompletion,
    ChatCompletionRequest,
    ChatCompletionResult,
    CompletionFinishReason,
)
from email_support.tools.execution import RunBudget, ToolExecutor


class Gateway:
    def __init__(self, kind: str) -> None:
        self.kind = kind

    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResult:
        assert request.tools is None
        content = json.dumps(
            {
                "claims": [
                    {
                        "id": "claim",
                        "kind": self.kind,
                        "text": "A claim",
                        "evidence_ids": ["email"],
                    }
                ]
            }
        )
        return ChatCompletionResult(
            completion=ChatCompletion(
                content=content, finish_reason=CompletionFinishReason.STOP
            )
        )


def executor() -> ToolExecutor:
    return ToolExecutor(
        [],
        RunBudget(max_calls=2, max_attempts=1, max_concurrency=1, deadline_seconds=5),
    )


@pytest.mark.asyncio
async def test_sender_statement_can_be_recorded_as_need() -> None:
    report = await generate_report(
        Gateway("need"),
        "model",
        executor(),
        SynthesisInput(
            evidence=[
                SynthesisEvidence(id="email", content="please discuss", origin="email")
            ],
            gaps=[],
        ),
        uuid4(),
    )
    assert report.claims[0].kind.value == "need"


@pytest.mark.asyncio
async def test_sender_statement_cannot_be_promoted_to_company_fact() -> None:
    with pytest.raises(ProviderCallError):
        await generate_report(
            Gateway("fact"),
            "model",
            executor(),
            SynthesisInput(
                evidence=[
                    SynthesisEvidence(id="email", content="unverified", origin="email")
                ],
                gaps=[],
            ),
            uuid4(),
        )


@pytest.mark.asyncio
async def test_invalid_claim_is_retried_within_the_call_budget() -> None:
    class CorrectingGateway(Gateway):
        def __init__(self) -> None:
            super().__init__("fact")
            self.calls = 0

        async def complete(
            self, request: ChatCompletionRequest
        ) -> ChatCompletionResult:
            self.calls += 1
            if self.calls == 2:
                self.kind = "need"
                assert "failed validation" in request.messages[-1].content
            return await super().complete(request)

    gateway = CorrectingGateway()
    report = await generate_report(
        gateway,
        "model",
        executor(),
        SynthesisInput(
            evidence=[
                SynthesisEvidence(id="email", content="please discuss", origin="email")
            ],
            gaps=[],
        ),
        uuid4(),
    )
    assert gateway.calls == 2
    assert report.claims[0].kind.value == "need"
