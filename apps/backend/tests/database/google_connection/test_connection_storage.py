"""Real PostgreSQL tests for owner-bound consent and stale-result fences."""

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from email_support.config import AuthSettings
from email_support.integrations.google_oidc import (
    CONNECTION_SCOPES,
    GoogleAuthorization,
    GoogleIdentity,
)
from email_support.integrations.google_workspace import (
    CalendarEventSummary,
    GmailMessageMetadata,
    GoogleRefreshResult,
    GoogleWorkspaceClient,
)
from email_support.models.google_connection import (
    GoogleConnectionErrorCode,
    GoogleConnectionFailure,
    GoogleConnectionStatus,
    GoogleTokenBundle,
)
from email_support.services.auth import SESSION_TTL
from email_support.services.google_connection import (
    begin_google_consent,
    consume_google_consent_attempt,
    disconnect_google_connection,
    finish_google_consent,
    get_google_connection_status,
    read_gmail_metadata,
)
from email_support.services.google_connection_crypto import (
    decrypt_token_bundle,
    encrypt_token_bundle,
)
from email_support.storage.postgres.persistence.auth import create_owner_session
from email_support.storage.postgres.persistence.google_connection import (
    claim_refresh_lease,
    save_refreshed_bundle,
)
from email_support.storage.postgres.persistence.tables.auth import (
    OAuthAttemptRow,
    OwnerSessionRow,
)
from email_support.storage.postgres.persistence.tables.core import ProviderAccountRow
from email_support.storage.postgres.persistence.tables.google_connection import (
    GoogleConnectionRow,
)

OWNER_SUB = "configured-owner-subject"
SESSION_TOKEN = "owner-session-token"
BROWSER_COOKIE = "owner-browser-cookie"
ENCRYPTION_KEY = Fernet.generate_key().decode()


def make_settings() -> AuthSettings:
    return AuthSettings(
        database_url="postgresql+psycopg://user:pass@db/app",
        owner_sub=OWNER_SUB,
        google_client_id="client-id",
        google_client_secret="client-secret",
        callback_uri="https://support.example/api/auth/google/callback",
        web_origin="https://support.example",
        google_token_encryption_key=ENCRYPTION_KEY,
    )


async def seed_owner_session(
    sessions: async_sessionmaker[AsyncSession], token: str = SESSION_TOKEN
) -> None:
    now = datetime.now(UTC)
    async with sessions() as session, session.begin():
        await create_owner_session(
            session,
            token_digest=hashlib.sha256(token.encode()).digest(),
            owner_sub=OWNER_SUB,
            created_at=now,
            expires_at=now + SESSION_TTL,
            csrf_secret="csrf-token",
        )


async def start_attempt(
    sessions: async_sessionmaker[AsyncSession],
    *,
    owner_token: str = SESSION_TOKEN,
    browser_cookie: str = BROWSER_COOKIE,
) -> GoogleAuthorization:
    return await begin_google_consent(
        make_settings(),
        sessions,
        owner_sub=OWNER_SUB,
        owner_session_token=owner_token,
        browser_cookie=browser_cookie,
    )


async def complete_consent(
    sessions: async_sessionmaker[AsyncSession],
) -> UUID:
    connection_id, status = await finish_grant(
        sessions,
        token_bundle=GoogleTokenBundle(
            access_token="stored-access-token",
            refresh_token="stored-refresh-token",
            access_expires_at=datetime.now(UTC) + timedelta(hours=1),
        ),
        granted_scopes=frozenset(CONNECTION_SCOPES),
    )
    assert status is GoogleConnectionStatus.CONNECTED
    return connection_id


async def finish_grant(
    sessions: async_sessionmaker[AsyncSession],
    *,
    token_bundle: GoogleTokenBundle,
    granted_scopes: frozenset[str],
) -> tuple[UUID, GoogleConnectionStatus | None]:
    settings = make_settings()
    authorization = await start_attempt(sessions)
    attempt = await consume_google_consent_attempt(
        sessions,
        settings=settings,
        state=authorization.state,
        browser_cookie=BROWSER_COOKIE,
        owner_session_token=SESSION_TOKEN,
    )
    assert attempt is not None
    status = await finish_google_consent(
        sessions,
        settings=settings,
        attempt=attempt,
        owner_session_token=SESSION_TOKEN,
        identity=GoogleIdentity(sub=OWNER_SUB, email="owner@example.test"),
        token_bundle=token_bundle,
        granted_scopes=granted_scopes,
    )
    return attempt.connection_id, status


