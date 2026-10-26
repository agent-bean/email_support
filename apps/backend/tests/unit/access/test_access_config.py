"""Authentication configuration remains opt-in and rejects unsafe public HTTP."""

import pytest

from email_support.config import load_auth_settings


def set_valid_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "EMAIL_SUPPORT_AUTH_ENABLED": "true",
        "EMAIL_SUPPORT_DATABASE_URL": "postgresql+psycopg://user:pass@db/app",
        "EMAIL_SUPPORT_OWNER_SUB": "google-subject",
        "EMAIL_SUPPORT_GOOGLE_CLIENT_ID": "client-id",
        "EMAIL_SUPPORT_GOOGLE_CLIENT_SECRET": "client-secret",
        "EMAIL_SUPPORT_GOOGLE_CALLBACK_URI": "http://localhost:8000/api/auth/google/callback",
        "EMAIL_SUPPORT_WEB_ORIGIN": "http://localhost:5173",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_auth_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EMAIL_SUPPORT_AUTH_ENABLED", raising=False)

    assert load_auth_settings() is None


def test_local_http_is_limited_to_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    set_valid_configuration(monkeypatch)

    settings = load_auth_settings()

    assert settings is not None
    assert settings.secure_cookie is False

    monkeypatch.setenv("EMAIL_SUPPORT_WEB_ORIGIN", "http://example.com")
    with pytest.raises(ValueError, match="loopback"):
        load_auth_settings()


def test_public_https_uses_secure_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
    set_valid_configuration(monkeypatch)
    monkeypatch.setenv("EMAIL_SUPPORT_WEB_ORIGIN", "https://support.example.com")
    monkeypatch.setenv(
        "EMAIL_SUPPORT_GOOGLE_CALLBACK_URI",
        "https://support.example.com/api/auth/google/callback",
    )

    settings = load_auth_settings()

    assert settings is not None
    assert settings.secure_cookie is True
