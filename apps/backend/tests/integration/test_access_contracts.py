"""Access endpoints stay unavailable until owner authentication is configured."""

from collections.abc import Iterator
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from email_support.api import access as access_api
from email_support.config import AuthSettings
from email_support.integrations.google_oidc import GoogleAuthorization
from email_support.main import app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    for name in (
        "EMAIL_SUPPORT_AUTH_ENABLED",
        "EMAIL_SUPPORT_DATABASE_URL",
        "EMAIL_SUPPORT_OWNER_SUB",
        "EMAIL_SUPPORT_GOOGLE_CLIENT_ID",
        "EMAIL_SUPPORT_GOOGLE_CLIENT_SECRET",
        "EMAIL_SUPPORT_GOOGLE_CALLBACK_URI",
        "EMAIL_SUPPORT_WEB_ORIGIN",
    ):
        monkeypatch.delenv(name, raising=False)
    with TestClient(app) as test_client:
        yield test_client


def test_health_and_openapi_do_not_require_auth_configuration(
    client: TestClient,
) -> None:
    assert client.get("/api/health").status_code == 200
    assert client.get("/openapi.json").status_code == 200


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/auth/preauth"),
        ("post", "/api/auth/google/login"),
        ("get", "/api/auth/google/callback"),
        ("get", "/api/auth/session"),
        ("post", "/api/auth/logout"),
    ],
)
def test_access_endpoints_fail_closed_without_auth_configuration(
    client: TestClient, method: str, path: str
) -> None:
    response = getattr(client, method)(path)

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "auth_unavailable"


def test_openapi_describes_authentication_and_csrf_contracts(
    client: TestClient,
) -> None:
    schema = client.get("/openapi.json").json()

    assert "/api/auth/session" in schema["paths"]
    session_operation = schema["paths"]["/api/auth/session"]["get"]
    assert session_operation["security"] == [{"OwnerSession": []}]
    logout_operation = schema["paths"]["/api/auth/logout"]["post"]
    assert "X-CSRF-Token" in str(logout_operation["parameters"])
    assert "OwnerSession" in schema["components"]["securitySchemes"]


def test_google_login_accepts_json_request(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = AuthSettings(
        database_url="postgresql+psycopg://user:password@localhost/app",
        owner_sub="owner-subject",
        google_client_id="client-id",
        google_client_secret="client-secret",
        callback_uri="http://localhost:8000/api/auth/google/callback",
        web_origin="http://localhost:5173",
    )

    async def begin_login_stub(
        *_args: object, **_kwargs: object
    ) -> GoogleAuthorization:
        return GoogleAuthorization(
            url="https://accounts.google.com/o/oauth2/v2/auth?state=test-state",
            state="test-state",
            nonce="test-nonce",
            code_verifier="test-verifier",
        )

    sessions = cast(async_sessionmaker[AsyncSession], object())
    monkeypatch.setattr(
        access_api,
        "runtime",
        lambda _request: access_api.AccessRuntime(settings, sessions, None),
    )
    monkeypatch.setattr(access_api, "begin_login", begin_login_stub)
    client.cookies.set("owner_browser", "browser-secret")

    response = client.post(
        "/api/auth/google/login",
        headers={
            "Content-Type": "application/json",
            "Origin": settings.web_origin,
            "X-CSRF-Token": "csrf-secret",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?state=test-state"
    }


def test_invalid_configuration_fails_closed_without_affecting_health(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMAIL_SUPPORT_AUTH_ENABLED", "true")
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        response = client.get("/api/auth/session")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "auth_unavailable"


def test_database_outage_does_not_affect_health(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        "EMAIL_SUPPORT_AUTH_ENABLED": "true",
        "EMAIL_SUPPORT_DATABASE_URL": "postgresql+psycopg://user:pass@127.0.0.1:1/app",
        "EMAIL_SUPPORT_OWNER_SUB": "owner-subject",
        "EMAIL_SUPPORT_GOOGLE_CLIENT_ID": "client-id",
        "EMAIL_SUPPORT_GOOGLE_CLIENT_SECRET": "client-secret",
        "EMAIL_SUPPORT_GOOGLE_CALLBACK_URI": (
            "http://localhost:8000/api/auth/google/callback"
        ),
        "EMAIL_SUPPORT_WEB_ORIGIN": "http://localhost:5173",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    with TestClient(app) as client:
        client.cookies.set("owner_session", "unrecognized-session")
        health = client.get("/api/health")
        protected = client.get("/api/auth/session")

    assert health.status_code == 200
    assert protected.status_code == 503
    assert protected.json()["detail"]["code"] == "auth_unavailable"
