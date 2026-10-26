"""Bounded Google Workspace endpoint behavior and response minimization."""

import json
from collections import deque
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from email_support.integrations import google_workspace
from email_support.integrations.google_workspace import TokenProbeOutcome
from email_support.models.google_connection import GoogleConnectionFailure


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self.body = json.dumps(payload or {}).encode()

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        yield self.body


class FakeStream:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    async def __aenter__(self) -> FakeResponse:
        return self.response

    async def __aexit__(self, *_: object) -> None:
        return None


class FakeClient:
    def __init__(
        self, responses: deque[FakeResponse], calls: list[dict[str, Any]]
    ) -> None:
        self.responses = responses
        self.calls = calls

    async def __aenter__(self) -> "FakeClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def stream(self, method: str, url: str, **kwargs: Any) -> FakeStream:
        self.calls.append({"method": method, "url": url, **kwargs})
        return FakeStream(self.responses.popleft())


def fake_client_factory(
    responses: list[FakeResponse], calls: list[dict[str, Any]]
) -> Callable[..., FakeClient]:
    queued = deque(responses)
    return lambda **_: FakeClient(queued, calls)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (200, TokenProbeOutcome.ACCEPTED),
        (401, TokenProbeOutcome.REJECTED),
        (403, TokenProbeOutcome.INCONCLUSIVE),
    ],
)
async def test_direct_revocation_probe_only_treats_401_as_rejection(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    expected: TokenProbeOutcome,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        google_workspace,
        "AsyncClient",
        fake_client_factory([FakeResponse(status_code)], calls),
    )

    result = await google_workspace.GoogleWorkspaceClient().probe_gmail_access_token(
        "private-access-token"
    )

    assert result is expected
    assert calls[0]["url"].endswith("/messages")
    assert calls[0]["headers"] == {"Authorization": "Bearer private-access-token"}


@pytest.mark.asyncio
async def test_gmail_read_requests_one_message_metadata_without_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        google_workspace,
        "AsyncClient",
        fake_client_factory(
            [
                FakeResponse(200, {"messages": [{"id": "mail/id"}]}),
                FakeResponse(
                    200,
                    {
                        "id": "mail/id",
                        "threadId": "thread-id",
                        "payload": {
                            "headers": [
                                {"name": "Subject", "value": "Private subject"},
                                {"name": "To", "value": "ignored@example.test"},
                            ],
                            "body": {"data": "must-not-be-returned"},
                        },
                    },
                ),
            ],
            calls,
        ),
    )

    result = await google_workspace.GoogleWorkspaceClient().read_gmail_metadata(
        "private-access-token"
    )

    assert result is not None
    assert result.headers == (("Subject", "Private subject"),)
    assert "private-access-token" not in repr(result)
    assert calls[0]["url"].endswith("/messages")
    assert calls[0]["params"] == {"maxResults": 1, "fields": "messages(id)"}
    assert calls[0]["headers"] == {"Authorization": "Bearer private-access-token"}
    assert calls[1]["url"].endswith("/messages/mail%2Fid")
    assert calls[1]["params"]["format"] == "metadata"
    assert calls[1]["params"]["metadataHeaders"] == ["From", "Subject", "Date"]
    assert "body" not in calls[1]["params"]["fields"]
    assert "private-access-token" not in calls[0]["url"]


@pytest.mark.asyncio
async def test_calendar_chooses_secondary_calendar_and_limits_event_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        google_workspace,
        "AsyncClient",
        fake_client_factory(
            [
                FakeResponse(
                    200,
                    {
                        "items": [
                            {"id": "primary-id", "primary": True},
                            {"id": "shared@example.test", "primary": False},
                        ]
                    },
                ),
                FakeResponse(
                    200,
                    {
                        "items": [
                            {
                                "id": "event-id",
                                "summary": "Private event title",
                                "start": {"dateTime": "2026-10-27T10:00:00Z"},
                                "end": {"dateTime": "2026-10-27T11:00:00Z"},
                            }
                        ]
                    },
                ),
            ],
            calls,
        ),
    )

    result = await google_workspace.GoogleWorkspaceClient().read_secondary_calendar(
        "private-access-token", now=datetime(2026, 10, 26, tzinfo=UTC)
    )

    assert result.secondary_calendar_found
    assert result.event is not None
    assert "Private event title" not in repr(result)
    assert "private-access-token" not in repr(result)
    assert calls[0]["params"] == {
        "maxResults": 100,
        "fields": "items(id,primary)",
    }
    assert calls[1]["url"].endswith("/calendars/shared%40example.test/events")
    assert calls[1]["params"]["maxResults"] == 1
    assert "summary" not in calls[1]["params"]["fields"]
    assert "private-access-token" not in calls[1]["url"]


@pytest.mark.asyncio
async def test_refresh_invalid_grant_is_typed_without_echoing_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        google_workspace,
        "AsyncClient",
        fake_client_factory([FakeResponse(400, {"error": "invalid_grant"})], calls),
    )

    with pytest.raises(GoogleConnectionFailure) as failure:
        await google_workspace.GoogleWorkspaceClient().refresh(
            "private-refresh-token",
            client_id="client-id",
            client_secret="client-secret",
        )

    assert failure.value.code == "refresh_invalid"
    assert "private-refresh-token" not in str(failure.value)
    assert calls[0]["data"]["refresh_token"] == "private-refresh-token"
