"""Configured owner routes use PostgreSQL sessions and browser-bound login state."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from email_support.api.access import SESSION_TTL_SECONDS
from email_support.integrations.google_oidc import GoogleIdentity
from email_support.main import app
from email_support.services.access import digest
from email_support.storage.postgres.persistence.access import create_owner_session

OWNER_SUB = "configured-owner-subject"
WEB_ORIGIN = "http://localhost:5173"


@pytest.fixture
def configured_client(
    monkeypatch: pytest.MonkeyPatch, database_url: str
) -> Iterator[TestClient]:
    settings = {
        "EMAIL_SUPPORT_AUTH_ENABLED": "true",
        "EMAIL_SUPPORT_DATABASE_URL": database_url,
        "EMAIL_SUPPORT_OWNER_SUB": OWNER_SUB,
        "EMAIL_SUPPORT_GOOGLE_CLIENT_ID": "client-id",
        "EMAIL_SUPPORT_GOOGLE_CLIENT_SECRET": "client-secret",
        "EMAIL_SUPPORT_GOOGLE_CALLBACK_URI": (
            "http://localhost:8000/api/auth/google/callback"
        ),
        "EMAIL_SUPPORT_WEB_ORIGIN": WEB_ORIGIN,
    }
    for name, value in settings.items():
        monkeypatch.setenv(name, value)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def secure_client(
    monkeypatch: pytest.MonkeyPatch, database_url: str
) -> Iterator[TestClient]:
    settings = {
        "EMAIL_SUPPORT_AUTH_ENABLED": "true",
        "EMAIL_SUPPORT_DATABASE_URL": database_url,
        "EMAIL_SUPPORT_OWNER_SUB": OWNER_SUB,
        "EMAIL_SUPPORT_GOOGLE_CLIENT_ID": "client-id",
        "EMAIL_SUPPORT_GOOGLE_CLIENT_SECRET": "client-secret",
        "EMAIL_SUPPORT_GOOGLE_CALLBACK_URI": (
            "https://support.example/api/auth/google/callback"
        ),
        "EMAIL_SUPPORT_WEB_ORIGIN": "https://support.example",
    }
    for name, value in settings.items():
        monkeypatch.setenv(name, value)
    with TestClient(app, base_url="https://support.example") as test_client:
        yield test_client


@pytest.mark.asyncio
async def test_owner_session_cookie_and_csrf_protect_logout(
    configured_client: TestClient,
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    token = "opaque-session-token"
    csrf = "synchronizer-csrf-token-value-with-sufficient-length"
    now = datetime.now(UTC)
    async with database_sessions() as session, session.begin():
        await create_owner_session(
            session,
            token_digest=digest(token),
            owner_sub=OWNER_SUB,
            created_at=now,
            expires_at=now + timedelta(seconds=SESSION_TTL_SECONDS),
            csrf_secret=csrf,
        )
    configured_client.cookies.set("owner_session", token)

    session_response = configured_client.get("/api/auth/session")
    assert session_response.status_code == 200
    assert session_response.json()["authenticated"] is True
    assert session_response.json()["csrf_token"] == csrf
    assert "owner_sub" not in session_response.json()
    assert session_response.headers["cache-control"] == "no-store"

    wrong_origin = configured_client.post(
        "/api/auth/logout",
        headers={"Origin": "https://attacker.example", "X-CSRF-Token": csrf},
    )
    wrong_csrf = configured_client.post(
        "/api/auth/logout",
        headers={"Origin": WEB_ORIGIN, "X-CSRF-Token": "wrong"},
    )
    assert wrong_origin.status_code == 403
    assert wrong_csrf.status_code == 403

    logout_response = configured_client.post(
        "/api/auth/logout",
        headers={"Origin": WEB_ORIGIN, "X-CSRF-Token": csrf},
    )
    assert logout_response.status_code == 204
    assert "Max-Age=0" in logout_response.headers.get("set-cookie", "")
    assert configured_client.get("/api/auth/session").status_code == 401
    configured_client.cookies.set("owner_session", "stale-session")
    stale = configured_client.get("/api/auth/session")
    assert stale.status_code == 401
    assert "Max-Age=0" in stale.headers.get("set-cookie", "")


def test_preauth_cookie_and_csrf_challenge_are_one_use(
    configured_client: TestClient,
) -> None:
    preauth = configured_client.get("/api/auth/preauth")
    assert preauth.status_code == 200
    assert preauth.headers["cache-control"] == "no-store"
    browser_cookie = preauth.headers["set-cookie"]
    assert "HttpOnly" in browser_cookie
    assert "SameSite=lax" in browser_cookie

    headers = {
        "Origin": WEB_ORIGIN,
        "Content-Type": "application/json",
        "X-CSRF-Token": preauth.json()["csrf_token"],
    }
    first = configured_client.post("/api/auth/google/login", json={}, headers=headers)
    replay = configured_client.post("/api/auth/google/login", json={}, headers=headers)

    assert first.status_code == 200
    auth_query = parse_qs(urlparse(first.json()["authorization_url"]).query)
    assert auth_query["redirect_uri"] == [
        "http://localhost:8000/api/auth/google/callback"
    ]
    assert replay.status_code == 400
    assert replay.json()["detail"]["code"] == "login_restart"


def test_callback_rejects_non_owner_subject_and_consumes_state(
    configured_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from email_support.api import access as access_api

    async def exchange(*args: object, **kwargs: object) -> GoogleIdentity:
        del args, kwargs
        return GoogleIdentity(sub="attacker-subject", email="owner@example.com")

    monkeypatch.setattr(access_api, "exchange_code", exchange)
    preauth = configured_client.get("/api/auth/preauth")
    login = configured_client.post(
        "/api/auth/google/login",
        json={},
        headers={
            "Origin": WEB_ORIGIN,
            "Content-Type": "application/json",
            "X-CSRF-Token": preauth.json()["csrf_token"],
        },
    )
    state = parse_qs(urlparse(login.json()["authorization_url"]).query)["state"][0]

    callback = configured_client.get(
        "/api/auth/google/callback",
        params={"code": "provider-code", "state": state},
        follow_redirects=False,
    )
    replay = configured_client.get(
        "/api/auth/google/callback",
        params={"code": "provider-code", "state": state},
        follow_redirects=False,
    )

    assert callback.status_code == 303
    assert callback.headers["location"] == f"{WEB_ORIGIN}/?auth=rejected"
    assert "owner_session" not in callback.headers.get("set-cookie", "")
    assert replay.headers["location"] == f"{WEB_ORIGIN}/?auth=restart"


def test_provider_denial_consumes_attempt_without_issuing_a_session(
    configured_client: TestClient,
) -> None:
    preauth = configured_client.get("/api/auth/preauth")
    login = configured_client.post(
        "/api/auth/google/login",
        json={},
        headers={
            "Origin": WEB_ORIGIN,
            "Content-Type": "application/json",
            "X-CSRF-Token": preauth.json()["csrf_token"],
        },
    )
    state = parse_qs(urlparse(login.json()["authorization_url"]).query)["state"][0]

    callback = configured_client.get(
        "/api/auth/google/callback",
        params={"error": "access_denied", "state": state},
        follow_redirects=False,
    )

    assert callback.status_code == 303
    assert callback.headers["location"] == f"{WEB_ORIGIN}/?auth=rejected"
    assert "owner_session" not in callback.headers.get("set-cookie", "")


def test_https_preauth_cookie_uses_host_prefix_and_secure_attributes(
    secure_client: TestClient,
) -> None:
    response = secure_client.get("/api/auth/preauth")

    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("__Host-owner_browser=")
    assert "Secure" in cookie
    assert "HttpOnly" in cookie
    assert "Path=/" in cookie
    assert "SameSite=lax" in cookie


def test_owner_login_issues_https_session_cookie(
    secure_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from email_support.api import access as access_api

    async def exchange(*args: object, **kwargs: object) -> GoogleIdentity:
        del args, kwargs
        return GoogleIdentity(sub=OWNER_SUB, email="changed@example.com")

    monkeypatch.setattr(access_api, "exchange_code", exchange)
    preauth = secure_client.get("/api/auth/preauth")
    login = secure_client.post(
        "/api/auth/google/login",
        json={},
        headers={
            "Origin": "https://support.example",
            "Content-Type": "application/json",
            "X-CSRF-Token": preauth.json()["csrf_token"],
        },
    )
    state = parse_qs(urlparse(login.json()["authorization_url"]).query)["state"][0]

    callback = secure_client.get(
        "/api/auth/google/callback",
        params={"code": "provider-code", "state": state},
        follow_redirects=False,
    )
    cookie = callback.headers["set-cookie"]

    assert callback.status_code == 303
    assert cookie.startswith("__Host-owner_session=")
    assert "Secure" in cookie
    assert "HttpOnly" in cookie
    assert "Path=/" in cookie
    assert "SameSite=lax" in cookie
    assert secure_client.get("/api/auth/session").status_code == 200
