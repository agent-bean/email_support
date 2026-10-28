"""Bounded public-only research with approved company and topics."""

from datetime import UTC, datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from email_support.integrations.provider_http import ProviderCallError
from email_support.models.research import (
    ApprovedCompany,
    FetchResult,
    ResearchRole,
    SearchTopic,
    ToolName,
    WebSearchResult,
)
from email_support.tools.execution import ToolExecutor


class ApprovedResearch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    company: ApprovedCompany
    topics: list[SearchTopic] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def distinct_topics(self) -> Self:
        if len(self.topics) != len(set(self.topics)):
            raise ValueError("duplicate research topic")
        return self


class ResearchOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sources: list[FetchResult]
    gaps: list[str]
    retrieved_at: datetime


async def research_public(
    request: ApprovedResearch, executor: ToolExecutor, run_id: UUID
) -> ResearchOutput:
    sources: list[FetchResult] = []
    gaps: list[str] = []
    seen: set[UUID] = set()
    for topic in request.topics:
        try:
            result = await executor.execute(
                ToolName.WEB_SEARCH.value,
                ResearchRole.WEB_RESEARCH,
                {
                    "company": request.company.value,
                    "topic": topic.value,
                    "max_results": 3,
                },
                run_id=run_id,
            )
            if not isinstance(result, WebSearchResult):
                raise ValueError("search result has wrong type")
        except ProviderCallError as error:
            gaps.append(f"{topic.value}: {error.category.value}")
            continue
        if not result.sources:
            gaps.append(f"{topic.value}: no sources")
        for source in result.sources:
            if source.id in seen:
                continue
            seen.add(source.id)
            try:
                fetched = await executor.execute(
                    ToolName.FETCH_SOURCE.value,
                    ResearchRole.WEB_RESEARCH,
                    {"source_id": str(source.id)},
                    run_id=run_id,
                )
                if not isinstance(fetched, FetchResult):
                    raise ValueError("fetch result has wrong type")
                sources.append(fetched)
            except ProviderCallError as error:
                gaps.append(f"{source.id}: {error.category.value}")
    return ResearchOutput(sources=sources, gaps=gaps, retrieved_at=datetime.now(UTC))
