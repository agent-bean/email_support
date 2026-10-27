from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from email_support.integrations.provider_http import ProviderCallError
from email_support.models.research import (
    ProviderErrorCategory,
    ResearchRole,
    ToolExecutionEvent,
    ToolName,
    ToolOutcome,
)
from email_support.tools.execution import (
    ResearchTool,
    RunBudget,
    ToolExecutor,
    ToolFunction,
)


class _Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    value: str = Field(min_length=1, max_length=20)


class _Result(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    value: str


def _tool(
    function: ToolFunction, roles: frozenset[ResearchRole] | None = None
) -> ResearchTool:
    return ResearchTool(
        name=ToolName.WEB_SEARCH,
        description="Search public company information.",
        provider="test-provider",
        model="test-model",
        allowed_roles=roles or frozenset({ResearchRole.WEB_RESEARCH}),
        argument_model=_Arguments,
        result_model=_Result,
        function=function,
    )


def _budget(max_calls: int = 8, max_attempts: int = 2) -> RunBudget:
    return RunBudget(
        max_calls=max_calls,
        max_attempts=max_attempts,
        max_concurrency=2,
        deadline_seconds=2,
    )


@pytest.mark.asyncio
async def test_unknown_tool_extra_arguments_and_denied_role_never_dispatch() -> None:
    invoked = False

    async def call(_args: BaseModel) -> BaseModel:
        nonlocal invoked
        invoked = True
        return _Result(value="ok")

    events: list[ToolExecutionEvent] = []
    executor = ToolExecutor([_tool(call)], _budget(), events=events)
    assert executor.metadata(ResearchRole.EMAIL_INTERPRETATION) == []
    with pytest.raises(ProviderCallError) as unknown:
        await executor.execute("approve", ResearchRole.WEB_RESEARCH, {}, run_id=uuid4())
    assert unknown.value.category is ProviderErrorCategory.INVALID_REQUEST
    for role in (ResearchRole.EMAIL_INTERPRETATION, ResearchRole.SYNTHESIS):
        with pytest.raises(ProviderCallError) as denied:
            await executor.execute("web_search", role, {"value": "x"}, run_id=uuid4())
        assert denied.value.category is ProviderErrorCategory.PERMISSION
    with pytest.raises(ProviderCallError):
        await executor.execute(
            "web_search",
            ResearchRole.WEB_RESEARCH,
            {"value": "x", "secret": "mail"},
            run_id=uuid4(),
        )
    assert invoked is False
    assert "secret" not in str(events)
    assert "PRIVATE-CANARY" not in str(events)


@pytest.mark.asyncio
async def test_public_research_prompt_cannot_accept_or_leak_private_context() -> None:
    from email_support.models.research import (
        ApprovedCompany,
        ChatCompletion,
        ChatCompletionRequest,
        ChatCompletionResult,
        CompletionFinishReason,
        PublicResearchRequest,
        SearchTopic,
    )
    from email_support.tools.research import request_public_research

    captured: list[ChatCompletionRequest] = []

    class Gateway:
        async def complete(
            self, request: ChatCompletionRequest
        ) -> ChatCompletionResult:
            captured.append(request)
            return ChatCompletionResult(
                completion=ChatCompletion(
                    content="Ready to search.",
                    finish_reason=CompletionFinishReason.STOP,
                )
            )

    async def call(_args: BaseModel) -> BaseModel:
        return _Result(value="ok")

    executor = ToolExecutor([_tool(call)], _budget())
    with pytest.raises(ValidationError):
        PublicResearchRequest.model_validate(
            {
                "company": "microsoft",
                "topic": "company_overview",
                "private_email": "PRIVATE-CANARY",
            }
        )
    await request_public_research(
        Gateway(),
        "configured-model",
        PublicResearchRequest(
            company=ApprovedCompany.MICROSOFT,
            topic=SearchTopic.COMPANY_OVERVIEW,
        ),
        executor,
        run_id=uuid4(),
    )
    request = captured[0]
    serialized = request.model_dump_json()
    assert "PRIVATE-CANARY" not in serialized
    assert "Microsoft" in serialized


@pytest.mark.asyncio
async def test_public_gateway_call_uses_shared_budget_and_trace() -> None:
    from email_support.models.research import (
        ApprovedCompany,
        ChatCompletion,
        ChatCompletionRequest,
        ChatCompletionResult,
        CompletionFinishReason,
        ProviderUsage,
        PublicResearchRequest,
        SearchTopic,
    )
    from email_support.tools.research import request_public_research

    class Gateway:
        async def complete(
            self, request: ChatCompletionRequest
        ) -> ChatCompletionResult:
            return ChatCompletionResult(
                completion=ChatCompletion(
                    content="Ready", finish_reason=CompletionFinishReason.STOP
                ),
                usage=ProviderUsage(input_tokens=12, output_tokens=3),
            )

    async def unused(_args: BaseModel) -> BaseModel:
        raise AssertionError("no tools should execute in this test")

    budget = _budget(max_calls=1)
    events: list[ToolExecutionEvent] = []
    executor = ToolExecutor([_tool(unused)], budget, events=events)
    run_id = uuid4()
    result = await request_public_research(
        Gateway(),
        "configured-model",
        PublicResearchRequest(
            company=ApprovedCompany.MICROSOFT,
            topic=SearchTopic.COMPANY_OVERVIEW,
        ),
        executor,
        run_id=run_id,
    )
    assert result.usage is not None
    assert budget.calls_used == 1
    assert budget.attempts_used == 1
    assert events[0].run_id == run_id
    assert events[0].provider == "gateway"
    assert events[0].model == "configured-model"
    assert events[0].usage == result.usage


@pytest.mark.asyncio
async def test_executor_retries_transient_failure_with_shared_attempt_budget() -> None:
    invocations = 0
    sleeps: list[float] = []

    async def call(_args: BaseModel) -> BaseModel:
        nonlocal invocations
        invocations += 1
        if invocations == 1:
            raise ProviderCallError(
                ProviderErrorCategory.RATE_LIMITED, retry_after_seconds=0
            )
        return _Result(value="ok")

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    budget = _budget()
    events: list[ToolExecutionEvent] = []
    executor = ToolExecutor(
        [_tool(call)], budget, events=events, sleep=sleep, jitter=lambda: 0
    )
    result = await executor.execute(
        "web_search", ResearchRole.WEB_RESEARCH, {"value": "public"}, run_id=uuid4()
    )
    assert result == _Result(value="ok")
    assert invocations == 2
    assert budget.calls_used == 1
    assert budget.attempts_used == 2
    assert sleeps == [0.125]
    assert events[0].attempt_count == 2
    assert events[0].outcome is ToolOutcome.SUCCEEDED
    assert not hasattr(events[0], "arguments")


@pytest.mark.asyncio
async def test_executor_does_not_retry_ambiguous_timeout_or_hide_cancellation() -> None:
    invocations = 0

    async def timeout(_args: BaseModel) -> BaseModel:
        nonlocal invocations
        invocations += 1
        raise ProviderCallError(ProviderErrorCategory.TIMEOUT)

    executor = ToolExecutor([_tool(timeout)], _budget())
    with pytest.raises(ProviderCallError) as error:
        await executor.execute(
            "web_search", ResearchRole.WEB_RESEARCH, {"value": "x"}, run_id=uuid4()
        )
    assert error.value.category is ProviderErrorCategory.TIMEOUT
    assert invocations == 1

    async def cancelled(_args: BaseModel) -> BaseModel:
        raise asyncio.CancelledError

    events: list[ToolExecutionEvent] = []
    executor = ToolExecutor([_tool(cancelled)], _budget(), events=events)
    with pytest.raises(asyncio.CancelledError):
        await executor.execute(
            "web_search", ResearchRole.WEB_RESEARCH, {"value": "x"}, run_id=uuid4()
        )
    assert events[0].error_category is ProviderErrorCategory.CANCELLED


@pytest.mark.asyncio
async def test_budget_stops_dispatch_at_call_and_attempt_limits() -> None:
    invocations = 0

    async def call(_args: BaseModel) -> BaseModel:
        nonlocal invocations
        invocations += 1
        return _Result(value="ok")

    executor = ToolExecutor([_tool(call)], _budget(max_calls=1))
    run_id = uuid4()
    await executor.execute(
        "web_search", ResearchRole.WEB_RESEARCH, {"value": "x"}, run_id=run_id
    )
    with pytest.raises(ProviderCallError) as error:
        await executor.execute(
            "web_search", ResearchRole.WEB_RESEARCH, {"value": "x"}, run_id=run_id
        )
    assert error.value.category is ProviderErrorCategory.BUDGET_EXHAUSTED
    assert invocations == 1


@pytest.mark.asyncio
async def test_invalid_result_and_schema_metadata_are_checked() -> None:
    async def invalid(_args: BaseModel) -> BaseModel:
        return _Arguments(value="wrong result type")

    tool = _tool(invalid)
    metadata = tool.metadata()
    assert metadata.name is ToolName.WEB_SEARCH
    assert metadata.arguments_schema["additionalProperties"] is False
    executor = ToolExecutor([tool], _budget())
    with pytest.raises(ProviderCallError) as error:
        await executor.execute(
            "web_search", ResearchRole.WEB_RESEARCH, {"value": "x"}, run_id=uuid4()
        )
    assert error.value.category is ProviderErrorCategory.MALFORMED_RESPONSE


@pytest.mark.asyncio
async def test_public_toolset_scopes_companies_and_source_ids_per_run() -> None:
    from email_support.models.research import (
        ApprovedCompany,
        FetchResult,
        ProviderUsage,
        SearchSourceReference,
        SearchTopic,
        WebSearchInput,
        WebSearchResult,
    )
    from email_support.tools.research import build_research_tools

    source_id = uuid4()
    observed_search: list[tuple[ApprovedCompany, SearchTopic]] = []
    fetched: list[tuple[str, object]] = []

    class Search:
        async def search(
            self, company: ApprovedCompany, topic: SearchTopic, *, max_results: int
        ) -> WebSearchResult:
            observed_search.append((company, topic))
            assert max_results <= 5
            return WebSearchResult(
                sources=[
                    SearchSourceReference.model_validate(
                        {
                            "id": source_id,
                            "url": "https://www.microsoft.com/about",
                            "title": "About",
                            "snippet": "Public overview",
                        }
                    )
                ],
                usage=ProviderUsage(),
            )

    class Fetch:
        async def fetch(self, url: str, *, source_id: UUID) -> FetchResult:
            fetched.append((url, source_id))
            return FetchResult.model_validate(
                {
                    "source_id": source_id,
                    "url": url,
                    "title": "About",
                    "text": "Public page",
                    "content_type": "text/html",
                    "content_sha256": "0" * 64,
                }
            )

    tools, registry = build_research_tools(
        Search(),
        Fetch(),
        approved_companies=frozenset({ApprovedCompany.MICROSOFT}),
    )
    events: list[ToolExecutionEvent] = []
    executor = ToolExecutor(tools, _budget(), events=events)
    run_id = uuid4()
    with pytest.raises(ProviderCallError) as denied:
        await executor.execute(
            "web_search",
            ResearchRole.WEB_RESEARCH,
            {"company": "adobe", "topic": "company_overview"},
            run_id=run_id,
        )
    assert denied.value.category is ProviderErrorCategory.PERMISSION
    assert observed_search == []

    search_result = await executor.execute(
        "web_search",
        ResearchRole.WEB_RESEARCH,
        WebSearchInput(
            company=ApprovedCompany.MICROSOFT,
            topic=SearchTopic.COMPANY_OVERVIEW,
        ).model_dump(mode="json"),
        run_id=run_id,
    )
    assert isinstance(search_result, WebSearchResult)
    with pytest.raises(ProviderCallError):
        await executor.execute(
            "fetch_source",
            ResearchRole.WEB_RESEARCH,
            {"source_id": str(uuid4())},
            run_id=run_id,
        )
    fetched_result = await executor.execute(
        "fetch_source",
        ResearchRole.WEB_RESEARCH,
        {"source_id": str(source_id)},
        run_id=run_id,
    )
    assert isinstance(fetched_result, FetchResult)
    assert fetched == [("https://www.microsoft.com/about", source_id)]
    assert registry.resolve(source_id) == "https://www.microsoft.com/about"
