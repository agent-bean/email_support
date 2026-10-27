"""Authenticated encryption for a single Google connection credential bundle."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken

from email_support.models.google_connection import (
    GoogleConnectionFailure,
    GoogleTokenBundle,
)

FERNET_KEY_VERSION = "fernet-v1"


def _fernet(key: str | None) -> Fernet:
    if not key:
        raise GoogleConnectionFailure("credentials_unavailable")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError, TypeError):
        raise GoogleConnectionFailure("credentials_unavailable") from None


def validate_encryption_key(key: str | None) -> None:
    _fernet(key)


def encrypt_token_bundle(
    bundle: GoogleTokenBundle,
    key: str | None,
    *,
    connection_id: UUID,
    owner_sub: str,
) -> tuple[bytes, str]:
    if bundle.access_expires_at.tzinfo is None or not bundle.access_token:
        raise GoogleConnectionFailure("credentials_unavailable")
    payload = {
        "version": 1,
        "provider": "google",
        "connection_id": str(connection_id),
        "owner_sub": owner_sub,
        "access_token": bundle.access_token,
        "refresh_token": bundle.refresh_token,
        "access_expires_at": bundle.access_expires_at.astimezone(UTC).isoformat(),
    }
    try:
        ciphertext = _fernet(key).encrypt(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        )
    except GoogleConnectionFailure:
        raise
    except (TypeError, ValueError, UnicodeEncodeError):
        raise GoogleConnectionFailure("credentials_unavailable") from None
    return ciphertext, FERNET_KEY_VERSION


def decrypt_token_bundle(
    ciphertext: bytes,
    key: str | None,
    *,
    connection_id: UUID,
    owner_sub: str,
) -> GoogleTokenBundle:
    try:
        payload = json.loads(_fernet(key).decrypt(ciphertext))
        expected_keys = {
            "version",
            "provider",
            "connection_id",
            "owner_sub",
            "access_token",
            "refresh_token",
            "access_expires_at",
        }
        if (
            not isinstance(payload, dict)
            or set(payload) != expected_keys
            or payload["version"] != 1
            or payload["provider"] != "google"
            or payload["connection_id"] != str(connection_id)
            or payload["owner_sub"] != owner_sub
            or not isinstance(payload["access_token"], str)
            or not payload["access_token"]
            or (
                payload["refresh_token"] is not None
                and not isinstance(payload["refresh_token"], str)
            )
            or not isinstance(payload["access_expires_at"], str)
        ):
            raise ValueError("invalid encrypted token bundle")
        expiry = datetime.fromisoformat(payload["access_expires_at"])
        if expiry.tzinfo is None:
            raise ValueError("encrypted token expiry is naive")
        return GoogleTokenBundle(
            access_token=payload["access_token"],
            refresh_token=payload["refresh_token"],
            access_expires_at=expiry,
        )
    except GoogleConnectionFailure:
        raise
    except (InvalidToken, ValueError, TypeError, UnicodeDecodeError, KeyError):
        raise GoogleConnectionFailure("credentials_unavailable") from None
