"""Read-only web search and invocation-scoped source fetching tools."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from pydantic import BaseModel

from email_support.integrations.provider_http import ProviderCallError
from email_support.models.research import (
    APPROVED_COMPANY_NAMES,
    ApprovedCompany,
    ChatCompletionRequest,
    ChatCompletionResult,
    ChatMessage,
    ChatRole,
    FetchResult,
    FetchSourceInput,
    ProviderErrorCategory,
    PublicResearchRequest,
    ResearchRole,
    SearchTopic,
    ToolName,
    WebSearchInput,
    WebSearchResult,
)
from email_support.tools.execution import ResearchTool, ToolExecutor


class ResearchGateway(Protocol):
    async def complete(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResult: ...


_TOPIC_NAMES = {
    SearchTopic.COMPANY_OVERVIEW: "company overview",
    SearchTopic.PRODUCTS_AND_SERVICES: "products and services",
    SearchTopic.PUBLIC_NEWS: "public news",
}


async def request_public_research(
    gateway: ResearchGateway,
    model: str,
    request: PublicResearchRequest,
    executor: ToolExecutor,
    *,
    run_id: UUID,
) -> ChatCompletionResult:
    """Build the research model context only from approved public identifiers."""
    company = APPROVED_COMPANY_NAMES[request.company]
    topic = _TOPIC_NAMES[request.topic]
    chat_request = ChatCompletionRequest(
        model=model,
        messages=[
            ChatMessage(
                role=ChatRole.SYSTEM,
                content=(
                    "You are a public web research role. Use only the provided "
                    "read-only research tools. Do not request or disclose private "
                    "emails, meetings, contact data, or internal knowledge."
                ),
            ),
            ChatMessage(
                role=ChatRole.USER,
                content=f"Research the public {topic} for {company}.",
            ),
        ],
        tools=executor.metadata(ResearchRole.WEB_RESEARCH),
        max_output_tokens=1024,
    )
    result = await executor.execute_provider_call(
        lambda: gateway.complete(chat_request),
        role=ResearchRole.WEB_RESEARCH,
        provider="gateway",
        model=model,
        run_id=run_id,
    )
    if not isinstance(result, ChatCompletionResult):
        raise ProviderCallError(ProviderErrorCategory.MALFORMED_RESPONSE)
    return result


class SourceRegistry:
    """Maps provider-returned source IDs to URLs for one workflow invocation."""

    def __init__(self) -> None:
        self._sources: dict[UUID, str] = {}

    def register(self, result: WebSearchResult) -> None:
        for source in result.sources:
            self._sources[source.id] = str(source.url)

    def resolve(self, source_id: UUID) -> str:
        try:
            return self._sources[source_id]
        except KeyError:
            raise ProviderCallError(ProviderErrorCategory.INVALID_REQUEST) from None


class SearchAdapter(Protocol):
    async def search(
        self, company: ApprovedCompany, topic: SearchTopic, *, max_results: int
    ) -> WebSearchResult: ...


class FetchAdapter(Protocol):
    async def fetch(self, url: str, *, source_id: UUID) -> FetchResult: ...


def build_research_tools(
    search: SearchAdapter,
    fetcher: FetchAdapter,
    *,
    approved_companies: frozenset[ApprovedCompany],
) -> tuple[list[ResearchTool], SourceRegistry]:
    registry = SourceRegistry()

    async def web_search(arguments: BaseModel) -> BaseModel:
        if not isinstance(arguments, WebSearchInput):
            raise ProviderCallError(ProviderErrorCategory.INVALID_REQUEST)
        if arguments.company not in approved_companies:
            raise ProviderCallError(ProviderErrorCategory.PERMISSION)
        result = await search.search(
            arguments.company, arguments.topic, max_results=arguments.max_results
        )
        registry.register(result)
        return result

    async def fetch_source(arguments: BaseModel) -> BaseModel:
        if not isinstance(arguments, FetchSourceInput):
            raise ProviderCallError(ProviderErrorCategory.INVALID_REQUEST)
        url = registry.resolve(arguments.source_id)
        return await fetcher.fetch(url, source_id=arguments.source_id)

    roles = frozenset({ResearchRole.WEB_RESEARCH})
    tools = [
        ResearchTool(
            name=ToolName.WEB_SEARCH,
            description="Search approved public company information by topic.",
            provider="tavily",
            model=None,
            allowed_roles=roles,
            argument_model=WebSearchInput,
            result_model=WebSearchResult,
            function=web_search,
        ),
        ResearchTool(
            name=ToolName.FETCH_SOURCE,
            description="Fetch a source returned earlier in this research run.",
            provider="public_web",
            model=None,
            allowed_roles=roles,
            argument_model=FetchSourceInput,
            result_model=FetchResult,
            function=fetch_source,
        ),
    ]
    return tools, registry
