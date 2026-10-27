"""Small, bounded Google Workspace HTTP operations for connection checks."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from urllib.parse import quote

from httpx2 import AsyncClient, Timeout

from email_support.models.google_connection import (
    GoogleConnectionFailure,
    GoogleTokenBundle,
)

TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
REVOKE_ENDPOINT = "https://oauth2.googleapis.com/revoke"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
CALENDAR_API = "https://www.googleapis.com/calendar/v3"
HTTP_TIMEOUT_SECONDS = 8.0
MAX_RESPONSE_BYTES = 262_144


class TokenProbeOutcome(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, slots=True)
class GoogleRefreshResult:
    token_bundle: GoogleTokenBundle = field(repr=False)

    def __repr__(self) -> str:
        return "GoogleRefreshResult(token_bundle=...)"


@dataclass(frozen=True, slots=True)
class GmailMessageMetadata:
    message_id: str = field(repr=False)
    thread_id: str | None = field(repr=False)
    headers: tuple[tuple[str, str], ...] = field(repr=False)

    def __repr__(self) -> str:
        return "GmailMessageMetadata(message_id=..., thread_id=..., headers=...)"


@dataclass(frozen=True, slots=True)
class CalendarEventSummary:
    event_id: str = field(repr=False)
    start: str | None = field(repr=False)
    end: str | None = field(repr=False)

    def __repr__(self) -> str:
        return "CalendarEventSummary(event_id=..., start=..., end=...)"


@dataclass(frozen=True, slots=True)
class CalendarReadResult:
    secondary_calendar_found: bool
    event: CalendarEventSummary | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class GoogleReadSummary:
    gmail_read_succeeded: bool
    secondary_calendar_found: bool
    calendar_read_succeeded: bool
    calendar_event_found: bool


class GoogleWorkspaceClient:
    """Calls only the fixed Google endpoints needed for phase 3 verification."""

    async def refresh(
        self,
        refresh_token: str,
        *,
        client_id: str,
        client_secret: str,
        now: datetime | None = None,
    ) -> GoogleRefreshResult:
        try:
            async with AsyncClient(
                timeout=Timeout(HTTP_TIMEOUT_SECONDS), follow_redirects=False
            ) as client:
                status_code, payload = await _request_json(
                    client,
                    "POST",
                    TOKEN_ENDPOINT,
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                    },
                )
            if status_code >= 400:
                if payload.get("error") == "invalid_grant":
                    raise GoogleConnectionFailure("refresh_invalid")
                raise GoogleConnectionFailure("provider_unavailable")
            access_token = payload.get("access_token")
            token_type = payload.get("token_type", "Bearer")
            expires_in = payload.get("expires_in")
            rotated_refresh = payload.get("refresh_token")
            if (
                not isinstance(access_token, str)
                or not access_token
                or not isinstance(token_type, str)
                or token_type.lower() != "bearer"
                or type(expires_in) is not int
                or not 0 < expires_in <= 86_400
                or (
                    rotated_refresh is not None
                    and (not isinstance(rotated_refresh, str) or not rotated_refresh)
                )
            ):
                raise GoogleConnectionFailure("provider_unavailable")
            origin = datetime.now(UTC) if now is None else now
            if origin.tzinfo is None:
                raise GoogleConnectionFailure("provider_unavailable")
            return GoogleRefreshResult(
                GoogleTokenBundle(
                    access_token=access_token,
                    refresh_token=rotated_refresh,
                    access_expires_at=origin + timedelta(seconds=expires_in),
                )
            )
        except GoogleConnectionFailure:
            raise
        except Exception:
            raise GoogleConnectionFailure("provider_unavailable") from None

    async def revoke(self, token: str) -> bool:
        try:
            async with AsyncClient(
                timeout=Timeout(HTTP_TIMEOUT_SECONDS), follow_redirects=False
            ) as client:
                response = await client.post(REVOKE_ENDPOINT, data={"token": token})
            return response.status_code == 200
        except Exception:
            return False

    async def probe_gmail_access_token(self, access_token: str) -> TokenProbeOutcome:
        """Probe one minimal Gmail read; only HTTP 401 proves credential rejection."""
        try:
            async with AsyncClient(
                timeout=Timeout(HTTP_TIMEOUT_SECONDS), follow_redirects=False
            ) as client:
                async with client.stream(
                    "GET",
                    f"{GMAIL_API}/messages",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"maxResults": 1, "fields": "messages(id)"},
                ) as response:
                    if response.status_code == 401:
                        return TokenProbeOutcome.REJECTED
                    if 200 <= response.status_code < 300:
                        return TokenProbeOutcome.ACCEPTED
                    return TokenProbeOutcome.INCONCLUSIVE
        except Exception:
            return TokenProbeOutcome.INCONCLUSIVE

    async def read_gmail_metadata(
        self, access_token: str
    ) -> GmailMessageMetadata | None:
        try:
            async with AsyncClient(
                timeout=Timeout(HTTP_TIMEOUT_SECONDS), follow_redirects=False
            ) as client:
                listing_status, listing_json = await _request_json(
                    client,
                    "GET",
                    f"{GMAIL_API}/messages",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"maxResults": 1, "fields": "messages(id)"},
                )
                _raise_for_provider_status(listing_status)
                messages = listing_json.get("messages", [])
                if not isinstance(messages, list) or not messages:
                    return None
                first = messages[0]
                if not isinstance(first, dict) or not isinstance(first.get("id"), str):
                    raise GoogleConnectionFailure("provider_unavailable")
                message_id = first["id"]
                detail_status, detail_json = await _request_json(
                    client,
                    "GET",
                    f"{GMAIL_API}/messages/{quote(message_id, safe='')}",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={
                        "format": "metadata",
                        "metadataHeaders": ["From", "Subject", "Date"],
                        "fields": "id,threadId,payload(headers(name,value))",
                    },
                )
                _raise_for_provider_status(detail_status)
            payload = detail_json.get("payload")
            headers = payload.get("headers", []) if isinstance(payload, dict) else []
            if not isinstance(headers, list):
                raise GoogleConnectionFailure("provider_unavailable")
            safe_headers: list[tuple[str, str]] = []
            for header in headers:
                if (
                    isinstance(header, dict)
                    and isinstance(header.get("name"), str)
                    and header["name"].lower() in {"from", "subject", "date"}
                    and isinstance(header.get("value"), str)
                ):
                    safe_headers.append((header["name"], header["value"]))
            thread_id = detail_json.get("threadId")
            return GmailMessageMetadata(
                message_id=message_id,
                thread_id=thread_id if isinstance(thread_id, str) else None,
                headers=tuple(safe_headers),
            )
        except GoogleConnectionFailure:
            raise
        except Exception:
            raise GoogleConnectionFailure("provider_unavailable") from None

    async def read_secondary_calendar(
        self,
        access_token: str,
        *,
        now: datetime | None = None,
    ) -> CalendarReadResult:
        try:
            async with AsyncClient(
                timeout=Timeout(HTTP_TIMEOUT_SECONDS), follow_redirects=False
            ) as client:
                calendar_status, calendars = await _request_json(
                    client,
                    "GET",
                    f"{CALENDAR_API}/users/me/calendarList",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={
                        "maxResults": 100,
                        "fields": "items(id,primary)",
                    },
                )
                _raise_for_provider_status(calendar_status)
                items = calendars.get("items", [])
                if not isinstance(items, list):
                    raise GoogleConnectionFailure("provider_unavailable")
                secondary_id = next(
                    (
                        item.get("id")
                        for item in items
                        if isinstance(item, dict)
                        and item.get("primary", False) is False
                        and isinstance(item.get("id"), str)
                    ),
                    None,
                )
                if secondary_id is None:
                    return CalendarReadResult(False, None)
                origin = datetime.now(UTC) if now is None else now
                if origin.tzinfo is None:
                    raise GoogleConnectionFailure("provider_unavailable")
                events_status, events = await _request_json(
                    client,
                    "GET",
                    f"{CALENDAR_API}/calendars/{quote(secondary_id, safe='')}/events",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={
                        "maxResults": 1,
                        "singleEvents": "true",
                        "orderBy": "startTime",
                        "timeMin": origin.isoformat(),
                        "timeMax": (origin + timedelta(days=7)).isoformat(),
                        "fields": "items(id,start(date,dateTime),end(date,dateTime))",
                    },
                )
                _raise_for_provider_status(events_status)
            event_items = events.get("items", [])
            if not isinstance(event_items, list) or not event_items:
                return CalendarReadResult(True, None)
            first_event = event_items[0]
            if not isinstance(first_event, dict) or not isinstance(
                first_event.get("id"), str
            ):
                raise GoogleConnectionFailure("provider_unavailable")
            start = first_event.get("start")
            end = first_event.get("end")
            return CalendarReadResult(
                True,
                CalendarEventSummary(
                    event_id=first_event["id"],
                    start=_event_time(start),
                    end=_event_time(end),
                ),
            )
        except GoogleConnectionFailure:
            raise
        except Exception:
            raise GoogleConnectionFailure("provider_unavailable") from None

    async def verify_reads(self, access_token: str) -> GoogleReadSummary:
        await self.read_gmail_metadata(access_token)
        calendar = await self.read_secondary_calendar(access_token)
        return GoogleReadSummary(
            gmail_read_succeeded=True,
            secondary_calendar_found=calendar.secondary_calendar_found,
            calendar_read_succeeded=True,
            calendar_event_found=calendar.event is not None,
        )

    async def read_secondary_calendar_event(
        self, access_token: str, *, now: datetime | None = None
    ) -> CalendarEventSummary | None:
        return (await self.read_secondary_calendar(access_token, now=now)).event


def _event_time(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    candidate = value.get("dateTime", value.get("date"))
    return candidate if isinstance(candidate, str) else None


async def _read_json_response(response: Any) -> dict[str, Any]:
    body = bytearray()
    async for chunk in response.aiter_bytes():
        body.extend(chunk)
        if len(body) > MAX_RESPONSE_BYTES:
            raise GoogleConnectionFailure("provider_unavailable")
    if not body:
        return {}
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise GoogleConnectionFailure("provider_unavailable") from None
    if not isinstance(value, dict):
        raise GoogleConnectionFailure("provider_unavailable")
    return value


async def _request_json(
    client: Any,
    method: str,
    url: str,
    **kwargs: Any,
) -> tuple[int, dict[str, Any]]:
    async with client.stream(method, url, **kwargs) as response:
        payload = await _read_json_response(response)
        return response.status_code, payload


def _raise_for_provider_status(status_code: int) -> None:
    if status_code < 200 or status_code >= 300:
        raise GoogleConnectionFailure("provider_unavailable")
