"""Tavily basic-search adapter with application-built public queries."""

from __future__ import annotations

from uuid import uuid4

import httpx2
from pydantic import ValidationError

from email_support.integrations.provider_http import ProviderCallError, post_json
from email_support.models.research import (
    APPROVED_COMPANY_NAMES,
    ApprovedCompany,
    ProviderErrorCategory,
    ProviderUsage,
    SearchSourceReference,
    SearchTopic,
    WebSearchResult,
)
from email_support.research_config import ResearchSettings

_TOPIC_TEXT = {
    SearchTopic.COMPANY_OVERVIEW: "company overview",
    SearchTopic.PRODUCTS_AND_SERVICES: "products and services",
    SearchTopic.PUBLIC_NEWS: "recent public news",
}


class TavilySearch:
    def __init__(self, settings: ResearchSettings, client: httpx2.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    async def search(
        self,
        company: ApprovedCompany,
        topic: SearchTopic,
        *,
        max_results: int = 3,
    ) -> WebSearchResult:
        if not isinstance(company, ApprovedCompany) or not isinstance(
            topic, SearchTopic
        ):
            raise ProviderCallError(ProviderErrorCategory.INVALID_REQUEST)
        bounded_results = min(max(max_results, 1), self._settings.max_search_results)
        query = f"{APPROVED_COMPANY_NAMES[company]} {_TOPIC_TEXT[topic]}"
        response = await post_json(
            self._client,
            "https://api.tavily.com/search",
            self._settings.tavily_api_key.get_secret_value(),
            {
                "query": query,
                "search_depth": "basic",
                "max_results": bounded_results,
                "include_answer": False,
                "include_raw_content": False,
            },
            timeout_seconds=self._settings.request_timeout_seconds,
            max_response_bytes=self._settings.max_provider_response_bytes,
        )
        try:
            raw_results = response["results"]
            if not isinstance(raw_results, list) or len(raw_results) > bounded_results:
                raise ValueError
            sources: list[SearchSourceReference] = []
            for row in raw_results:
                if not isinstance(row, dict):
                    raise ValueError
                sources.append(
                    SearchSourceReference(
                        id=uuid4(),
                        url=row["url"],
                        title=row["title"],
                        snippet=row.get("content", ""),
                    )
                )
            usage_data = response.get("usage")
            usage = None
            if isinstance(usage_data, dict) and usage_data.get("credits") is not None:
                usage = ProviderUsage(provider_units=usage_data.get("credits"))
            return WebSearchResult(sources=sources, usage=usage)
        except (KeyError, TypeError, ValueError, ValidationError):
            raise ProviderCallError(ProviderErrorCategory.MALFORMED_RESPONSE) from None
