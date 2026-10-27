from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx2
import pytest

from email_support.integrations.llm_gateway import GatewayClient, ProviderCallError
from email_support.integrations.openrouter_embeddings import OpenRouterEmbeddings
from email_support.integrations.provider_http import post_json
from email_support.integrations.tavily import TavilySearch
from email_support.models.research import (
    ChatCompletionRequest,
    ChatMessage,
    ChatRole,
    ProviderErrorCategory,
    ProviderUsage,
    ToolMetadata,
    ToolName,
)
from email_support.research_config import ResearchSettings


def _settings() -> ResearchSettings:
    return ResearchSettings.from_environment(
        {
            "RESEARCH_GATEWAY_URL": "https://gateway.example/v1",
            "RESEARCH_GATEWAY_API_KEY": "gateway-secret",
            "RESEARCH_GATEWAY_MODEL": "configured-chat-model",
            "OPENROUTER_API_KEY": "router-secret",
            "OPENROUTER_EMBEDDING_MODEL": "configured-embedding-model",
            "TAVILY_API_KEY": "search-secret",
        }
    )


@pytest.mark.asyncio
async def test_gateway_authenticates_and_normalizes_tool_calls_and_usage() -> None:
    observed: dict[str, object] = {}

    async def handler(request: httpx2.Request) -> httpx2.Response:
        observed["url"] = str(request.url)
        observed["authorization"] = request.headers.get("authorization")
        payload = json.loads(request.content)
        observed["payload"] = payload
        observed["tool_parameters"] = payload["tools"][0]["function"]["parameters"]
        return httpx2.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "web_search",
                                        "arguments": (
                                            '{"company":"microsoft",'
                                            '"topic":"company_overview"}'
                                        ),
                                    },
                                }
                            ],
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 21,
                    "completion_tokens": 4,
                    "total_tokens": 25,
                },
            },
        )

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        gateway = GatewayClient(_settings(), client)
        result = await gateway.complete(
            ChatCompletionRequest(
                model="configured-chat-model",
                messages=[
                    ChatMessage(role=ChatRole.USER, content="Research Microsoft")
                ],
                tools=[
                    ToolMetadata(
                        name=ToolName.WEB_SEARCH,
                        description="Search public company information.",
                        arguments_schema={
                            "type": "object",
                            "properties": {"value": {"type": "string"}},
                            "required": ["value"],
                            "additionalProperties": False,
                        },
                        result_schema={"type": "object"},
                    )
                ],
            )
        )
    assert observed["url"] == "https://gateway.example/v1/chat/completions"
    assert observed["authorization"] == "Bearer gateway-secret"
    assert result.completion.tool_calls[0].name == "web_search"
    assert result.completion.tool_calls[0].arguments["company"] == "microsoft"
    assert result.usage is not None and result.usage.input_tokens == 21
    tool_parameters = observed["tool_parameters"]
    assert isinstance(tool_parameters, dict)
    assert tool_parameters["additionalProperties"] is False


@pytest.mark.asyncio
async def test_gateway_structured_output_keeps_unknown_usage_null() -> None:
    async def handler(request: httpx2.Request) -> httpx2.Response:
        payload = json.loads(request.content)
        assert payload["response_format"]["json_schema"]["strict"] is True
        return httpx2.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"ok":true}'},
                    }
                ]
            },
        )

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        result = await GatewayClient(_settings(), client).complete(
            ChatCompletionRequest(
                model="configured-chat-model",
                messages=[ChatMessage(role=ChatRole.USER, content="Return a result")],
                response_schema={
                    "type": "object",
                    "properties": {"ok": {"type": "boolean"}},
                },
            )
        )
    assert result.completion.content == '{"ok":true}'
    assert result.usage is None


@pytest.mark.asyncio
async def test_gateway_malformed_tool_arguments_fail_closed() -> None:
    async def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "function": {
                                        "name": "web_search",
                                        "arguments": "{private malformed payload",
                                    },
                                }
                            ],
                        },
                    }
                ]
            },
        )

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        with pytest.raises(ProviderCallError) as error:
            await GatewayClient(_settings(), client).complete(
                ChatCompletionRequest(
                    model="configured-chat-model",
                    messages=[ChatMessage(role=ChatRole.USER, content="Use tools")],
                )
            )
    assert error.value.category is ProviderErrorCategory.MALFORMED_RESPONSE


@pytest.mark.asyncio
async def test_provider_status_errors_are_categorized_without_body_leakage() -> None:
    async def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(401, text="private provider diagnostic body")

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        with pytest.raises(ProviderCallError) as error:
            await GatewayClient(_settings(), client).complete(
                ChatCompletionRequest(
                    model="configured-chat-model",
                    messages=[ChatMessage(role=ChatRole.USER, content="Hello")],
                )
            )
    assert error.value.category is ProviderErrorCategory.AUTHENTICATION
    assert "private provider diagnostic body" not in str(error.value)


@pytest.mark.parametrize(
    ("status", "category"),
    [
        (403, ProviderErrorCategory.PERMISSION),
        (429, ProviderErrorCategory.RATE_LIMITED),
        (503, ProviderErrorCategory.PROVIDER_UNAVAILABLE),
    ],
)
@pytest.mark.asyncio
async def test_provider_status_categories_and_transient_retry_metadata(
    status: int, category: ProviderErrorCategory
) -> None:
    async def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status,
            headers={"retry-after": "2"},
            text="private response body",
        )

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        with pytest.raises(ProviderCallError) as error:
            await post_json(
                client,
                "https://provider.example/api",
                "private-token",
                {},
                timeout_seconds=1,
                max_response_bytes=1024,
            )
    assert error.value.category is category
    expected_retry_after = (
        2
        if category
        in {
            ProviderErrorCategory.RATE_LIMITED,
            ProviderErrorCategory.PROVIDER_UNAVAILABLE,
        }
        else None
    )
    assert error.value.retry_after_seconds == expected_retry_after
    assert "private response body" not in str(error.value)


