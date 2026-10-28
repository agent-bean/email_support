"""Shared bounded JSON transport and safe provider failure categories."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import cast

import httpx2

from email_support.models.research import ProviderErrorCategory


@dataclass(slots=True)
class ProviderCallError(Exception):
    category: ProviderErrorCategory
    retry_after_seconds: float | None = None

    def __str__(self) -> str:
        return self.category.value


async def post_json(
    client: httpx2.AsyncClient,
    url: str,
    api_key: str,
    payload: dict[str, object],
    *,
    timeout_seconds: float,
    max_response_bytes: int,
) -> dict[str, object]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        async with asyncio.timeout(timeout_seconds):
            async with client.stream(
                "POST", url, headers=headers, json=payload
            ) as response:
                if response.status_code < 200 or response.status_code >= 300:
                    raise _status_error(response)
                content_length = response.headers.get("content-length")
                if content_length is not None:
                    try:
                        if int(content_length) > max_response_bytes:
                            raise ProviderCallError(
                                ProviderErrorCategory.MALFORMED_RESPONSE
                            )
                    except ValueError:
                        raise ProviderCallError(
                            ProviderErrorCategory.MALFORMED_RESPONSE
                        ) from None
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > max_response_bytes:
                        raise ProviderCallError(
                            ProviderErrorCategory.MALFORMED_RESPONSE
                        )
                if not content:
                    raise ProviderCallError(ProviderErrorCategory.MALFORMED_RESPONSE)
    except ProviderCallError:
        raise
    except (TimeoutError, httpx2.TimeoutException):
        raise ProviderCallError(ProviderErrorCategory.TIMEOUT) from None
    except httpx2.RequestError:
        raise ProviderCallError(ProviderErrorCategory.PROVIDER_UNAVAILABLE) from None

    try:
        value = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProviderCallError(ProviderErrorCategory.MALFORMED_RESPONSE) from None
    if not isinstance(value, dict):
        raise ProviderCallError(ProviderErrorCategory.MALFORMED_RESPONSE)
    return cast(dict[str, object], value)


def _status_error(response: httpx2.Response) -> ProviderCallError:
    if response.status_code == 401:
        return ProviderCallError(ProviderErrorCategory.AUTHENTICATION)
    if response.status_code == 403:
        return ProviderCallError(ProviderErrorCategory.PERMISSION)
    if response.status_code == 429:
        return ProviderCallError(
            ProviderErrorCategory.RATE_LIMITED,
            retry_after_seconds=_retry_after(response.headers.get("retry-after")),
        )
    if response.status_code >= 500:
        return ProviderCallError(
            ProviderErrorCategory.PROVIDER_UNAVAILABLE,
            retry_after_seconds=_retry_after(response.headers.get("retry-after")),
        )
    return ProviderCallError(ProviderErrorCategory.INVALID_REQUEST)


def _retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return min(max(float(value), 0.0), 5.0)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        return min(max((retry_at - datetime.now(UTC)).total_seconds(), 0.0), 5.0)
