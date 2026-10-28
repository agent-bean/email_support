"""Typed OpenRouter embeddings adapter."""

from __future__ import annotations

import httpx2
from pydantic import ValidationError

from email_support.integrations.provider_http import ProviderCallError, post_json
from email_support.models.research import (
    EmbeddingBatch,
    ProviderErrorCategory,
    ProviderUsage,
)
from email_support.research_config import ResearchSettings


class OpenRouterEmbeddings:
    def __init__(self, settings: ResearchSettings, client: httpx2.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    async def embed(self, inputs: list[str]) -> EmbeddingBatch:
        if (
            not inputs
            or len(inputs) > 128
            or any(not item or len(item) > 20_000 for item in inputs)
        ):
            raise ProviderCallError(ProviderErrorCategory.INVALID_REQUEST)
        response = await post_json(
            self._client,
            "https://openrouter.ai/api/v1/embeddings",
            self._settings.openrouter_api_key.get_secret_value(),
            {"model": self._settings.embedding_model, "input": inputs},
            timeout_seconds=self._settings.request_timeout_seconds,
            max_response_bytes=self._settings.max_provider_response_bytes,
        )
        try:
            data = response["data"]
            if not isinstance(data, list) or len(data) != len(inputs):
                raise ValueError
            if not all(isinstance(row, dict) for row in data):
                raise ValueError
            data.sort(key=lambda row: row.get("index", -1))
            vectors: list[dict[str, object]] = []
            for row in data:
                vectors.append({"index": row["index"], "values": row["embedding"]})
            usage_value = response.get("usage")
            usage = None
            if usage_value is not None:
                if not isinstance(usage_value, dict):
                    raise ValueError
                usage = ProviderUsage(
                    input_tokens=usage_value.get("prompt_tokens"),
                    output_tokens=usage_value.get("completion_tokens"),
                    total_tokens=usage_value.get("total_tokens"),
                )
            return EmbeddingBatch.model_validate(
                {
                    "model": response.get("model") or self._settings.embedding_model,
                    "vectors": vectors,
                    "usage": usage,
                }
            )
        except (KeyError, TypeError, ValueError, ValidationError):
            raise ProviderCallError(ProviderErrorCategory.MALFORMED_RESPONSE) from None
