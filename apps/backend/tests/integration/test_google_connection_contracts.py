"""HTTP contracts for owner-only Google connection routes."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from email_support.api import google_connection as google_api
from email_support.api.auth import AuthRuntime, protected_session
from email_support.config import AuthSettings
from email_support.integrations.google_oidc import GoogleAuthorization
from email_support.models.google_connection import (
    GoogleConnectionErrorCode,
    GoogleConnectionResponse,
    GoogleConnectionStatus,
)

OWNER_SUB = "configured-owner-subject"
WEB_ORIGIN = "http://localhost:5173"
CSRF = "synchronizer-csrf-token-value-with-sufficient-length"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    settings = AuthSettings(
        database_url="postgresql+psycopg://user:pass@db/app",
        owner_sub=OWNER_SUB,
        google_client_id="client-id",
        google_client_secret="client-secret",
        callback_uri="http://localhost:8000/api/auth/google/callback",
        web_origin=WEB_ORIGIN,
    )
    auth = AuthRuntime(
        settings,
        cast(async_sessionmaker[AsyncSession], object()),
        None,
    )
    app = FastAPI()
    app.include_router(google_api.router)
    app.dependency_overrides[protected_session] = lambda: (
        OWNER_SUB,
        datetime.now(UTC) + timedelta(hours=1),
        CSRF,
    )
    monkeypatch.setattr(google_api, "require_auth_runtime", lambda _: auth)
    with TestClient(app) as test_client:
        test_client.cookies.set("owner_browser", "browser-secret")
        test_client.cookies.set("owner_session", "session-secret")
        yield test_client


def test_status_is_sanitized_owner_only_and_not_cached(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def status(*_: object, **__: object) -> GoogleConnectionResponse:
        return GoogleConnectionResponse(
            status=GoogleConnectionStatus.RECONNECT_REQUIRED,
            granted_scopes=["openid"],
            missing_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            error=GoogleConnectionErrorCode.PARTIAL_SCOPE,
        )

    monkeypatch.setattr(google_api, "get_google_connection_status", status)

    response = client.get("/api/google/connection")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["status"] == "reconnect_required"
    assert body["missing_scopes"] == ["https://www.googleapis.com/auth/gmail.readonly"]
    assert "access_token" not in body
    assert "refresh_token" not in body
    assert "owner_sub" not in body


def test_consent_requires_origin_and_csrf_before_creating_attempt(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = False

    async def begin(*_: object, **__: object) -> GoogleAuthorization:
        nonlocal called
        called = True
        return GoogleAuthorization("https://accounts.google.com/", "s", "n", "v")

    monkeypatch.setattr(google_api, "begin_google_consent", begin)
    headers = {"Origin": WEB_ORIGIN, "Content-Type": "application/json"}

    response = client.post("/api/google/connection/consent", json={}, headers=headers)

    assert response.status_code == 403
    assert called is False


def test_consent_returns_only_authorization_url(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def begin(*_: object, **__: object) -> GoogleAuthorization:
        return GoogleAuthorization(
            "https://accounts.google.com/o/oauth2/v2/auth?scope=openid",
            "private-state",
            "private-nonce",
            "private-verifier",
        )

    monkeypatch.setattr(google_api, "begin_google_consent", begin)
    response = client.post(
        "/api/google/connection/consent",
        json={},
        headers={
            "Origin": WEB_ORIGIN,
            "Content-Type": "application/json",
            "X-CSRF-Token": CSRF,
        },
    )

    assert response.status_code == 200
    assert set(response.json()) == {"authorization_url"}
    assert "private-state" not in response.text
    assert "private-nonce" not in response.text
    assert "private-verifier" not in response.text


def test_consent_accepts_the_empty_post_used_by_generated_client(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def begin(*_: object, **__: object) -> GoogleAuthorization:
        return GoogleAuthorization(
            "https://accounts.google.com/o/oauth2/v2/auth", "s", "n", "v"
        )

    monkeypatch.setattr(google_api, "begin_google_consent", begin)
    response = client.post(
        "/api/google/connection/consent",
        headers={"Origin": WEB_ORIGIN, "X-CSRF-Token": CSRF},
    )

    assert response.status_code == 200


def test_callback_redirect_does_not_reflect_provider_query_values(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def no_attempt(*_: object, **__: object) -> None:
        return None

    monkeypatch.setattr(google_api, "consume_google_consent_attempt", no_attempt)
    response = client.get(
        "/api/google/connection/callback",
        params={"code": "private-code", "state": "private-state"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "private-code" not in response.headers["location"]
    assert "private-state" not in response.headers["location"]
    assert response.headers["location"] == (f"{WEB_ORIGIN}/?google=invalid_callback")