@pytest.mark.asyncio
async def test_provider_timeout_is_categorized_without_retry() -> None:
    async def handler(_request: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(1)
        return httpx2.Response(200, json={"ok": True})

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        with pytest.raises(ProviderCallError) as error:
            await post_json(
                client,
                "https://provider.example/api",
                "private-token",
                {},
                timeout_seconds=0.01,
                max_response_bytes=1024,
            )
    assert error.value.category is ProviderErrorCategory.TIMEOUT


@pytest.mark.asyncio
async def test_executor_metadata_preserves_known_usage() -> None:
    from pydantic import BaseModel, ConfigDict

    from email_support.models.research import ResearchRole, ToolExecutionEvent, ToolName
    from email_support.tools.execution import ResearchTool, RunBudget, ToolExecutor

    class Arguments(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)
        query: str

    class Result(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)
        usage: ProviderUsage

    async def search(_arguments: BaseModel) -> BaseModel:
        return Result(usage=ProviderUsage(input_tokens=3, total_tokens=3))

    event_list: list[ToolExecutionEvent] = []
    executor = ToolExecutor(
        [
            ResearchTool(
                name=ToolName.WEB_SEARCH,
                description="Search public information.",
                provider="gateway",
                model="configured-model",
                allowed_roles=frozenset({ResearchRole.WEB_RESEARCH}),
                argument_model=Arguments,
                result_model=Result,
                function=search,
            )
        ],
        RunBudget(max_calls=2, max_attempts=1, max_concurrency=1, deadline_seconds=1),
        events=event_list,
    )
    await executor.execute(
        "web_search",
        ResearchRole.WEB_RESEARCH,
        {"query": "public only"},
        run_id=__import__("uuid").uuid4(),
    )
    assert event_list[0].duration_ms >= 0
    assert event_list[0].usage is not None
    assert event_list[0].usage.input_tokens == 3


@pytest.mark.asyncio
async def test_embeddings_validate_order_dimensions_and_report_usage() -> None:
    async def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.headers["authorization"] == "Bearer router-secret"
        payload = json.loads(request.content)
        assert payload["input"] == ["first", "second"]
        return httpx2.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.3, 0.4]},
                    {"index": 0, "embedding": [0.1, 0.2]},
                ],
                "usage": {"prompt_tokens": 5, "total_tokens": 5},
            },
        )

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        result = await OpenRouterEmbeddings(_settings(), client).embed(
            ["first", "second"]
        )
    assert [vector.index for vector in result.vectors] == [0, 1]
    assert result.vectors[1].values == [0.3, 0.4]
    assert result.usage is not None and result.usage.output_tokens is None


@pytest.mark.asyncio
async def test_tavily_search_uses_bounded_typed_public_query() -> None:
    async def handler(request: httpx2.Request) -> httpx2.Response:
        assert str(request.url) == "https://api.tavily.com/search"
        assert request.headers["authorization"] == "Bearer search-secret"
        payload = json.loads(request.content)
        assert payload["max_results"] <= 5
        assert "PRIVATE-CANARY" not in payload["query"]
        return httpx2.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://www.microsoft.com/en-us/about",
                        "title": "About Microsoft",
                        "content": "A short public search snippet.",
                    }
                ]
            },
        )

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        from email_support.models.research import ApprovedCompany, SearchTopic

        result = await TavilySearch(_settings(), client).search(
            ApprovedCompany.MICROSOFT, SearchTopic.COMPANY_OVERVIEW, max_results=100
        )
    assert len(result.sources) == 1
    assert result.sources[0].title == "About Microsoft"
    assert result.usage is None


@pytest.mark.asyncio
async def test_provider_http_parses_bounded_retry_after_date() -> None:
    retry_at = format_datetime(datetime.now(UTC) + timedelta(seconds=2), usegmt=True)

    async def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(429, headers={"retry-after": retry_at}, text="private")

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
        with pytest.raises(ProviderCallError) as error:
            await post_json(
                client,
                "https://provider.example/api",
                "private-token",
                {"query": "private canary"},
                timeout_seconds=1,
                max_response_bytes=1024,
            )
    assert error.value.category is ProviderErrorCategory.RATE_LIMITED
    assert error.value.retry_after_seconds is not None
    assert 0 <= error.value.retry_after_seconds <= 2
    assert "private" not in str(error.value)


@pytest.mark.asyncio
async def test_provider_http_rejects_oversize_and_non_json_responses() -> None:
    async def oversized(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=b"x" * 20)

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(oversized)) as client:
        with pytest.raises(ProviderCallError) as error:
            await post_json(
                client,
                "https://provider.example/api",
                "token",
                {},
                timeout_seconds=1,
                max_response_bytes=10,
            )
    assert error.value.category is ProviderErrorCategory.MALFORMED_RESPONSE

    async def non_json(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=b"<private response>")

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(non_json)) as client:
        with pytest.raises(ProviderCallError) as error:
            await post_json(
                client,
                "https://provider.example/api",
                "token",
                {},
                timeout_seconds=1,
                max_response_bytes=1024,
            )
    assert error.value.category is ProviderErrorCategory.MALFORMED_RESPONSE
