"""Google connection encryption, scope and safe contract behavior."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from email_support.models.google_connection import (
    GoogleConnectionFailure,
    GoogleConnectionStatus,
    GoogleTokenBundle,
)
from email_support.services.google_connection import (
    REQUESTED_CONNECTION_SCOPES,
    REQUIRED_PRODUCT_SCOPES,
    evaluate_granted_scopes,
)
from email_support.services.google_connection_crypto import (
    decrypt_token_bundle,
    encrypt_token_bundle,
)


def token_bundle() -> GoogleTokenBundle:
    return GoogleTokenBundle(
        access_token="access-token-value",
        refresh_token="refresh-token-value",
        access_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


def test_connection_requests_only_the_required_google_scopes() -> None:
    assert REQUESTED_CONNECTION_SCOPES == (
        "openid",
        "email",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/calendar.events.readonly",
        "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    )
    assert set(REQUIRED_PRODUCT_SCOPES) == set(REQUESTED_CONNECTION_SCOPES[2:])
    assert "https://mail.google.com/" not in REQUESTED_CONNECTION_SCOPES


def test_partial_scope_is_actionable_and_never_connected() -> None:
    actual = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/calendar.events.readonly",
    ]

    decision = evaluate_granted_scopes(actual)

    assert decision.status is GoogleConnectionStatus.RECONNECT_REQUIRED
    assert decision.missing_scopes == (
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    )
    assert decision.unexpected_scopes == ()


def test_unrequested_product_scope_is_rejected() -> None:
    decision = evaluate_granted_scopes(
        [
            *REQUESTED_CONNECTION_SCOPES,
            "https://www.googleapis.com/auth/gmail.modify",
        ]
    )

    assert decision.status is GoogleConnectionStatus.RECONNECT_REQUIRED
    assert decision.unexpected_scopes == (
        "https://www.googleapis.com/auth/gmail.modify",
    )


def test_fernet_bundle_round_trip_contains_context_and_no_plaintext_tokens() -> None:
    key = Fernet.generate_key().decode()
    connection_id = uuid4()
    bundle = token_bundle()

    encrypted, key_version = encrypt_token_bundle(
        bundle,
        key,
        connection_id=connection_id,
        owner_sub="configured-owner",
    )

    assert key_version == "fernet-v1"
    assert b"access-token-value" not in encrypted
    assert b"refresh-token-value" not in encrypted
    assert (
        decrypt_token_bundle(
            encrypted,
            key,
            connection_id=connection_id,
            owner_sub="configured-owner",
        )
        == bundle
    )


@pytest.mark.parametrize(
    "context",
    [
        {"owner_sub": "different-owner"},
        {"connection_id": uuid4()},
    ],
)
def test_fernet_bundle_rejects_context_swaps(
    context: dict[str, object],
) -> None:
    key = Fernet.generate_key().decode()
    connection_id = uuid4()
    encrypted, _ = encrypt_token_bundle(
        token_bundle(),
        key,
        connection_id=connection_id,
        owner_sub="configured-owner",
    )
    decrypt_context: dict[str, object] = {
        "connection_id": connection_id,
        "owner_sub": "configured-owner",
    }
    decrypt_context.update(context)

    with pytest.raises(GoogleConnectionFailure) as failure:
        decrypt_token_bundle(encrypted, key, **decrypt_context)  # type: ignore[arg-type]

    assert failure.value.code == "credentials_unavailable"


def test_missing_or_invalid_key_and_tampered_ciphertext_fail_closed() -> None:
    connection_id = uuid4()
    encrypted, _ = encrypt_token_bundle(
        token_bundle(),
        Fernet.generate_key().decode(),
        connection_id=connection_id,
        owner_sub="configured-owner",
    )

    for key, ciphertext in ((None, encrypted), ("invalid-key", encrypted)):
        with pytest.raises(GoogleConnectionFailure) as failure:
            decrypt_token_bundle(
                ciphertext,
                key,
                connection_id=connection_id,
                owner_sub="configured-owner",
            )
        assert failure.value.code == "credentials_unavailable"

    tampered = encrypted[:-1] + bytes([encrypted[-1] ^ 1])
    with pytest.raises(GoogleConnectionFailure) as failure:
        decrypt_token_bundle(
            tampered,
            Fernet.generate_key().decode(),
            connection_id=connection_id,
            owner_sub="configured-owner",
        )
    assert failure.value.code == "credentials_unavailable"
