"""Bounded Google authorization-code and OpenID Connect validation."""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass

# Authlib currently ships without PEP 561 stubs; this adapter validates all values
# crossing its OAuth boundary before they enter application state.
from authlib.integrations.httpx_client import AsyncOAuth2Client  # type: ignore[import-untyped]
from authlib.oidc.core import CodeIDToken  # type: ignore[import-untyped]
from httpx2 import AsyncClient, Timeout
from joserfc import jwt
from joserfc.errors import InvalidKeyIdError
from joserfc.jwk import KeySet

AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
JWKS_ENDPOINT = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


@dataclass(frozen=True, slots=True)
class GoogleAuthorization:
    url: str
    state: str
    nonce: str
    code_verifier: str


@dataclass(frozen=True, slots=True)
class GoogleIdentity:
    sub: str
    email: str | None


_cached_keys: KeySet | None = None
_cached_until = 0.0


def _client(client_id: str, client_secret: str, callback_uri: str) -> AsyncOAuth2Client:
    return AsyncOAuth2Client(
        client_id,
        client_secret,
        scope="openid email",
        redirect_uri=callback_uri,
        code_challenge_method="S256",
        timeout=Timeout(5.0),
    )


def create_authorization(
    client_id: str, client_secret: str, callback_uri: str
) -> GoogleAuthorization:
    import secrets

    verifier = secrets.token_urlsafe(64)[:96]
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    client = _client(client_id, client_secret, callback_uri)
    uri, _ = client.create_authorization_url(
        AUTHORIZATION_ENDPOINT,
        state=state,
        nonce=nonce,
        code_verifier=verifier,
    )
    return GoogleAuthorization(uri, state, nonce, verifier)


async def _load_keys(*, force: bool = False) -> KeySet:
    global _cached_keys, _cached_until
    if not force and _cached_keys is not None and _cached_until > time.monotonic():
        return _cached_keys
    async with AsyncClient(timeout=Timeout(5.0), follow_redirects=False) as client:
        async with client.stream("GET", JWKS_ENDPOINT) as response:
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > 65_536:
                    raise ValueError(
                        "Google signing-key response exceeded its size limit"
                    )
            data = json.loads(body)
    key_set = KeySet.import_key_set(data)
    _cached_keys = key_set
    cache_control = response.headers.get("cache-control", "")
    max_age = 300
    for directive in cache_control.split(","):
        key, separator, value = directive.strip().partition("=")
        if key == "max-age" and separator:
            try:
                max_age = int(value)
            except ValueError:
                max_age = 300
            break
    cache_seconds = min(max(max_age, 60), 3600)
    _cached_until = time.monotonic() + cache_seconds
    return key_set


def _validate_claims(
    claims: Mapping[str, object], *, client_id: str, expected_nonce: str, now: int
) -> GoogleIdentity:
    validated = CodeIDToken(
        dict(claims),
        {},
        options={
            "iss": {"values": list(ISSUERS)},
            "aud": {"values": [client_id]},
        },
        params={"client_id": client_id, "nonce": expected_nonce},
    )
    try:
        validated.validate(now=now)
    except Exception as exc:
        raise ValueError("Google ID token claims were rejected") from exc
    subject = validated.get("sub")
    expires_at = validated.get("exp")
    issued_at = validated.get("iat")
    if (
        not isinstance(subject, str)
        or not subject
        or len(subject) > 512
        or type(expires_at) is not int
        or expires_at <= now
        or type(issued_at) is not int
        or issued_at < now - 3600
    ):
        raise ValueError("Google token time claims were not accepted")
    email_value = validated.get("email")
    email = email_value if isinstance(email_value, str) else None
    return GoogleIdentity(sub=subject, email=email)


async def validate_id_token(
    token: str, *, client_id: str, expected_nonce: str, now: int | None = None
) -> GoogleIdentity:
    current_time = int(time.time()) if now is None else now
    keys = await _load_keys()
    try:
        encoded_header = token.split(".", maxsplit=1)[0]
        header = json.loads(base64.urlsafe_b64decode(encoded_header + "=="))
        key_id = header.get("kid") if isinstance(header, dict) else None
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Google ID token header was malformed") from exc
    refresh_keys = not isinstance(key_id, str)
    if isinstance(key_id, str):
        try:
            keys.get_by_kid(key_id)
        except InvalidKeyIdError:
            refresh_keys = True
    if refresh_keys:
        keys = await _load_keys(force=True)
    try:
        decoded = jwt.decode(token, keys, algorithms=["RS256"])
    except Exception as exc:
        raise ValueError("Google ID token signature was rejected") from exc
    return _validate_claims(
        decoded.claims,
        client_id=client_id,
        expected_nonce=expected_nonce,
        now=current_time,
    )


async def exchange_code(
    code: str,
    *,
    client_id: str,
    client_secret: str,
    callback_uri: str,
    code_verifier: str,
    expected_nonce: str,
) -> GoogleIdentity:
    async with _client(client_id, client_secret, callback_uri) as client:
        token = await client.fetch_token(
            TOKEN_ENDPOINT,
            code=code,
            redirect_uri=callback_uri,
            code_verifier=code_verifier,
            timeout=Timeout(5.0),
        )
    id_token = token.get("id_token")
    if not isinstance(id_token, str) or not id_token:
        raise ValueError("Google did not return an ID token")
    return await validate_id_token(
        id_token, client_id=client_id, expected_nonce=expected_nonce
    )
