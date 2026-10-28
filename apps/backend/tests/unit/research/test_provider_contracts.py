from __future__ import annotations

import pytest
from pydantic import ValidationError

from email_support.models.research import (
    ApprovedCompany,
    EmbeddingBatch,
    ProviderUsage,
    ResearchRole,
    SearchTopic,
    ToolName,
    WebSearchInput,
)
from email_support.research_config import ResearchConfigurationError, ResearchSettings


def test_tool_identities_contain_only_read_only_callable_operations() -> None:
    assert set(ToolName) == {ToolName.WEB_SEARCH, ToolName.FETCH_SOURCE}
    assert ResearchRole.WEB_RESEARCH.value == "web_research"


def test_search_input_uses_approved_public_company_and_closed_topic() -> None:
    request = WebSearchInput(
        company=ApprovedCompany.MICROSOFT,
        topic=SearchTopic.COMPANY_OVERVIEW,
    )
    assert request.company is ApprovedCompany.MICROSOFT
    with pytest.raises(ValidationError):
        WebSearchInput.model_validate(
            {
                "company": "unapproved_company",
                "topic": "company_overview",
                "query": "a private mailbox body",
            }
        )


def test_provider_usage_keeps_missing_values_unknown() -> None:
    usage = ProviderUsage()
    assert usage.input_tokens is None
    assert usage.output_tokens is None
    assert usage.cost_usd is None


def test_embedding_batch_rejects_non_finite_and_mismatched_vectors() -> None:
    with pytest.raises(ValidationError, match="finite"):
        EmbeddingBatch.model_validate(
            {
                "model": "configured-model",
                "vectors": [{"index": 0, "values": [0.1, float("nan")]}],
                "usage": None,
            }
        )
    with pytest.raises(ValidationError, match="dimension"):
        EmbeddingBatch.model_validate(
            {
                "model": "configured-model",
                "vectors": [
                    {"index": 0, "values": [0.1, 0.2]},
                    {"index": 1, "values": [0.3]},
                ],
                "usage": None,
            }
        )


def test_research_settings_require_all_provider_secrets_without_echoing_them() -> None:
    with pytest.raises(ResearchConfigurationError) as error:
        ResearchSettings.from_environment({})
    assert "RESEARCH_GATEWAY_API_KEY" in str(error.value)

    values = {
        "RESEARCH_GATEWAY_URL": "https://gateway.example/v1",
        "RESEARCH_GATEWAY_API_KEY": "gateway-secret",
        "RESEARCH_GATEWAY_MODEL": "model-id",
        "OPENROUTER_API_KEY": "router-secret",
        "OPENROUTER_EMBEDDING_MODEL": "embedding-id",
        "TAVILY_API_KEY": "search-secret",
    }
    settings = ResearchSettings.from_environment(values)
    assert "gateway-secret" not in repr(settings)
    assert "router-secret" not in repr(settings)
    assert "search-secret" not in repr(settings)
