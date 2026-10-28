"""Typed provider, search, tool, and execution-evidence contracts."""

from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)


class ResearchContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ApprovedCompany(StrEnum):
    """Public company identities eligible for explicitly approved research."""

    MICROSOFT = "microsoft"
    SALESFORCE = "salesforce"
    ADOBE = "adobe"
    FPT_SOFTWARE = "fpt_software"
    VINAMILK = "vinamilk"
    SAMSUNG_VIETNAM = "samsung_vietnam"
    SHOPEE_VIETNAM = "shopee_vietnam"
    VIETTEL_SOLUTIONS = "viettel_solutions"
    BOSCH_VIETNAM = "bosch_vietnam"


APPROVED_COMPANY_NAMES = {
    ApprovedCompany.MICROSOFT: "Microsoft",
    ApprovedCompany.SALESFORCE: "Salesforce",
    ApprovedCompany.ADOBE: "Adobe",
    ApprovedCompany.FPT_SOFTWARE: "FPT Software",
    ApprovedCompany.VINAMILK: "Vinamilk",
    ApprovedCompany.SAMSUNG_VIETNAM: "Samsung Electronics Vietnam",
    ApprovedCompany.SHOPEE_VIETNAM: "Shopee Vietnam",
    ApprovedCompany.VIETTEL_SOLUTIONS: "Viettel Solutions",
    ApprovedCompany.BOSCH_VIETNAM: "Bosch Global Software Technologies Vietnam",
}


class SearchTopic(StrEnum):
    COMPANY_OVERVIEW = "company_overview"
    PRODUCTS_AND_SERVICES = "products_and_services"
    PUBLIC_NEWS = "public_news"


class ResearchRole(StrEnum):
    WEB_RESEARCH = "web_research"
    EMAIL_INTERPRETATION = "email_interpretation"
    SYNTHESIS = "synthesis"


class ToolName(StrEnum):
    WEB_SEARCH = "web_search"
    FETCH_SOURCE = "fetch_source"


class ProviderErrorCategory(StrEnum):
    INVALID_REQUEST = "invalid_request"
    AUTHENTICATION = "authentication"
    PERMISSION = "permission"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    FETCH_UNAVAILABLE = "fetch_unavailable"
    MALFORMED_RESPONSE = "malformed_response"
    TOOL_FAILURE = "tool_failure"
    BUDGET_EXHAUSTED = "budget_exhausted"


class ToolOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ChatRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class CompletionFinishReason(StrEnum):
    STOP = "stop"
    TOOL_CALLS = "tool_calls"
    LENGTH = "length"
    CONTENT_FILTER = "content_filter"


class ProviderUsage(ResearchContract):
    input_tokens: StrictInt | None = Field(default=None, ge=0)
    output_tokens: StrictInt | None = Field(default=None, ge=0)
    total_tokens: StrictInt | None = Field(default=None, ge=0)
    cost_usd: Decimal | None = Field(default=None, ge=0)
    provider_units: StrictInt | None = Field(default=None, ge=0)


class WebSearchInput(ResearchContract):
    company: ApprovedCompany
    topic: SearchTopic
    max_results: StrictInt = Field(default=3, ge=1, le=5)


class PublicResearchRequest(ResearchContract):
    company: ApprovedCompany
    topic: SearchTopic


class FetchSourceInput(ResearchContract):
    source_id: UUID


class SearchSourceReference(ResearchContract):
    id: UUID
    url: AnyHttpUrl
    title: str = Field(min_length=1, max_length=300)
    snippet: str = Field(max_length=2000)
    published_at: datetime | None = None

    @field_validator("published_at")
    @classmethod
    def publication_time_is_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("publication timestamps must be timezone-aware")
        return value


class WebSearchResult(ResearchContract):
    sources: list[SearchSourceReference] = Field(max_length=5)
    usage: ProviderUsage | None = None


class FetchResult(ResearchContract):
    source_id: UUID
    url: AnyHttpUrl
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=50_000)
    content_type: str = Field(min_length=1, max_length=100)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class EmbeddingVector(ResearchContract):
    index: StrictInt = Field(ge=0)
    values: list[float] = Field(min_length=1, max_length=8192)

    @field_validator("values")
    @classmethod
    def values_are_finite(cls, values: list[float]) -> list[float]:
        if any(not math.isfinite(value) for value in values):
            raise ValueError("embedding values must be finite")
        return values


class EmbeddingBatch(ResearchContract):
    model: str = Field(min_length=1, max_length=200)
    vectors: list[EmbeddingVector] = Field(min_length=1, max_length=128)
    usage: ProviderUsage | None = None

    @model_validator(mode="after")
    def indexes_and_dimensions_match(self) -> Self:
        indexes = [item.index for item in self.vectors]
        if indexes != list(range(len(self.vectors))):
            raise ValueError("embedding indexes must cover the input order exactly")
        dimensions = {len(item.values) for item in self.vectors}
        if len(dimensions) != 1:
            raise ValueError("embedding vector dimensions must match")
        return self


class ChatMessage(ResearchContract):
    role: ChatRole
    content: str = Field(max_length=100_000)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    tool_call_id: str | None = Field(default=None, min_length=1, max_length=100)


class ChatToolCall(ResearchContract):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, object]


class ToolMetadata(ResearchContract):
    name: ToolName
    description: str = Field(min_length=1, max_length=1000)
    arguments_schema: dict[str, object]
    result_schema: dict[str, object]


class ChatCompletionRequest(ResearchContract):
    model: str = Field(min_length=1, max_length=200)
    messages: list[ChatMessage] = Field(min_length=1, max_length=100)
    tools: list[ToolMetadata] | None = Field(default=None, max_length=10)
    response_schema: dict[str, object] | None = None
    max_output_tokens: StrictInt = Field(default=2048, ge=1, le=8192)


class ChatCompletion(ResearchContract):
    content: str | None = Field(default=None, max_length=100_000)
    tool_calls: list[ChatToolCall] = Field(default_factory=list, max_length=10)
    finish_reason: CompletionFinishReason

    @model_validator(mode="after")
    def response_matches_finish_reason(self) -> Self:
        if (
            self.finish_reason is CompletionFinishReason.TOOL_CALLS
            and not self.tool_calls
        ):
            raise ValueError("tool_calls finish reason requires tool calls")
        if self.finish_reason is CompletionFinishReason.STOP and self.tool_calls:
            raise ValueError("stop finish reason cannot include tool calls")
        if self.content is None and not self.tool_calls:
            raise ValueError("completion must contain content or a tool call")
        return self


class ChatCompletionResult(ResearchContract):
    completion: ChatCompletion
    usage: ProviderUsage | None = None


class ToolExecutionEvent(ResearchContract):
    id: UUID
    run_id: UUID
    parent_execution_id: UUID | None = None
    role: ResearchRole
    tool: ToolName | None
    provider: str = Field(min_length=1, max_length=100)
    model: str | None = Field(default=None, max_length=200)
    started_at: datetime
    duration_ms: StrictInt = Field(ge=0)
    attempt_count: StrictInt = Field(default=0, ge=0)
    outcome: ToolOutcome
    error_category: ProviderErrorCategory | None = None
    usage: ProviderUsage | None = None

    @field_validator("started_at")
    @classmethod
    def start_time_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("execution timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def failures_have_categories(self) -> Self:
        if self.outcome is ToolOutcome.FAILED and self.error_category is None:
            raise ValueError("failed executions require an error category")
        if self.outcome is ToolOutcome.SUCCEEDED and self.error_category is not None:
            raise ValueError("successful executions cannot have an error category")
        return self
