"""Explicit authentication configuration, kept separate from public liveness."""

import os
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse


@dataclass(frozen=True, slots=True)
class AuthSettings:
    database_url: str
    owner_sub: str
    google_client_id: str
    google_client_secret: str
    callback_uri: str
    web_origin: str
    google_token_encryption_key: str | None = None

    @property
    def secure_cookie(self) -> bool:
        return urlparse(self.web_origin).scheme == "https"

    @property
    def google_connection_callback_uri(self) -> str:
        """Dedicated callback path derived from the configured public origin."""
        parsed = urlparse(self.callback_uri)
        return urlunparse(
            parsed._replace(
                path="/api/google/connection/callback",
                params="",
                query="",
                fragment="",
            )
        )


def load_auth_settings() -> AuthSettings | None:
    """Return valid settings only when authentication is explicitly enabled."""
    if os.environ.get("EMAIL_SUPPORT_AUTH_ENABLED", "false").lower() != "true":
        return None
    values = {
        "database_url": os.environ.get("EMAIL_SUPPORT_DATABASE_URL", ""),
        "owner_sub": os.environ.get("EMAIL_SUPPORT_OWNER_SUB", ""),
        "google_client_id": os.environ.get("EMAIL_SUPPORT_GOOGLE_CLIENT_ID", ""),
        "google_client_secret": os.environ.get(
            "EMAIL_SUPPORT_GOOGLE_CLIENT_SECRET", ""
        ),
        "callback_uri": os.environ.get("EMAIL_SUPPORT_GOOGLE_CALLBACK_URI", ""),
        "web_origin": os.environ.get("EMAIL_SUPPORT_WEB_ORIGIN", ""),
    }
    if not all(value.strip() for value in values.values()):
        raise ValueError("authentication configuration is incomplete")
    if not values["database_url"].startswith("postgresql+psycopg://"):
        raise ValueError("authentication database URL must use async Psycopg")
    origin = urlparse(values["web_origin"])
    callback = urlparse(values["callback_uri"])
    if origin.scheme not in {"http", "https"} or not origin.netloc:
        raise ValueError("web origin must be an absolute HTTP origin")
    if (
        origin.path
        or origin.query
        or origin.fragment
        or origin.username
        or origin.password
    ):
        raise ValueError("web origin must not contain a path or query")
    if callback.scheme not in {"http", "https"} or not callback.netloc:
        raise ValueError("callback URI must be an absolute HTTP URL")
    if (
        callback.query
        or callback.fragment
        or callback.username
        or callback.password
        or not callback.path
    ):
        raise ValueError("callback URI must be a fixed path without credentials")
    if origin.scheme != callback.scheme:
        raise ValueError("web origin and callback URI must use the same scheme")
    loopback_hosts = {"localhost", "127.0.0.1", "::1"}
    if origin.scheme == "http" and origin.hostname not in loopback_hosts:
        raise ValueError("plain HTTP is allowed only for loopback origins")
    if callback.scheme == "http" and callback.hostname not in loopback_hosts:
        raise ValueError("plain HTTP callback is allowed only for loopback")
    encryption_key = os.environ.get("EMAIL_SUPPORT_GOOGLE_TOKEN_ENCRYPTION_KEY", "")
    return AuthSettings(
        **values,
        google_token_encryption_key=encryption_key.strip() or None,
    )
