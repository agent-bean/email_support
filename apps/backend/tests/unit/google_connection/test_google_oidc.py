"""Separate-consent OAuth parameters and token response safety."""

from urllib.parse import parse_qs, urlparse

from email_support.integrations.google_oidc import (
    create_connection_authorization,
    parse_connection_token_response,
)
from email_support.models.google_connection import (
    GoogleConnectionFailure,
)


def test_connection_authorization_is_separate_offline_and_scope_limited() -> None:
    authorization = create_connection_authorization(
        "client-id",
        "client-secret",
        "https://support.example/api/google/connection/callback",
    )
    query = parse_qs(urlparse(authorization.url).query)

    assert set(query["scope"][0].split()) == {
        "openid",
        "email",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/calendar.events.readonly",
        "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    }
    assert query["access_type"] == ["offline"]
    assert query["include_granted_scopes"] == ["true"]
    assert query["prompt"] == ["consent"]
    assert query["redirect_uri"] == [
        "https://support.example/api/google/connection/callback"
    ]
    assert query["state"] == [authorization.state]
    assert query["nonce"] == [authorization.nonce]
    assert query["code_challenge_method"] == ["S256"]


def test_connection_token_response_requires_access_and_exact_scope_shape() -> None:
    parsed = parse_connection_token_response(
        {
            "access_token": "opaque-access-token",
            "refresh_token": "opaque-refresh-token",
            "expires_in": 3600,
            "scope": "openid email https://www.googleapis.com/auth/gmail.readonly",
            "id_token": "opaque-id-token",
        },
    )

    assert parsed.token_bundle.access_token == "opaque-access-token"
    assert parsed.token_bundle.refresh_token == "opaque-refresh-token"
    assert parsed.granted_scopes == frozenset(
        {
            "openid",
            "email",
            "https://www.googleapis.com/auth/gmail.readonly",
        }
    )
    assert "opaque-access-token" not in repr(parsed)
    assert "opaque-refresh-token" not in repr(parsed)


def test_malformed_connection_token_response_is_sanitized() -> None:
    try:
        parse_connection_token_response(
            {
                "access_token": "secret-from-provider",
                "expires_in": "not-a-duration",
                "scope": "openid",
                "id_token": "bad-token",
            }
        )
    except GoogleConnectionFailure as error:
        assert error.code == "provider_unavailable"
        assert "secret-from-provider" not in str(error)
        assert "bad-token" not in str(error)
    else:
        raise AssertionError("malformed provider token response was accepted")
