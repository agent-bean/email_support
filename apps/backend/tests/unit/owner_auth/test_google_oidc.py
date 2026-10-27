"""OIDC protocol parameters and strict owner-claim validation."""

import asyncio
import base64
import hashlib
from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlparse

import pytest
from joserfc import jwk, jwt
from joserfc.jwk import KeySet

from email_support.integrations.google_oidc import (
    _validate_claims,
    create_authorization,
    exchange_code,
)
from email_support.services.owner_auth import require_owner_subject


def test_authorization_uses_fixed_callback_openid_email_and_s256_pkce() -> None:
    authorization = create_authorization(
        "client-id", "client-secret", "http://localhost:8000/api/auth/google/callback"
    )
    query = parse_qs(urlparse(authorization.url).query)

    assert query["redirect_uri"] == ["http://localhost:8000/api/auth/google/callback"]
    assert query["scope"] == ["openid email"]
    assert query["response_type"] == ["code"]
    assert query["state"] == [authorization.state]
    assert query["nonce"] == [authorization.nonce]
    assert query["code_challenge_method"] == ["S256"]
    challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(authorization.code_verifier.encode()).digest()
        )
        .rstrip(b"=")
        .decode()
    )
    assert query["code_challenge"] == [challenge]
    assert "access_type" not in query


def claims(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "sub": "owner-subject",
        "iss": "https://accounts.google.com",
        "aud": "client-id",
        "exp": 2_000_000_100,
        "iat": 2_000_000_000,
        "nonce": "expected-nonce",
        "email": "owner@example.com",
    }
    values.update(changes)
    return values


def test_valid_owner_subject_is_independent_of_email() -> None:
    identity = _validate_claims(
        claims(email="changed@example.com"),
        client_id="client-id",
        expected_nonce="expected-nonce",
        now=2_000_000_050,
    )

    assert identity.sub == "owner-subject"
    assert identity.email == "changed@example.com"
    require_owner_subject(identity, "owner-subject")


def test_authorized_party_with_multiple_audiences_is_validated() -> None:
    identity = _validate_claims(
        claims(aud=["client-id", "another-client"], azp="client-id"),
        client_id="client-id",
        expected_nonce="expected-nonce",
        now=2_000_000_050,
    )

    assert identity.sub == "owner-subject"


def test_matching_email_does_not_authorize_another_google_subject() -> None:
    identity = _validate_claims(
        claims(sub="attacker-subject", email="owner@example.com"),
        client_id="client-id",
        expected_nonce="expected-nonce",
        now=2_000_000_050,
    )

    with pytest.raises(PermissionError, match="configured owner"):
        require_owner_subject(identity, "owner-subject")


@pytest.mark.parametrize(
    "invalid_claims",
    [
        {"iss": "https://attacker.example"},
        {"aud": "another-client"},
        {"aud": ["client-id", "another-client"]},
        {"azp": "another-client"},
        {"exp": 2_000_000_050},
        {"iat": 2_000_000_200},
        {"iat": 1_999_996_000},
        {"nonce": "another-nonce"},
    ],
)
def test_untrusted_claim_variants_are_rejected(
    invalid_claims: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        _validate_claims(
            claims(**invalid_claims),
            client_id="client-id",
            expected_nonce="expected-nonce",
            now=2_000_000_050,
        )


def signed_id_token(key: object, kid: str) -> str:
    return jwt.encode(
        {"alg": "RS256", "kid": kid},
        {
            "sub": "owner-subject",
            "iss": "https://accounts.google.com",
            "aud": "client-id",
            "exp": 2_000_000_100,
            "iat": 2_000_000_000,
            "nonce": "expected-nonce",
        },
        key,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_unknown_key_id_triggers_one_bounded_key_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from email_support.integrations import google_oidc

    first_private = jwk.generate_key("RSA", 2048, auto_kid=True)
    second_private = jwk.generate_key("RSA", 2048, auto_kid=True)
    assert first_private.kid is not None and second_private.kid is not None
    first_keys = KeySet.import_key_set({"keys": [first_private.as_dict(private=False)]})
    second_keys = KeySet.import_key_set(
        {"keys": [second_private.as_dict(private=False)]}
    )
    calls: list[bool] = []

    async def load_keys(*, force: bool = False) -> KeySet:
        calls.append(force)
        return second_keys if force else first_keys

    monkeypatch.setattr(google_oidc, "_load_keys", load_keys)
    token = signed_id_token(second_private, second_private.kid)

    identity = await google_oidc.validate_id_token(
        token,
        client_id="client-id",
        expected_nonce="expected-nonce",
        now=2_000_000_050,
    )

    assert identity.sub == "owner-subject"
    assert calls == [False, True]


@pytest.mark.asyncio
async def test_bad_signature_does_not_trigger_repeated_key_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from email_support.integrations import google_oidc

    trusted = jwk.generate_key("RSA", 2048, auto_kid=True)
    assert trusted.kid is not None
    attacker = jwk.generate_key("RSA", 2048, parameters={"kid": trusted.kid})
    assert attacker.kid == trusted.kid
    trusted_keys = KeySet.import_key_set({"keys": [trusted.as_dict(private=False)]})
    calls: list[bool] = []

    async def load_keys(*, force: bool = False) -> KeySet:
        calls.append(force)
        return trusted_keys

    monkeypatch.setattr(google_oidc, "_load_keys", load_keys)
    token = signed_id_token(attacker, trusted.kid)

    with pytest.raises(ValueError, match="signature"):
        await google_oidc.validate_id_token(
            token,
            client_id="client-id",
            expected_nonce="expected-nonce",
            now=2_000_000_050,
        )
    assert calls == [False]


@pytest.mark.asyncio
async def test_jwks_body_limit_is_enforced_while_streaming(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from email_support.integrations import google_oidc

    class Response:
        headers: dict[str, str] = {}

        def raise_for_status(self) -> None:
            pass

        async def aiter_bytes(self) -> AsyncIterator[bytes]:
            yield b"x" * 65_536
            yield b"y"

    class Stream:
        async def __aenter__(self) -> Response:
            return Response()

        async def __aexit__(self, *args: object) -> None:
            del args

    class Client:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

        async def __aenter__(self) -> object:
            return self

        async def __aexit__(self, *args: object) -> None:
            del args

        def stream(self, method: str, url: str) -> Stream:
            assert method == "GET"
            assert url == google_oidc.JWKS_ENDPOINT
            return Stream()

    monkeypatch.setattr(google_oidc, "AsyncClient", Client)
    monkeypatch.setattr(google_oidc, "_cached_keys", None)

    with pytest.raises(ValueError, match="size limit"):
        await google_oidc._load_keys(force=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [TimeoutError("provider timeout"), asyncio.CancelledError()]
)
async def test_provider_timeout_and_cancellation_propagate(
    monkeypatch: pytest.MonkeyPatch, failure: BaseException
) -> None:
    from email_support.integrations import google_oidc

    class RaisingClient:
        async def __aenter__(self) -> object:
            return self

        async def __aexit__(self, *args: object) -> None:
            del args

        async def fetch_token(self, *args: object, **kwargs: object) -> object:
            del args, kwargs
            raise failure

    monkeypatch.setattr(google_oidc, "_client", lambda *args: RaisingClient())

    with pytest.raises(type(failure)):
        await exchange_code(
            "code",
            client_id="client-id",
            client_secret="client-secret",
            callback_uri="https://support.example/api/auth/google/callback",
            code_verifier="verifier",
            expected_nonce="nonce",
        )