class FakeWorkspace:
    def __init__(self, *, revoke_result: bool = True) -> None:
        self.revoke_result = revoke_result
        self.revoke_calls: list[str] = []
        self.refresh_calls = 0
        self.refresh_started = asyncio.Event()
        self.refresh_release = asyncio.Event()
        self.read_started = asyncio.Event()
        self.read_release = asyncio.Event()
        self.block_refresh = False
        self.block_read = False
        self.refresh_failure: GoogleConnectionErrorCode | None = None
        self.before_revoke: Callable[[], Awaitable[None]] | None = None

    async def revoke(self, token: str) -> bool:
        self.revoke_calls.append(token)
        if self.before_revoke is not None:
            await self.before_revoke()
        return self.revoke_result

    async def refresh(
        self, refresh_token: str, *, client_id: str, client_secret: str
    ) -> GoogleRefreshResult:
        assert refresh_token == "stored-refresh-token"
        assert client_id == "client-id"
        assert client_secret == "client-secret"
        self.refresh_calls += 1
        self.refresh_started.set()
        if self.block_refresh:
            await self.refresh_release.wait()
        if self.refresh_failure is not None:
            raise GoogleConnectionFailure(self.refresh_failure)
        return GoogleRefreshResult(
            GoogleTokenBundle(
                access_token="new-access-token",
                refresh_token=None,
                access_expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )

    async def read_gmail_metadata(
        self, access_token: str
    ) -> GmailMessageMetadata | None:
        assert (
            access_token == "new-access-token" or access_token == "stored-access-token"
        )
        self.read_started.set()
        if self.block_read:
            await self.read_release.wait()
        return None

    async def read_secondary_calendar_event(
        self, access_token: str
    ) -> CalendarEventSummary | None:
        del access_token
        return None


@pytest.mark.asyncio
async def test_consent_attempt_is_bound_to_live_session_browser_and_generation(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    await seed_owner_session(database_sessions)
    settings = make_settings()
    authorization = await start_attempt(database_sessions)

    wrong_browser = await consume_google_consent_attempt(
        database_sessions,
        settings=settings,
        state=authorization.state,
        browser_cookie="different-browser",
        owner_session_token=SESSION_TOKEN,
    )
    valid = await consume_google_consent_attempt(
        database_sessions,
        settings=settings,
        state=authorization.state,
        browser_cookie=BROWSER_COOKIE,
        owner_session_token=SESSION_TOKEN,
    )
    replay = await consume_google_consent_attempt(
        database_sessions,
        settings=settings,
        state=authorization.state,
        browser_cookie=BROWSER_COOKIE,
        owner_session_token=SESSION_TOKEN,
    )

    assert wrong_browser is None
    assert valid is not None
    assert valid.generation == 1
    assert replay is None


@pytest.mark.asyncio
async def test_consent_attempt_rejects_wrong_session_and_expiry(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    await seed_owner_session(database_sessions)
    settings = make_settings()
    authorization = await start_attempt(database_sessions)

    wrong_session = await consume_google_consent_attempt(
        database_sessions,
        settings=settings,
        state=authorization.state,
        browser_cookie=BROWSER_COOKIE,
        owner_session_token="another-session-token",
    )
    async with database_sessions() as session, session.begin():
        attempt = await session.scalar(
            select(OAuthAttemptRow).where(
                OAuthAttemptRow.state_digest
                == hashlib.sha256(authorization.state.encode()).digest()
            )
        )
        assert attempt is not None
        attempt.expires_at = datetime.now(UTC) - timedelta(hours=1)

    expired = await consume_google_consent_attempt(
        database_sessions,
        settings=settings,
        state=authorization.state,
        browser_cookie=BROWSER_COOKIE,
        owner_session_token=SESSION_TOKEN,
    )

    assert wrong_session is None
    assert expired is None


@pytest.mark.asyncio
async def test_login_purpose_attempt_cannot_be_consumed_as_google_consent(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    await seed_owner_session(database_sessions)
    settings = make_settings()
    authorization = await start_attempt(database_sessions)
    async with database_sessions() as session, session.begin():
        attempt = await session.scalar(
            select(OAuthAttemptRow).where(
                OAuthAttemptRow.state_digest
                == hashlib.sha256(authorization.state.encode()).digest()
            )
        )
        assert attempt is not None
        attempt.purpose = "login"
        attempt.connection_id = None
        attempt.session_digest = None
        attempt.generation = None

    result = await consume_google_consent_attempt(
        database_sessions,
        settings=settings,
        state=authorization.state,
        browser_cookie=BROWSER_COOKIE,
        owner_session_token=SESSION_TOKEN,
    )

    assert result is None


@pytest.mark.asyncio
async def test_new_consent_generation_rejects_a_late_callback(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    await seed_owner_session(database_sessions)
    settings = make_settings()
    first_authorization = await start_attempt(database_sessions)
    first_attempt = await consume_google_consent_attempt(
        database_sessions,
        settings=settings,
        state=first_authorization.state,
        browser_cookie=BROWSER_COOKIE,
        owner_session_token=SESSION_TOKEN,
    )
    assert first_attempt is not None

    second_authorization = await start_attempt(database_sessions)
    second_attempt = await consume_google_consent_attempt(
        database_sessions,
        settings=settings,
        state=second_authorization.state,
        browser_cookie=BROWSER_COOKIE,
        owner_session_token=SESSION_TOKEN,
    )
    assert second_attempt is not None
    grant = GoogleTokenBundle(
        access_token="new-consent-access-token",
        refresh_token="new-consent-refresh-token",
        access_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    stale = await finish_google_consent(
        database_sessions,
        settings=settings,
        attempt=first_attempt,
        owner_session_token=SESSION_TOKEN,
        identity=GoogleIdentity(sub=OWNER_SUB, email="owner@example.test"),
        token_bundle=grant,
        granted_scopes=frozenset(CONNECTION_SCOPES),
    )
    accepted = await finish_google_consent(
        database_sessions,
        settings=settings,
        attempt=second_attempt,
        owner_session_token=SESSION_TOKEN,
        identity=GoogleIdentity(sub=OWNER_SUB, email="owner@example.test"),
        token_bundle=grant,
        granted_scopes=frozenset(CONNECTION_SCOPES),
    )

    async with database_sessions() as session:
        row = await session.get(GoogleConnectionRow, second_attempt.connection_id)

    assert stale is None
    assert accepted is GoogleConnectionStatus.CONNECTED
    assert row is not None and row.status == GoogleConnectionStatus.CONNECTED.value


@pytest.mark.asyncio
async def test_different_google_subject_never_persists_callback_credentials(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    await seed_owner_session(database_sessions)
    settings = make_settings()
    authorization = await start_attempt(database_sessions)
    attempt = await consume_google_consent_attempt(
        database_sessions,
        settings=settings,
        state=authorization.state,
        browser_cookie=BROWSER_COOKIE,
        owner_session_token=SESSION_TOKEN,
    )
    assert attempt is not None

    status = await finish_google_consent(
        database_sessions,
        settings=settings,
        attempt=attempt,
        owner_session_token=SESSION_TOKEN,
        identity=GoogleIdentity(
            sub="different-google-subject", email="owner@example.test"
        ),
        token_bundle=GoogleTokenBundle(
            access_token="wrong-subject-access-token",
            refresh_token="wrong-subject-refresh-token",
            access_expires_at=datetime.now(UTC) + timedelta(hours=1),
        ),
        granted_scopes=frozenset(CONNECTION_SCOPES),
    )

    async with database_sessions() as session:
        row = await session.get(GoogleConnectionRow, attempt.connection_id)

    assert status is GoogleConnectionStatus.DISCONNECTED
    assert row is not None
    assert row.last_error == GoogleConnectionErrorCode.IDENTITY_MISMATCH.value
    assert row.encrypted_token_bundle is None


@pytest.mark.asyncio
async def test_reauthorization_replaces_a_rotated_refresh_token(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    await seed_owner_session(database_sessions)
    connection_id = await complete_consent(database_sessions)

    _, status = await finish_grant(
        database_sessions,
        token_bundle=GoogleTokenBundle(
            access_token="reauthorized-access-token",
            refresh_token="rotated-refresh-token",
            access_expires_at=datetime.now(UTC) + timedelta(hours=1),
        ),
        granted_scopes=frozenset(CONNECTION_SCOPES),
    )

    async with database_sessions() as session:
        row = await session.get(GoogleConnectionRow, connection_id)
    assert status is GoogleConnectionStatus.CONNECTED
    assert row is not None and row.encrypted_token_bundle is not None
    bundle = decrypt_token_bundle(
        row.encrypted_token_bundle,
        ENCRYPTION_KEY,
        connection_id=connection_id,
        owner_sub=OWNER_SUB,
    )
    assert bundle.refresh_token == "rotated-refresh-token"


@pytest.mark.asyncio
async def test_completed_grant_stores_only_context_bound_ciphertext(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    await seed_owner_session(database_sessions)
    connection_id = await complete_consent(database_sessions)
    async with database_sessions() as session:
        row = await session.scalar(select(GoogleConnectionRow))
    assert row is not None
    assert row.provider_account_id == connection_id
    assert row.status == "connected"
    assert row.encrypted_token_bundle is not None
    assert b"stored-access-token" not in row.encrypted_token_bundle
    assert b"stored-refresh-token" not in row.encrypted_token_bundle
    decrypted = decrypt_token_bundle(
        row.encrypted_token_bundle,
        ENCRYPTION_KEY,
        connection_id=connection_id,
        owner_sub=OWNER_SUB,
    )
    assert decrypted.access_token == "stored-access-token"
    assert decrypted.refresh_token == "stored-refresh-token"
    public_status = await get_google_connection_status(
        database_sessions, owner_sub=OWNER_SUB
    )
    assert "stored-access-token" not in public_status.model_dump_json()
    assert "stored-refresh-token" not in public_status.model_dump_json()


@pytest.mark.asyncio
async def test_initial_grant_without_refresh_token_stays_reconnect_required(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    await seed_owner_session(database_sessions)
    connection_id, status = await finish_grant(
        database_sessions,
        token_bundle=GoogleTokenBundle(
            access_token="access-without-offline-grant",
            refresh_token=None,
            access_expires_at=datetime.now(UTC) + timedelta(hours=1),
        ),
        granted_scopes=frozenset(CONNECTION_SCOPES),
    )

    async with database_sessions() as session:
        row = await session.get(GoogleConnectionRow, connection_id)

    assert status is GoogleConnectionStatus.RECONNECT_REQUIRED
    assert row is not None
    assert row.status == GoogleConnectionStatus.RECONNECT_REQUIRED.value
    assert row.encrypted_token_bundle is None
    assert row.last_error == "credentials_unavailable"


@pytest.mark.asyncio
async def test_partial_grant_persists_actual_scopes_without_credentials(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    await seed_owner_session(database_sessions)
    partial_scopes = frozenset(CONNECTION_SCOPES[:-1])
    connection_id, status = await finish_grant(
        database_sessions,
        token_bundle=GoogleTokenBundle(
            access_token="partial-access-token",
            refresh_token="partial-refresh-token",
            access_expires_at=datetime.now(UTC) + timedelta(hours=1),
        ),
        granted_scopes=partial_scopes,
    )

    async with database_sessions() as session:
        row = await session.get(GoogleConnectionRow, connection_id)

    assert status is GoogleConnectionStatus.RECONNECT_REQUIRED
    assert row is not None
    assert row.status == GoogleConnectionStatus.RECONNECT_REQUIRED.value
    assert row.granted_scopes == sorted(partial_scopes)
    assert row.encrypted_token_bundle is None
    response = await get_google_connection_status(
        database_sessions, owner_sub=OWNER_SUB
    )
    assert response.missing_scopes == [CONNECTION_SCOPES[-1]]


@pytest.mark.asyncio
async def test_reauthorization_without_new_refresh_token_preserves_existing_grant(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    await seed_owner_session(database_sessions)
    connection_id = await complete_consent(database_sessions)
    _, status = await finish_grant(
        database_sessions,
        token_bundle=GoogleTokenBundle(
            access_token="reauthorized-access-token",
            refresh_token=None,
            access_expires_at=datetime.now(UTC) + timedelta(hours=1),
        ),
        granted_scopes=frozenset(CONNECTION_SCOPES),
    )

    async with database_sessions() as session:
        row = await session.get(GoogleConnectionRow, connection_id)

    assert status is GoogleConnectionStatus.CONNECTED
    assert row is not None and row.encrypted_token_bundle is not None
    bundle = decrypt_token_bundle(
        row.encrypted_token_bundle,
        ENCRYPTION_KEY,
        connection_id=connection_id,
        owner_sub=OWNER_SUB,
    )
    assert bundle.access_token == "reauthorized-access-token"
    assert bundle.refresh_token == "stored-refresh-token"


@pytest.mark.asyncio
async def test_disconnect_fences_a_callback_consumed_before_disconnect(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    await seed_owner_session(database_sessions)
    settings = make_settings()
    authorization = await start_attempt(database_sessions)
    attempt = await consume_google_consent_attempt(
        database_sessions,
        settings=settings,
        state=authorization.state,
        browser_cookie=BROWSER_COOKIE,
        owner_session_token=SESSION_TOKEN,
    )
    assert attempt is not None

    await disconnect_google_connection(
        database_sessions,
        settings=settings,
        owner_session_token=SESSION_TOKEN,
        workspace=cast(GoogleWorkspaceClient, FakeWorkspace()),
    )
    result = await finish_google_consent(
        database_sessions,
        settings=settings,
        attempt=attempt,
        owner_session_token=SESSION_TOKEN,
        identity=GoogleIdentity(sub=OWNER_SUB, email="owner@example.test"),
        token_bundle=GoogleTokenBundle(
            access_token="late-access-token",
            refresh_token="late-refresh-token",
            access_expires_at=datetime.now(UTC) + timedelta(hours=1),
        ),
        granted_scopes=frozenset(CONNECTION_SCOPES),
    )

    async with database_sessions() as session:
        row = await session.get(GoogleConnectionRow, attempt.connection_id)

    assert result is None
    assert row is not None
    assert row.status == GoogleConnectionStatus.DISCONNECTED.value
    assert row.encrypted_token_bundle is None


@pytest.mark.asyncio
@pytest.mark.parametrize("invalidation", ["logout", "expiry"])
async def test_session_invalidation_fences_callback_waiting_on_final_lock(
    database_sessions: async_sessionmaker[AsyncSession], invalidation: str
) -> None:
    await seed_owner_session(database_sessions)
    settings = make_settings()
    authorization = await start_attempt(database_sessions)
    attempt = await consume_google_consent_attempt(
        database_sessions,
        settings=settings,
        state=authorization.state,
        browser_cookie=BROWSER_COOKIE,
        owner_session_token=SESSION_TOKEN,
    )
    assert attempt is not None

    session_digest = hashlib.sha256(SESSION_TOKEN.encode()).digest()
    callback: asyncio.Task[GoogleConnectionStatus | None]
    async with database_sessions() as invalidating_session:
        async with invalidating_session.begin():
            locked_session = await invalidating_session.scalar(
                select(OwnerSessionRow)
                .where(OwnerSessionRow.token_digest == session_digest)
                .with_for_update()
            )
            assert locked_session is not None
            callback = asyncio.create_task(
                finish_google_consent(
                    database_sessions,
                    settings=settings,
                    attempt=attempt,
                    owner_session_token=SESSION_TOKEN,
                    identity=GoogleIdentity(sub=OWNER_SUB, email="owner@example.test"),
                    token_bundle=GoogleTokenBundle(
                        access_token="late-access-token",
                        refresh_token="late-refresh-token",
                        access_expires_at=datetime.now(UTC) + timedelta(hours=1),
                    ),
                    granted_scopes=frozenset(CONNECTION_SCOPES),
                )
            )

            deadline = asyncio.get_running_loop().time() + 2
            while True:
                async with database_sessions() as observer:
                    waiting_callbacks = await observer.scalar(
                        text(
                            "SELECT count(*) FROM pg_stat_activity "
                            "WHERE pid <> pg_backend_pid() "
                            "AND wait_event_type = 'Lock' "
                            "AND query ILIKE '%owner_sessions%'"
                        )
                    )
                if waiting_callbacks:
                    break
                if asyncio.get_running_loop().time() >= deadline:
                    raise AssertionError("callback did not wait on the session lock")
                await asyncio.sleep(0.01)

            if invalidation == "logout":
                await invalidating_session.execute(
                    delete(OwnerSessionRow).where(
                        OwnerSessionRow.token_digest == session_digest
                    )
                )
            else:
                locked_session.expires_at = locked_session.created_at + timedelta(
                    microseconds=1
                )

    result = await callback
    async with database_sessions() as session:
        row = await session.get(GoogleConnectionRow, attempt.connection_id)

    assert result is None
    assert row is not None
    assert row.status == GoogleConnectionStatus.DISCONNECTED.value
    assert row.encrypted_token_bundle is None


@pytest.mark.asyncio
async def test_owner_logout_keeps_the_independent_google_connection(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    await seed_owner_session(database_sessions)
    connection_id = await complete_consent(database_sessions)
    async with database_sessions() as session, session.begin():
        await session.execute(
            delete(OwnerSessionRow).where(
                OwnerSessionRow.token_digest
                == hashlib.sha256(SESSION_TOKEN.encode()).digest()
            )
        )

    status = await get_google_connection_status(database_sessions, owner_sub=OWNER_SUB)
    async with database_sessions() as session:
        row = await session.get(GoogleConnectionRow, connection_id)

    assert status.status is GoogleConnectionStatus.CONNECTED
    assert row is not None and row.encrypted_token_bundle is not None


@pytest.mark.asyncio
async def test_unknown_revoke_purges_first_and_cannot_be_replayed_or_reconnected(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    await seed_owner_session(database_sessions)
    await complete_consent(database_sessions)
    settings = make_settings()
    authorization = await start_attempt(database_sessions)
    pending_attempt = await consume_google_consent_attempt(
        database_sessions,
        settings=settings,
        state=authorization.state,
        browser_cookie=BROWSER_COOKIE,
        owner_session_token=SESSION_TOKEN,
    )
    assert pending_attempt is not None
    workspace = FakeWorkspace(revoke_result=False)

    async def assert_local_block_is_committed() -> None:
        async with database_sessions() as session:
            before_provider_call = await session.scalar(select(GoogleConnectionRow))
        assert before_provider_call is not None
        assert before_provider_call.status == GoogleConnectionStatus.DISCONNECTED.value
        assert before_provider_call.encrypted_token_bundle is None
        assert before_provider_call.revoke_state == "in_progress"

    workspace.before_revoke = assert_local_block_is_committed

    first = await disconnect_google_connection(
        database_sessions,
        settings=settings,
        owner_session_token=SESSION_TOKEN,
        workspace=cast(GoogleWorkspaceClient, workspace),
    )
    stale_promotion = await finish_google_consent(
        database_sessions,
        settings=settings,
        attempt=pending_attempt,
        owner_session_token=SESSION_TOKEN,
        identity=GoogleIdentity(sub=OWNER_SUB, email="owner@example.test"),
        token_bundle=GoogleTokenBundle(
            access_token="stale-access-token",
            refresh_token="stale-refresh-token",
            access_expires_at=datetime.now(UTC) + timedelta(hours=1),
        ),
        granted_scopes=frozenset(CONNECTION_SCOPES),
    )
    second = await disconnect_google_connection(
        database_sessions,
        settings=settings,
        owner_session_token=SESSION_TOKEN,
        workspace=cast(GoogleWorkspaceClient, workspace),
    )
    async with database_sessions() as session:
        row = await session.scalar(select(GoogleConnectionRow))

    assert first.revoke_outcome.value == "unknown"
    assert stale_promotion is None
    assert first.reconnect_blocked is True
    assert second.reconnect_blocked is True
    assert workspace.revoke_calls == ["stored-refresh-token"]
    assert row is not None
    assert row.status == "disconnected"
    assert row.encrypted_token_bundle is None
    assert row.revoke_state == "unknown"
    with pytest.raises(GoogleConnectionFailure) as failure:
        await start_attempt(database_sessions)
    assert failure.value.code == "revocation_pending"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "revoke_error", [asyncio.CancelledError, TimeoutError], ids=["cancelled", "timeout"]
)
async def test_timeout_or_cancellation_during_revoke_keeps_local_credentials_purged(
    database_sessions: async_sessionmaker[AsyncSession],
    revoke_error: type[BaseException],
) -> None:
    await seed_owner_session(database_sessions)
    connection_id = await complete_consent(database_sessions)
    workspace = FakeWorkspace()

    async def cancel_provider_revoke() -> None:
        raise revoke_error()

    workspace.before_revoke = cancel_provider_revoke
    with pytest.raises(revoke_error):
        await disconnect_google_connection(
            database_sessions,
            settings=make_settings(),
            owner_session_token=SESSION_TOKEN,
            workspace=cast(GoogleWorkspaceClient, workspace),
        )

    async with database_sessions() as session:
        row = await session.get(GoogleConnectionRow, connection_id)
        account = await session.get(ProviderAccountRow, connection_id)

    assert row is not None
    assert row.status == GoogleConnectionStatus.DISCONNECTED.value
    assert row.encrypted_token_bundle is None
    assert row.revoke_state == "in_progress"
    assert account is not None
    assert account.provider == "google"
    assert account.external_account_id == OWNER_SUB
    with pytest.raises(GoogleConnectionFailure) as failure:
        await start_attempt(database_sessions)
    assert failure.value.code == "revocation_pending"


@pytest.mark.asyncio
async def test_refresh_lease_allows_one_provider_call_for_concurrent_sessions(
    database_sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await seed_owner_session(database_sessions)
    await seed_owner_session(database_sessions, token="second-session-token")
    connection_id = await complete_consent(database_sessions)
    async with database_sessions() as session, session.begin():
        row = await session.scalar(
            select(GoogleConnectionRow).where(
                GoogleConnectionRow.provider_account_id == connection_id
            )
        )
        assert row is not None and row.encrypted_token_bundle is not None
        row.encrypted_token_bundle, row.encryption_key_version = encrypt_token_bundle(
            GoogleTokenBundle(
                access_token="stored-access-token",
                refresh_token="stored-refresh-token",
                access_expires_at=datetime.now(UTC) - timedelta(seconds=1),
            ),
            ENCRYPTION_KEY,
            connection_id=connection_id,
            owner_sub=OWNER_SUB,
        )
    workspace = FakeWorkspace()
    workspace.block_refresh = True
    settings = make_settings()
    follower_observed_lease = asyncio.Event()

    async def observe_follower_claim(
        session: AsyncSession,
        *,
        connection_id: UUID,
        generation: int,
        credential_version: int,
        lease_owner: UUID,
        lease_duration: timedelta,
    ) -> bool:
        claimed = await claim_refresh_lease(
            session,
            connection_id=connection_id,
            generation=generation,
            credential_version=credential_version,
            lease_owner=lease_owner,
            lease_duration=lease_duration,
        )
        if not claimed:
            follower_observed_lease.set()
        return claimed

    monkeypatch.setattr(
        "email_support.services.google_connection.claim_refresh_lease",
        observe_follower_claim,
    )

    first = asyncio.create_task(
        read_gmail_metadata(
            database_sessions,
            settings=settings,
            workspace=cast(GoogleWorkspaceClient, workspace),
        )
    )
    await asyncio.wait_for(workspace.refresh_started.wait(), timeout=2)
    second = asyncio.create_task(
        read_gmail_metadata(
            database_sessions,
            settings=settings,
            workspace=cast(GoogleWorkspaceClient, workspace),
        )
    )
    await asyncio.wait_for(follower_observed_lease.wait(), timeout=2)
    workspace.refresh_release.set()
    assert tuple(await asyncio.gather(first, second)) == (None, None)

    assert workspace.refresh_calls == 1
    assert workspace.read_started.is_set()
    async with database_sessions() as session:
        row = await session.scalar(select(GoogleConnectionRow))
    assert row is not None
    assert row.credential_version == 2
    assert row.refresh_lease_owner is None
    assert row.refresh_lease_expires_at is None


@pytest.mark.asyncio
async def test_expired_refresh_lease_allows_a_new_holder_and_rejects_stale_save(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    await seed_owner_session(database_sessions)
    connection_id = await complete_consent(database_sessions)
    first_holder = uuid4()
    second_holder = uuid4()
    async with database_sessions() as session, session.begin():
        row = await session.get(GoogleConnectionRow, connection_id)
        assert row is not None
        generation = row.generation
        credential_version = row.credential_version
        assert await claim_refresh_lease(
            session,
            connection_id=connection_id,
            generation=generation,
            credential_version=credential_version,
            lease_owner=first_holder,
            lease_duration=timedelta(minutes=1),
        )
        row.refresh_lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)

    async with database_sessions() as session, session.begin():
        assert await claim_refresh_lease(
            session,
            connection_id=connection_id,
            generation=generation,
            credential_version=credential_version,
            lease_owner=second_holder,
            lease_duration=timedelta(minutes=1),
        )

    encrypted, key_version = encrypt_token_bundle(
        GoogleTokenBundle(
            access_token="refreshed-access-token",
            refresh_token="stored-refresh-token",
            access_expires_at=datetime.now(UTC) + timedelta(hours=1),
        ),
        ENCRYPTION_KEY,
        connection_id=connection_id,
        owner_sub=OWNER_SUB,
    )
    async with database_sessions() as session, session.begin():
        stale_saved = await save_refreshed_bundle(
            session,
            connection_id=connection_id,
            generation=generation,
            credential_version=credential_version,
            lease_owner=first_holder,
            encrypted_bundle=encrypted,
            key_version=key_version,
        )
        current_saved = await save_refreshed_bundle(
            session,
            connection_id=connection_id,
            generation=generation,
            credential_version=credential_version,
            lease_owner=second_holder,
            encrypted_bundle=encrypted,
            key_version=key_version,
        )

    assert stale_saved is False
    assert current_saved is True


@pytest.mark.asyncio
async def test_invalid_refresh_purges_grant_and_advances_generation(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    await seed_owner_session(database_sessions)
    connection_id = await complete_consent(database_sessions)
    async with database_sessions() as session, session.begin():
        row = await session.get(GoogleConnectionRow, connection_id)
        assert row is not None and row.encrypted_token_bundle is not None
        row.encrypted_token_bundle, row.encryption_key_version = encrypt_token_bundle(
            GoogleTokenBundle(
                access_token="expired-access-token",
                refresh_token="stored-refresh-token",
                access_expires_at=datetime.now(UTC) - timedelta(seconds=1),
            ),
            ENCRYPTION_KEY,
            connection_id=connection_id,
            owner_sub=OWNER_SUB,
        )
    workspace = FakeWorkspace()
    workspace.refresh_failure = GoogleConnectionErrorCode.REFRESH_INVALID

    with pytest.raises(GoogleConnectionFailure) as failure:
        await read_gmail_metadata(
            database_sessions,
            settings=make_settings(),
            workspace=cast(GoogleWorkspaceClient, workspace),
        )

    async with database_sessions() as session:
        row = await session.get(GoogleConnectionRow, connection_id)

    assert failure.value.code == "refresh_invalid"
    assert row is not None
    assert row.status == GoogleConnectionStatus.RECONNECT_REQUIRED.value
    assert row.encrypted_token_bundle is None
    assert row.generation == 2


@pytest.mark.asyncio
async def test_stale_invalid_grant_cannot_purge_a_newer_consent(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    await seed_owner_session(database_sessions)
    connection_id = await complete_consent(database_sessions)
    async with database_sessions() as session, session.begin():
        row = await session.get(GoogleConnectionRow, connection_id)
        assert row is not None and row.encrypted_token_bundle is not None
        row.encrypted_token_bundle, row.encryption_key_version = encrypt_token_bundle(
            GoogleTokenBundle(
                access_token="expired-access-token",
                refresh_token="stored-refresh-token",
                access_expires_at=datetime.now(UTC) - timedelta(seconds=1),
            ),
            ENCRYPTION_KEY,
            connection_id=connection_id,
            owner_sub=OWNER_SUB,
        )
    workspace = FakeWorkspace()
    workspace.block_refresh = True
    workspace.refresh_failure = GoogleConnectionErrorCode.REFRESH_INVALID
    settings = make_settings()
    pending_read = asyncio.create_task(
        read_gmail_metadata(
            database_sessions,
            settings=settings,
            workspace=cast(GoogleWorkspaceClient, workspace),
        )
    )
    await asyncio.wait_for(workspace.refresh_started.wait(), timeout=2)

    authorization = await start_attempt(database_sessions)
    attempt = await consume_google_consent_attempt(
        database_sessions,
        settings=settings,
        state=authorization.state,
        browser_cookie=BROWSER_COOKIE,
        owner_session_token=SESSION_TOKEN,
    )
    assert attempt is not None
    new_status = await finish_google_consent(
        database_sessions,
        settings=settings,
        attempt=attempt,
        owner_session_token=SESSION_TOKEN,
        identity=GoogleIdentity(sub=OWNER_SUB, email="owner@example.test"),
        token_bundle=GoogleTokenBundle(
            access_token="new-access-token",
            refresh_token="new-refresh-token",
            access_expires_at=datetime.now(UTC) + timedelta(hours=1),
        ),
        granted_scopes=frozenset(CONNECTION_SCOPES),
    )
    workspace.refresh_release.set()
    read_result = await asyncio.wait_for(pending_read, timeout=2)

    async with database_sessions() as session:
        row = await session.get(GoogleConnectionRow, connection_id)
    assert new_status is GoogleConnectionStatus.CONNECTED
    assert read_result is None
    assert workspace.refresh_calls == 1
    assert row is not None and row.encrypted_token_bundle is not None
    assert row.status == GoogleConnectionStatus.CONNECTED.value
    bundle = decrypt_token_bundle(
        row.encrypted_token_bundle,
        ENCRYPTION_KEY,
        connection_id=connection_id,
        owner_sub=OWNER_SUB,
    )
    assert bundle.refresh_token == "new-refresh-token"


@pytest.mark.asyncio
async def test_transient_refresh_error_preserves_credentials_and_releases_lease(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    await seed_owner_session(database_sessions)
    connection_id = await complete_consent(database_sessions)
    async with database_sessions() as session, session.begin():
        row = await session.get(GoogleConnectionRow, connection_id)
        assert row is not None and row.encrypted_token_bundle is not None
        row.encrypted_token_bundle, row.encryption_key_version = encrypt_token_bundle(
            GoogleTokenBundle(
                access_token="expired-access-token",
                refresh_token="stored-refresh-token",
                access_expires_at=datetime.now(UTC) - timedelta(seconds=1),
            ),
            ENCRYPTION_KEY,
            connection_id=connection_id,
            owner_sub=OWNER_SUB,
        )
    workspace = FakeWorkspace()
    workspace.refresh_failure = GoogleConnectionErrorCode.PROVIDER_UNAVAILABLE

    with pytest.raises(GoogleConnectionFailure) as failure:
        await read_gmail_metadata(
            database_sessions,
            settings=make_settings(),
            workspace=cast(GoogleWorkspaceClient, workspace),
        )

    async with database_sessions() as session:
        row = await session.get(GoogleConnectionRow, connection_id)

    assert failure.value.code == "provider_unavailable"
    assert row is not None
    assert row.status == GoogleConnectionStatus.CONNECTED.value
    assert row.encrypted_token_bundle is not None
    assert row.refresh_lease_owner is None
    assert row.refresh_lease_expires_at is None


@pytest.mark.asyncio
async def test_disconnect_during_refresh_discards_the_stale_provider_result(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    await seed_owner_session(database_sessions)
    connection_id = await complete_consent(database_sessions)
    async with database_sessions() as session, session.begin():
        row = await session.get(GoogleConnectionRow, connection_id)
        assert row is not None and row.encrypted_token_bundle is not None
        row.encrypted_token_bundle, row.encryption_key_version = encrypt_token_bundle(
            GoogleTokenBundle(
                access_token="expired-access-token",
                refresh_token="stored-refresh-token",
                access_expires_at=datetime.now(UTC) - timedelta(seconds=1),
            ),
            ENCRYPTION_KEY,
            connection_id=connection_id,
            owner_sub=OWNER_SUB,
        )
    workspace = FakeWorkspace()
    workspace.block_refresh = True
    read = asyncio.create_task(
        read_gmail_metadata(
            database_sessions,
            settings=make_settings(),
            workspace=cast(GoogleWorkspaceClient, workspace),
        )
    )
    await asyncio.wait_for(workspace.refresh_started.wait(), timeout=2)

    disconnected = await disconnect_google_connection(
        database_sessions,
        settings=make_settings(),
        owner_session_token=SESSION_TOKEN,
        workspace=cast(GoogleWorkspaceClient, workspace),
    )
    workspace.refresh_release.set()
    with pytest.raises(GoogleConnectionFailure) as stale_result:
        await read

    async with database_sessions() as session:
        row = await session.get(GoogleConnectionRow, connection_id)

    assert disconnected.status is GoogleConnectionStatus.DISCONNECTED
    assert stale_result.value.code == "credentials_unavailable"
    assert workspace.revoke_calls == ["stored-refresh-token"]
    assert row is not None
    assert row.status == GoogleConnectionStatus.DISCONNECTED.value
    assert row.encrypted_token_bundle is None
    assert row.generation == 2


@pytest.mark.asyncio
async def test_disconnect_fences_in_flight_read_and_new_admissions(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    await seed_owner_session(database_sessions)
    await complete_consent(database_sessions)
    workspace = FakeWorkspace()
    workspace.block_read = True
    settings = make_settings()
    read = asyncio.create_task(
        read_gmail_metadata(
            database_sessions,
            settings=settings,
            workspace=cast(GoogleWorkspaceClient, workspace),
        )
    )
    await asyncio.wait_for(workspace.read_started.wait(), timeout=2)

    disconnected = await disconnect_google_connection(
        database_sessions,
        settings=settings,
        owner_session_token=SESSION_TOKEN,
        workspace=cast(GoogleWorkspaceClient, workspace),
    )
    workspace.read_release.set()
    with pytest.raises(GoogleConnectionFailure) as stale_result:
        await read
    with pytest.raises(GoogleConnectionFailure) as new_admission:
        await read_gmail_metadata(
            database_sessions,
            settings=settings,
            workspace=cast(GoogleWorkspaceClient, workspace),
        )

    assert disconnected.revoke_outcome.value == "confirmed"
    assert stale_result.value.code == "revocation_pending"
    assert new_admission.value.code == "credentials_unavailable"
    async with database_sessions() as session:
        row = await session.scalar(select(GoogleConnectionRow))
    assert row is not None
    assert row.status == "disconnected"
    assert row.encrypted_token_bundle is None
