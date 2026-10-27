"""Google consent, encrypted credentials, refresh and disconnect invariants."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import random
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from email_support.config import AuthSettings
from email_support.integrations.google_oidc import (
    CONNECTION_SCOPES,
    GoogleAuthorization,
    GoogleIdentity,
    create_connection_authorization,
)
from email_support.integrations.google_workspace import (
    CalendarEventSummary,
    CalendarReadResult,
    GmailMessageMetadata,
    GoogleWorkspaceClient,
)
from email_support.models.google_connection import (
    GoogleConnectionErrorCode,
    GoogleConnectionFailure,
    GoogleConnectionResponse,
    GoogleConnectionStatus,
    GoogleDisconnectResponse,
    GoogleTokenBundle,
    RevokeOutcome,
    ScopeDecision,
)
from email_support.services.google_connection_crypto import (
    decrypt_token_bundle,
    encrypt_token_bundle,
    validate_encryption_key,
)
from email_support.storage.postgres.persistence.google_connection import (
    claim_refresh_lease,
    create_google_consent_attempt,
    invalidate_refresh_grant,
    is_connection_generation_current,
    lock_live_owner_session,
    release_refresh_lease,
    save_refreshed_bundle,
)
from email_support.storage.postgres.persistence.tables.google_connection import (
    GoogleConnectionRow,
)
from email_support.storage.postgres.persistence.tables.owner_auth import OAuthAttemptRow

ATTEMPT_TTL = timedelta(minutes=10)
REFRESH_LEASE_TTL = timedelta(seconds=30)
ACCESS_TOKEN_SAFETY_MARGIN = timedelta(seconds=60)
REFRESH_FOLLOWER_DEADLINE_SECONDS = 12.0
REQUESTED_CONNECTION_SCOPES = CONNECTION_SCOPES
REQUIRED_CONNECTION_SCOPES = CONNECTION_SCOPES
REQUIRED_PRODUCT_SCOPES = CONNECTION_SCOPES[2:]


@dataclass(frozen=True, slots=True)
class GoogleConsentAttempt:
    connection_id: UUID
    generation: int
    nonce: str
    code_verifier: str


@dataclass(frozen=True, slots=True)
class _ConnectionSnapshot:
    connection_id: UUID
    generation: int
    credential_version: int
    owner_sub: str
    granted_scopes: tuple[str, ...]
    status: str
    encrypted_token_bundle: bytes | None
    encryption_key_version: str | None
    refresh_lease_owner: UUID | None
    refresh_lease_expires_at: datetime | None
    revoke_state: str | None
    revoke_outcome: str | None
    revoke_recorded_at: datetime | None
    last_error: str | None


@dataclass(frozen=True, slots=True)
class _AdmittedAccessToken:
    access_token: str = field(repr=False)
    connection_id: UUID
    generation: int
    credential_version: int
    access_expires_at: datetime

    def __repr__(self) -> str:
        return (
            "_AdmittedAccessToken(access_token=..., connection_id=..., generation=...)"
        )


@dataclass(frozen=True, slots=True)
class GoogleLiveSmokeSnapshot:
    access_token: str = field(repr=False)
    access_expires_at: datetime
    generation: int
    gmail_read_succeeded: bool
    secondary_calendar_found: bool
    calendar_read_succeeded: bool

    def __repr__(self) -> str:
        return (
            "GoogleLiveSmokeSnapshot(access_token=..., access_expires_at=..., "
            "generation=..., read_results=...)"
        )


def _digest(secret: str) -> bytes:
    return hashlib.sha256(secret.encode("utf-8")).digest()


def _snapshot(row: GoogleConnectionRow) -> _ConnectionSnapshot:
    return _ConnectionSnapshot(
        connection_id=row.provider_account_id,
        generation=row.generation,
        credential_version=row.credential_version,
        owner_sub=row.owner_sub,
        granted_scopes=tuple(row.granted_scopes),
        status=row.status,
        encrypted_token_bundle=row.encrypted_token_bundle,
        encryption_key_version=row.encryption_key_version,
        refresh_lease_owner=row.refresh_lease_owner,
        refresh_lease_expires_at=row.refresh_lease_expires_at,
        revoke_state=row.revoke_state,
        revoke_outcome=row.revoke_outcome,
        revoke_recorded_at=row.revoke_recorded_at,
        last_error=row.last_error,
    )


def _revoke_blocked(row: GoogleConnectionRow | _ConnectionSnapshot) -> bool:
    return row.revoke_state in {"in_progress", "unknown"}


def _require_encryption_key(settings: AuthSettings) -> None:
    validate_encryption_key(settings.google_token_encryption_key)


def _decrypt_snapshot(
    snapshot: _ConnectionSnapshot, key: str | None
) -> GoogleTokenBundle:
    if (
        snapshot.encrypted_token_bundle is None
        or snapshot.encryption_key_version != "fernet-v1"
    ):
        raise GoogleConnectionFailure("credentials_unavailable")
    return decrypt_token_bundle(
        snapshot.encrypted_token_bundle,
        key,
        connection_id=snapshot.connection_id,
        owner_sub=snapshot.owner_sub,
    )


def _encrypt_bundle(
    bundle: GoogleTokenBundle,
    settings: AuthSettings,
    *,
    connection_id: UUID,
    owner_sub: str,
) -> tuple[bytes, str]:
    return encrypt_token_bundle(
        bundle,
        settings.google_token_encryption_key,
        connection_id=connection_id,
        owner_sub=owner_sub,
    )


async def begin_google_consent(
    settings: AuthSettings,
    sessions: async_sessionmaker[AsyncSession],
    *,
    owner_sub: str,
    owner_session_token: str,
    browser_cookie: str,
) -> GoogleAuthorization:
    if not hmac.compare_digest(owner_sub, settings.owner_sub):
        raise GoogleConnectionFailure("identity_mismatch")
    _require_encryption_key(settings)
    authorization = create_connection_authorization(
        settings.google_client_id,
        settings.google_client_secret,
        settings.google_connection_callback_uri,
    )
    session_hash = _digest(owner_session_token)
    now = datetime.now(UTC)
    async with sessions() as session, session.begin():
        live_session = await lock_live_owner_session(
            session, session_hash, settings.owner_sub
        )
        if live_session is None:
            raise GoogleConnectionFailure("session_expired")
        from email_support.storage.postgres.persistence.google_connection import (
            ensure_google_connection,
        )

        row = await ensure_google_connection(session, settings.owner_sub)
        if _revoke_blocked(row):
            raise GoogleConnectionFailure("revocation_pending")
        row.generation += 1
        row.revoke_operation_id = None
        row.revoke_state = None
        row.revoke_outcome = None
        row.revoke_recorded_at = None
        row.refresh_lease_owner = None
        row.refresh_lease_expires_at = None
        row.last_error = None
        row.updated_at = now
        await session.execute(
            delete(OAuthAttemptRow).where(
                OAuthAttemptRow.purpose == "google_consent",
                OAuthAttemptRow.connection_id == row.provider_account_id,
            )
        )
        await create_google_consent_attempt(
            session,
            state_digest=_digest(authorization.state),
            browser_digest=_digest(browser_cookie),
            session_digest=session_hash,
            expires_at=now + ATTEMPT_TTL,
            nonce=authorization.nonce,
            code_verifier=authorization.code_verifier,
            connection_id=row.provider_account_id,
            generation=row.generation,
        )
    return authorization


async def consume_google_consent_attempt(
    sessions: async_sessionmaker[AsyncSession],
    *,
    settings: AuthSettings,
    state: str,
    browser_cookie: str,
    owner_session_token: str,
) -> GoogleConsentAttempt | None:
    state_hash = _digest(state)
    browser_hash = _digest(browser_cookie)
    session_hash = _digest(owner_session_token)
    async with sessions() as session, session.begin():
        found = await session.execute(
            select(OAuthAttemptRow.id, OAuthAttemptRow.connection_id).where(
                OAuthAttemptRow.purpose == "google_consent",
                OAuthAttemptRow.state_digest == state_hash,
                OAuthAttemptRow.browser_digest == browser_hash,
                OAuthAttemptRow.session_digest == session_hash,
                OAuthAttemptRow.expires_at > func.now(),
            )
        )
        found_row = found.one_or_none()
        if found_row is None or found_row.connection_id is None:
            return None
        live_session = await lock_live_owner_session(
            session, session_hash, settings.owner_sub
        )
        if live_session is None:
            return None
        connection = await session.scalar(
            select(GoogleConnectionRow)
            .where(GoogleConnectionRow.provider_account_id == found_row.connection_id)
            .with_for_update()
        )
        if connection is None or connection.owner_sub != settings.owner_sub:
            return None
        # Consent creation and consumption lock session, then connection, then attempt.
        attempt = await session.scalar(
            select(OAuthAttemptRow)
            .where(
                OAuthAttemptRow.id == found_row.id,
                OAuthAttemptRow.purpose == "google_consent",
                OAuthAttemptRow.state_digest == state_hash,
                OAuthAttemptRow.browser_digest == browser_hash,
                OAuthAttemptRow.session_digest == session_hash,
                OAuthAttemptRow.expires_at > func.now(),
            )
            .with_for_update()
        )
        if attempt is None:
            return None
        await session.delete(attempt)
        if (
            attempt.generation != connection.generation
            or _revoke_blocked(connection)
            or attempt.nonce is None
            or attempt.code_verifier is None
        ):
            return None
        return GoogleConsentAttempt(
            connection_id=connection.provider_account_id,
            generation=attempt.generation,
            nonce=attempt.nonce,
            code_verifier=attempt.code_verifier,
        )


async def record_google_consent_failure(
    sessions: async_sessionmaker[AsyncSession],
    *,
    settings: AuthSettings,
    attempt: GoogleConsentAttempt,
    code: GoogleConnectionErrorCode,
    owner_session_token: str,
) -> bool:
    session_hash = _digest(owner_session_token)
    async with sessions() as session, session.begin():
        live_session = await lock_live_owner_session(
            session, session_hash, settings.owner_sub
        )
        if live_session is None:
            return False
        row = await session.scalar(
            select(GoogleConnectionRow)
            .where(GoogleConnectionRow.provider_account_id == attempt.connection_id)
            .with_for_update()
        )
        if (
            row is None
            or row.owner_sub != settings.owner_sub
            or row.generation != attempt.generation
            or _revoke_blocked(row)
        ):
            return False
        row.last_error = code.value
        row.updated_at = datetime.now(UTC)
        return True


async def finish_google_consent(
    sessions: async_sessionmaker[AsyncSession],
    *,
    settings: AuthSettings,
    attempt: GoogleConsentAttempt,
    owner_session_token: str,
    identity: GoogleIdentity,
    token_bundle: GoogleTokenBundle,
    granted_scopes: frozenset[str],
) -> GoogleConnectionStatus | None:
    session_hash = _digest(owner_session_token)
    granted = _normalize_scopes(granted_scopes)
    requested = frozenset(CONNECTION_SCOPES)
    missing = [scope for scope in CONNECTION_SCOPES if scope not in granted]
    unexpected = sorted(granted - requested)
    now = datetime.now(UTC)
    async with sessions() as session, session.begin():
        live_session = await lock_live_owner_session(
            session, session_hash, settings.owner_sub
        )
        if live_session is None:
            return None
        row = await session.scalar(
            select(GoogleConnectionRow)
            .where(GoogleConnectionRow.provider_account_id == attempt.connection_id)
            .with_for_update()
        )
        if (
            row is None
            or row.owner_sub != settings.owner_sub
            or row.generation != attempt.generation
            or _revoke_blocked(row)
        ):
            return None
        if not hmac.compare_digest(identity.sub, settings.owner_sub):
            row.last_error = GoogleConnectionErrorCode.IDENTITY_MISMATCH.value
            row.updated_at = now
            return GoogleConnectionStatus(row.status)
        row.granted_scopes = sorted(granted)
        row.refresh_lease_owner = None
        row.refresh_lease_expires_at = None
        if missing or unexpected:
            row.status = GoogleConnectionStatus.RECONNECT_REQUIRED.value
            row.encrypted_token_bundle = None
            row.encryption_key_version = None
            row.credential_version += 1
            row.last_error = GoogleConnectionErrorCode.PARTIAL_SCOPE.value
            row.updated_at = now
            return GoogleConnectionStatus.RECONNECT_REQUIRED
        if token_bundle.access_expires_at <= now:
            row.status = GoogleConnectionStatus.RECONNECT_REQUIRED.value
            row.encrypted_token_bundle = None
            row.encryption_key_version = None
            row.credential_version += 1
            row.last_error = GoogleConnectionErrorCode.PROVIDER_UNAVAILABLE.value
            row.updated_at = now
            return GoogleConnectionStatus.RECONNECT_REQUIRED
        effective_bundle = token_bundle
        if token_bundle.refresh_token is None:
            if row.status == GoogleConnectionStatus.CONNECTED.value:
                try:
                    previous = _decrypt_snapshot(
                        _snapshot(row), settings.google_token_encryption_key
                    )
                except GoogleConnectionFailure:
                    previous = None
                if previous is not None:
                    effective_bundle = GoogleTokenBundle(
                        access_token=token_bundle.access_token,
                        refresh_token=previous.refresh_token,
                        access_expires_at=token_bundle.access_expires_at,
                    )
            if effective_bundle.refresh_token is None:
                row.status = GoogleConnectionStatus.RECONNECT_REQUIRED.value
                row.encrypted_token_bundle = None
                row.encryption_key_version = None
                row.credential_version += 1
                row.last_error = GoogleConnectionErrorCode.CREDENTIALS_UNAVAILABLE.value
                row.updated_at = now
                return GoogleConnectionStatus.RECONNECT_REQUIRED
        try:
            ciphertext, key_version = _encrypt_bundle(
                effective_bundle,
                settings,
                connection_id=row.provider_account_id,
                owner_sub=settings.owner_sub,
            )
        except GoogleConnectionFailure as failure:
            row.status = GoogleConnectionStatus.RECONNECT_REQUIRED.value
            row.encrypted_token_bundle = None
            row.encryption_key_version = None
            row.credential_version += 1
            row.last_error = failure.code.value
            row.updated_at = now
            return GoogleConnectionStatus.RECONNECT_REQUIRED
        row.status = GoogleConnectionStatus.CONNECTED.value
        row.encrypted_token_bundle = ciphertext
        row.encryption_key_version = key_version
        row.credential_version += 1
        row.last_error = None
        row.updated_at = now
        return GoogleConnectionStatus.CONNECTED


def _normalize_scopes(scopes: frozenset[str]) -> frozenset[str]:
    normalized = set(scopes)
    if "https://www.googleapis.com/auth/userinfo.email" in normalized:
        normalized.remove("https://www.googleapis.com/auth/userinfo.email")
        normalized.add("email")
    return frozenset(normalized)


def evaluate_granted_scopes(
    scopes: tuple[str, ...] | list[str] | frozenset[str],
) -> ScopeDecision:
    granted = _normalize_scopes(frozenset(scopes))
    requested = frozenset(REQUESTED_CONNECTION_SCOPES)
    missing = tuple(
        scope for scope in REQUIRED_CONNECTION_SCOPES if scope not in granted
    )
    unexpected = tuple(sorted(granted - requested))
    status = (
        GoogleConnectionStatus.CONNECTED
        if not missing and not unexpected
        else GoogleConnectionStatus.RECONNECT_REQUIRED
    )
    return ScopeDecision(status, missing, unexpected)


async def get_google_connection_status(
    sessions: async_sessionmaker[AsyncSession],
    *,
    owner_sub: str,
    settings: AuthSettings | None = None,
) -> GoogleConnectionResponse:
    async with sessions() as session:
        row = await session.scalar(
            select(GoogleConnectionRow).where(
                GoogleConnectionRow.owner_sub == owner_sub
            )
        )
        if row is None:
            return GoogleConnectionResponse(status=GoogleConnectionStatus.DISCONNECTED)
        scopes = _normalize_scopes(frozenset(row.granted_scopes))
        missing = (
            [scope for scope in CONNECTION_SCOPES if scope not in scopes]
            if row.status == GoogleConnectionStatus.RECONNECT_REQUIRED.value
            else []
        )
        unexpected = sorted(scopes - frozenset(CONNECTION_SCOPES))
        try:
            error = (
                GoogleConnectionErrorCode(row.last_error) if row.last_error else None
            )
        except ValueError:
            error = GoogleConnectionErrorCode.CREDENTIALS_UNAVAILABLE
        if (
            row.status == GoogleConnectionStatus.CONNECTED.value
            and settings is not None
        ):
            try:
                _decrypt_snapshot(_snapshot(row), settings.google_token_encryption_key)
            except GoogleConnectionFailure:
                error = GoogleConnectionErrorCode.CREDENTIALS_UNAVAILABLE
        outcome = RevokeOutcome(row.revoke_outcome) if row.revoke_outcome else None
        return GoogleConnectionResponse(
            status=GoogleConnectionStatus(row.status),
            granted_scopes=sorted(scopes),
            missing_scopes=missing,
            unexpected_scopes=unexpected,
            error=error,
            revoke_outcome=outcome,
            revoke_recorded_at=row.revoke_recorded_at,
            reconnect_blocked=_revoke_blocked(row),
        )


async def disconnect_google_connection(
    sessions: async_sessionmaker[AsyncSession],
    *,
    settings: AuthSettings,
    owner_session_token: str,
    workspace: GoogleWorkspaceClient,
) -> GoogleDisconnectResponse:
    session_hash = _digest(owner_session_token)
    operation_id: UUID | None = None
    generation: int | None = None
    token_snapshot: str | None = None
    now = datetime.now(UTC)
    async with sessions() as session, session.begin():
        live_session = await lock_live_owner_session(
            session, session_hash, settings.owner_sub
        )
        if live_session is None:
            raise GoogleConnectionFailure("session_expired")
        row = await session.scalar(
            select(GoogleConnectionRow)
            .where(GoogleConnectionRow.owner_sub == settings.owner_sub)
            .with_for_update()
        )
        if row is None:
            return GoogleDisconnectResponse(
                status=GoogleConnectionStatus.DISCONNECTED,
                revoke_outcome=RevokeOutcome.NOT_ATTEMPTED,
                reconnect_blocked=False,
            )
        if _revoke_blocked(row):
            outcome = RevokeOutcome(row.revoke_outcome or RevokeOutcome.UNKNOWN.value)
            return GoogleDisconnectResponse(
                status=GoogleConnectionStatus.DISCONNECTED,
                revoke_outcome=outcome,
                revoke_recorded_at=row.revoke_recorded_at,
                reconnect_blocked=_revoke_blocked(row),
            )
        if (
            row.status == GoogleConnectionStatus.DISCONNECTED.value
            and row.encrypted_token_bundle is None
            and row.revoke_state == "resolved"
        ):
            return GoogleDisconnectResponse(
                status=GoogleConnectionStatus.DISCONNECTED,
                revoke_outcome=RevokeOutcome(row.revoke_outcome or "not_attempted"),
                revoke_recorded_at=row.revoke_recorded_at,
                reconnect_blocked=False,
            )
        if row.encrypted_token_bundle is not None:
            try:
                bundle = _decrypt_snapshot(
                    _snapshot(row), settings.google_token_encryption_key
                )
                token_snapshot = bundle.refresh_token or bundle.access_token
            except GoogleConnectionFailure:
                # Keep reconnect gated when the stored grant cannot be decrypted.
                operation_id = uuid4()
                generation = row.generation + 1
                row.revoke_operation_id = operation_id
                row.revoke_state = "unknown"
                row.revoke_outcome = RevokeOutcome.UNKNOWN.value
                row.revoke_recorded_at = now
                row.last_error = GoogleConnectionErrorCode.REVOCATION_PENDING.value
        row.generation += 1
        row.credential_version += 1
        row.status = GoogleConnectionStatus.DISCONNECTED.value
        row.encrypted_token_bundle = None
        row.encryption_key_version = None
        row.refresh_lease_owner = None
        row.refresh_lease_expires_at = None
        row.updated_at = now
        await session.execute(
            delete(OAuthAttemptRow).where(
                OAuthAttemptRow.purpose == "google_consent",
                OAuthAttemptRow.connection_id == row.provider_account_id,
            )
        )
        if token_snapshot is not None:
            operation_id = uuid4()
            generation = row.generation
            row.revoke_operation_id = operation_id
            row.revoke_state = "in_progress"
            row.revoke_outcome = RevokeOutcome.UNKNOWN.value
            row.revoke_recorded_at = now
            row.last_error = GoogleConnectionErrorCode.REVOCATION_PENDING.value
        elif row.revoke_state is None:
            row.revoke_operation_id = None
            row.revoke_state = "resolved"
            row.revoke_outcome = RevokeOutcome.NOT_ATTEMPTED.value
            row.revoke_recorded_at = now
            row.last_error = None
    if token_snapshot is None or operation_id is None or generation is None:
        async with sessions() as session:
            row = await session.scalar(
                select(GoogleConnectionRow).where(
                    GoogleConnectionRow.owner_sub == settings.owner_sub
                )
            )
            if row is None:
                return GoogleDisconnectResponse(
                    status=GoogleConnectionStatus.DISCONNECTED,
                    revoke_outcome=RevokeOutcome.NOT_ATTEMPTED,
                    reconnect_blocked=False,
                )
            return GoogleDisconnectResponse(
                status=GoogleConnectionStatus.DISCONNECTED,
                revoke_outcome=RevokeOutcome(row.revoke_outcome or "unknown"),
                revoke_recorded_at=row.revoke_recorded_at,
                reconnect_blocked=_revoke_blocked(row),
            )
    confirmed = await workspace.revoke(token_snapshot)
    outcome = RevokeOutcome.CONFIRMED if confirmed else RevokeOutcome.UNKNOWN
    async with sessions() as session, session.begin():
        row = await session.scalar(
            select(GoogleConnectionRow)
            .where(
                GoogleConnectionRow.owner_sub == settings.owner_sub,
                GoogleConnectionRow.revoke_operation_id == operation_id,
            )
            .with_for_update()
        )
        if row is not None and row.generation == generation:
            row.revoke_state = "resolved" if confirmed else "unknown"
            row.revoke_outcome = outcome.value
            row.revoke_recorded_at = datetime.now(UTC)
            row.last_error = (
                None
                if confirmed
                else GoogleConnectionErrorCode.REVOCATION_PENDING.value
            )
            row.updated_at = datetime.now(UTC)
            return GoogleDisconnectResponse(
                status=GoogleConnectionStatus.DISCONNECTED,
                revoke_outcome=outcome,
                revoke_recorded_at=row.revoke_recorded_at,
                reconnect_blocked=_revoke_blocked(row),
            )
    return GoogleDisconnectResponse(
        status=GoogleConnectionStatus.DISCONNECTED,
        revoke_outcome=RevokeOutcome.UNKNOWN,
        reconnect_blocked=True,
    )


async def _load_snapshot(
    sessions: async_sessionmaker[AsyncSession], owner_sub: str
) -> _ConnectionSnapshot | None:
    async with sessions() as session:
        row = await session.scalar(
            select(GoogleConnectionRow).where(
                GoogleConnectionRow.owner_sub == owner_sub
            )
        )
        return _snapshot(row) if row is not None else None


def _require_product_access(snapshot: _ConnectionSnapshot) -> None:
    if snapshot.revoke_state in {"in_progress", "unknown"}:
        raise GoogleConnectionFailure("revocation_pending")
    if snapshot.status != GoogleConnectionStatus.CONNECTED.value:
        if snapshot.last_error:
            raise GoogleConnectionFailure(snapshot.last_error)
        if snapshot.status == GoogleConnectionStatus.DISCONNECTED.value:
            raise GoogleConnectionFailure("credentials_unavailable")
        raise GoogleConnectionFailure("partial_scope")
    granted = _normalize_scopes(frozenset(snapshot.granted_scopes))
    if any(scope not in granted for scope in CONNECTION_SCOPES):
        raise GoogleConnectionFailure("partial_scope")


async def _access_token(
    sessions: async_sessionmaker[AsyncSession],
    *,
    settings: AuthSettings,
    workspace: GoogleWorkspaceClient,
    minimum_lifetime: timedelta = ACCESS_TOKEN_SAFETY_MARGIN,
) -> _AdmittedAccessToken:
    deadline = time.monotonic() + REFRESH_FOLLOWER_DEADLINE_SECONDS
    while True:
        snapshot = await _load_snapshot(sessions, settings.owner_sub)
        if snapshot is None:
            raise GoogleConnectionFailure("partial_scope")
        _require_product_access(snapshot)
        bundle = _decrypt_snapshot(snapshot, settings.google_token_encryption_key)
        now = datetime.now(UTC)
        if bundle.access_expires_at > now + minimum_lifetime:
            return _AdmittedAccessToken(
                bundle.access_token,
                snapshot.connection_id,
                snapshot.generation,
                snapshot.credential_version,
                bundle.access_expires_at,
            )
        if not bundle.refresh_token:
            raise GoogleConnectionFailure("refresh_invalid")
        lease_owner = uuid4()
        async with sessions() as session, session.begin():
            claimed = await claim_refresh_lease(
                session,
                connection_id=snapshot.connection_id,
                generation=snapshot.generation,
                credential_version=snapshot.credential_version,
                lease_owner=lease_owner,
                lease_duration=REFRESH_LEASE_TTL,
            )
        if not claimed:
            if time.monotonic() >= deadline:
                raise GoogleConnectionFailure("refresh_busy")
            await asyncio.sleep(
                min(random.uniform(0.05, 0.25), max(0.01, deadline - time.monotonic()))
            )
            continue
        try:
            refreshed = await workspace.refresh(
                bundle.refresh_token,
                client_id=settings.google_client_id,
                client_secret=settings.google_client_secret,
            )
        except GoogleConnectionFailure as failure:
            async with sessions() as session, session.begin():
                if failure.code is GoogleConnectionErrorCode.REFRESH_INVALID:
                    invalidated = await invalidate_refresh_grant(
                        session,
                        connection_id=snapshot.connection_id,
                        generation=snapshot.generation,
                        credential_version=snapshot.credential_version,
                        lease_owner=lease_owner,
                    )
                    if not invalidated:
                        continue
                else:
                    await release_refresh_lease(
                        session,
                        connection_id=snapshot.connection_id,
                        generation=snapshot.generation,
                        credential_version=snapshot.credential_version,
                        lease_owner=lease_owner,
                    )
            raise
        except BaseException:
            async with sessions() as session, session.begin():
                await release_refresh_lease(
                    session,
                    connection_id=snapshot.connection_id,
                    generation=snapshot.generation,
                    credential_version=snapshot.credential_version,
                    lease_owner=lease_owner,
                )
            raise
        refresh_token = refreshed.token_bundle.refresh_token or bundle.refresh_token
        if (
            refreshed.token_bundle.access_expires_at
            <= datetime.now(UTC) + minimum_lifetime
        ):
            async with sessions() as session, session.begin():
                await release_refresh_lease(
                    session,
                    connection_id=snapshot.connection_id,
                    generation=snapshot.generation,
                    credential_version=snapshot.credential_version,
                    lease_owner=lease_owner,
                )
            raise GoogleConnectionFailure("provider_unavailable")
        updated_bundle = GoogleTokenBundle(
            access_token=refreshed.token_bundle.access_token,
            refresh_token=refresh_token,
            access_expires_at=refreshed.token_bundle.access_expires_at,
        )
        ciphertext, key_version = _encrypt_bundle(
            updated_bundle,
            settings,
            connection_id=snapshot.connection_id,
            owner_sub=settings.owner_sub,
        )
        async with sessions() as session, session.begin():
            saved = await save_refreshed_bundle(
                session,
                connection_id=snapshot.connection_id,
                generation=snapshot.generation,
                credential_version=snapshot.credential_version,
                lease_owner=lease_owner,
                encrypted_bundle=ciphertext,
                key_version=key_version,
            )
        if saved:
            continue
        # Disconnect, new consent or lease expiry won the compare-and-swap.
        if time.monotonic() >= deadline:
            raise GoogleConnectionFailure("refresh_busy")


async def _admit_operation(
    sessions: async_sessionmaker[AsyncSession],
    token: _AdmittedAccessToken,
    owner_sub: str,
) -> None:
    async with sessions() as session, session.begin():
        row = await session.scalar(
            select(GoogleConnectionRow)
            .where(GoogleConnectionRow.provider_account_id == token.connection_id)
            .with_for_update()
        )
        if row is None or row.owner_sub != owner_sub:
            raise GoogleConnectionFailure("revocation_pending")
        _require_product_access(_snapshot(row))
        if row.generation != token.generation:
            raise GoogleConnectionFailure("revocation_pending")
        if row.credential_version != token.credential_version:
            raise GoogleConnectionFailure("refresh_busy")


async def _verify_generation(
    sessions: async_sessionmaker[AsyncSession], token: _AdmittedAccessToken
) -> None:
    async with sessions() as session:
        current = await is_connection_generation_current(
            session,
            connection_id=token.connection_id,
            generation=token.generation,
        )
    if not current:
        raise GoogleConnectionFailure("revocation_pending")


async def read_gmail_metadata(
    sessions: async_sessionmaker[AsyncSession],
    *,
    settings: AuthSettings,
    workspace: GoogleWorkspaceClient,
) -> GmailMessageMetadata | None:
    token = await _access_token(sessions, settings=settings, workspace=workspace)
    await _admit_operation(sessions, token, settings.owner_sub)
    result = await workspace.read_gmail_metadata(token.access_token)
    await _verify_generation(sessions, token)
    return result


async def read_secondary_calendar_event(
    sessions: async_sessionmaker[AsyncSession],
    *,
    settings: AuthSettings,
    workspace: GoogleWorkspaceClient,
) -> CalendarEventSummary | None:
    token = await _access_token(sessions, settings=settings, workspace=workspace)
    await _admit_operation(sessions, token, settings.owner_sub)
    result = await workspace.read_secondary_calendar_event(token.access_token)
    await _verify_generation(sessions, token)
    return result


async def read_secondary_calendar(
    sessions: async_sessionmaker[AsyncSession],
    *,
    settings: AuthSettings,
    workspace: GoogleWorkspaceClient,
) -> CalendarReadResult:
    token = await _access_token(sessions, settings=settings, workspace=workspace)
    await _admit_operation(sessions, token, settings.owner_sub)
    result = await workspace.read_secondary_calendar(token.access_token)
    await _verify_generation(sessions, token)
    return result


async def prepare_live_google_smoke(
    sessions: async_sessionmaker[AsyncSession],
    *,
    settings: AuthSettings,
    workspace: GoogleWorkspaceClient,
) -> GoogleLiveSmokeSnapshot:
    """Read minimal Gmail/Calendar data and retain a long-lived token in memory."""
    minimum_lifetime = timedelta(seconds=160)
    for _ in range(3):
        token = await _access_token(
            sessions,
            settings=settings,
            workspace=workspace,
            minimum_lifetime=minimum_lifetime,
        )
        await _admit_operation(sessions, token, settings.owner_sub)
        await workspace.read_gmail_metadata(token.access_token)
        await _verify_generation(sessions, token)

        await _admit_operation(sessions, token, settings.owner_sub)
        calendar = await workspace.read_secondary_calendar(token.access_token)
        await _verify_generation(sessions, token)

        snapshot = GoogleLiveSmokeSnapshot(
            access_token=token.access_token,
            access_expires_at=token.access_expires_at,
            generation=token.generation,
            gmail_read_succeeded=True,
            secondary_calendar_found=calendar.secondary_calendar_found,
            calendar_read_succeeded=True,
        )
        if not calendar.secondary_calendar_found:
            return snapshot
        if token.access_expires_at - datetime.now(UTC) > minimum_lifetime:
            return snapshot
    raise GoogleConnectionFailure("provider_unavailable")
