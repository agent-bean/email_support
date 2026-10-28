"""Typed adapter for an OpenAI-compatible configured chat gateway."""

from __future__ import annotations

import json
from typing import cast

import httpx2
from pydantic import ValidationError

from email_support.integrations.provider_http import ProviderCallError, post_json
from email_support.models.research import (
    ChatCompletion,
    ChatCompletionRequest,
    ChatCompletionResult,
    ProviderErrorCategory,
    ProviderUsage,
)
from email_support.research_config import ResearchSettings


class GatewayClient:
    def __init__(self, settings: ResearchSettings, client: httpx2.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResult:
        if request.model != self._settings.gateway_model:
            raise ProviderCallError(ProviderErrorCategory.INVALID_REQUEST)
        payload: dict[str, object] = {
            "model": request.model,
            "messages": [
                message.model_dump(mode="json", exclude_none=True)
                for message in request.messages
            ],
            "max_tokens": request.max_output_tokens,
        }
        if request.tools is not None:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name.value,
                        "description": tool.description,
                        "parameters": tool.arguments_schema,
                        "strict": True,
                    },
                }
                for tool in request.tools
            ]
            payload["tool_choice"] = "auto"
        if request.response_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "research_response",
                    "strict": True,
                    "schema": request.response_schema,
                },
            }
        base = str(self._settings.gateway_base_url).rstrip("/")
        response = await post_json(
            self._client,
            f"{base}/chat/completions",
            self._settings.gateway_api_key.get_secret_value(),
            payload,
            timeout_seconds=self._settings.request_timeout_seconds,
            max_response_bytes=self._settings.max_provider_response_bytes,
        )
        try:
            choices = response["choices"]
            if not isinstance(choices, list) or len(choices) != 1:
                raise ValueError
            choice = choices[0]
            if not isinstance(choice, dict):
                raise ValueError
            message = choice["message"]
            if not isinstance(message, dict):
                raise ValueError
            content = message.get("content")
            if content is not None and not isinstance(content, str):
                raise ValueError
            raw_calls = message.get("tool_calls", [])
            if not isinstance(raw_calls, list):
                raise ValueError
            calls: list[dict[str, object]] = []
            for call in raw_calls:
                if not isinstance(call, dict) or not isinstance(
                    call.get("function"), dict
                ):
                    raise ValueError
                function = cast(dict[str, object], call["function"])
                raw_arguments = function.get("arguments")
                if isinstance(raw_arguments, str):
                    raw_arguments = json.loads(raw_arguments)
                if not isinstance(raw_arguments, dict):
                    raise ValueError
                calls.append(
                    {
                        "id": call.get("id"),
                        "name": function.get("name"),
                        "arguments": raw_arguments,
                    }
                )
            finish_reason = choice.get("finish_reason")
            if finish_reason == "tool_calls":
                finish_reason = "tool_calls"
            elif finish_reason == "stop":
                finish_reason = "stop"
            elif finish_reason == "length":
                finish_reason = "length"
            elif finish_reason == "content_filter":
                finish_reason = "content_filter"
            else:
                raise ValueError
            completion = ChatCompletion.model_validate(
                {
                    "content": content,
                    "tool_calls": calls,
                    "finish_reason": finish_reason,
                }
            )
            usage = _parse_usage(response.get("usage"))
            return ChatCompletionResult(completion=completion, usage=usage)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, ValidationError):
            raise ProviderCallError(ProviderErrorCategory.MALFORMED_RESPONSE) from None


def _parse_usage(value: object) -> ProviderUsage | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError
    return ProviderUsage(
        input_tokens=value.get("prompt_tokens"),
        output_tokens=value.get("completion_tokens"),
        total_tokens=value.get("total_tokens"),
    )


__all__ = ["GatewayClient", "ProviderCallError"]
