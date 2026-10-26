"""Opt-in live verification for the local owner Google connection."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from email_support.config import AuthSettings, load_auth_settings
from email_support.integrations.google_workspace import (
    GoogleWorkspaceClient,
    TokenProbeOutcome,
)
from email_support.models.google_connection import GoogleConnectionFailure
from email_support.services.google_connection import (
    prepare_live_google_smoke,
    read_gmail_metadata,
)
from email_support.services.google_connection_crypto import validate_encryption_key
from email_support.storage.postgres.persistence.database import (
    create_database_engine,
    create_session_factory,
    dispose_database_engine,
)
from email_support.storage.postgres.persistence.tables.google_connection import (
    GoogleConnectionRow,
)

MAX_REMOTE_OBSERVATION_SECONDS = 120.0
POLL_INTERVAL_SECONDS = 5.0
EXPIRY_MARGIN_SECONDS = 30.0
MINIMUM_TOKEN_LIFETIME_SECONDS = 160.0


async def poll_for_remote_rejection(
    probe: Callable[[], Awaitable[TokenProbeOutcome]],
    *,
    expires_at: datetime,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    timeout_seconds: float = MAX_REMOTE_OBSERVATION_SECONDS,
    interval_seconds: float = POLL_INTERVAL_SECONDS,
) -> bool:
    """Return true only for credential rejection observed before expiry margin."""
    if expires_at.tzinfo is None or timeout_seconds <= 0 or interval_seconds <= 0:
        return False
    cutoff = expires_at - timedelta(seconds=EXPIRY_MARGIN_SECONDS)
    deadline = monotonic() + min(timeout_seconds, MAX_REMOTE_OBSERVATION_SECONDS)
    while monotonic() < deadline and now().astimezone(UTC) < cutoff:
        remaining = min(
            deadline - monotonic(),
            (cutoff - now().astimezone(UTC)).total_seconds(),
        )
        if remaining <= 0:
            return False
        try:
            result = await asyncio.wait_for(probe(), timeout=remaining)
        except TimeoutError:
            return False
        if monotonic() >= deadline or now().astimezone(UTC) >= cutoff:
            return False
        if result is TokenProbeOutcome.REJECTED:
            return True
        if result is TokenProbeOutcome.INCONCLUSIVE:
            return False
        remaining_time = deadline - monotonic()
        remaining_lifetime = (cutoff - now().astimezone(UTC)).total_seconds()
        delay = min(interval_seconds, remaining_time, remaining_lifetime)
        if delay <= 0:
            return False
        await sleep(delay)
    return False


async def _verify_local_disconnect(
    sessions: async_sessionmaker[AsyncSession],
    *,
    settings: AuthSettings,
    owner_sub: str,
    previous_generation: int,
    workspace: GoogleWorkspaceClient,
) -> bool:
    async with sessions() as session:
        row = await session.scalar(
            select(GoogleConnectionRow).where(
                GoogleConnectionRow.owner_sub == owner_sub
            )
        )
        if (
            row is None
            or row.status != "disconnected"
            or row.encrypted_token_bundle is not None
            or row.generation <= previous_generation
        ):
            return False
    try:
        await read_gmail_metadata(
            sessions,
            settings=settings,
            workspace=workspace,
        )
    except GoogleConnectionFailure:
        return True
    return False


async def run_smoke() -> int:
    try:
        settings = load_auth_settings()
        if settings is None:
            print("PENDING: local owner authentication is not configured.")
            return 2
        validate_encryption_key(settings.google_token_encryption_key)
    except (ValueError, GoogleConnectionFailure):
        print("PENDING: configure the local owner runtime and token encryption key.")
        return 2

    engine = create_database_engine(settings.database_url)
    sessions = create_session_factory(engine)
    workspace = GoogleWorkspaceClient()
    try:
        try:
            snapshot = await prepare_live_google_smoke(
                sessions,
                settings=settings,
                workspace=workspace,
            )
        except GoogleConnectionFailure as failure:
            print(f"PENDING: Google connection is not ready ({failure.code.value}).")
            return 2
        if not (
            snapshot.gmail_read_succeeded
            and snapshot.secondary_calendar_found
            and snapshot.calendar_read_succeeded
        ):
            print("PENDING: an accessible secondary or shared calendar is required.")
            return 2
        remaining = (snapshot.access_expires_at - datetime.now(UTC)).total_seconds()
        if remaining <= MINIMUM_TOKEN_LIFETIME_SECONDS:
            print("PENDING: a fresh Google access token is required before disconnect.")
            return 2

        print("PASS: minimal Gmail metadata and secondary Calendar reads succeeded.")
        print(f"Access token expiry deadline: {snapshot.access_expires_at.isoformat()}")
        await asyncio.to_thread(
            input,
            "Disconnect Google in the authenticated browser, then press Enter here. ",
        )
        disconnect_started = time.monotonic()

        if not await _verify_local_disconnect(
            sessions,
            settings=settings,
            owner_sub=settings.owner_sub,
            previous_generation=snapshot.generation,
            workspace=workspace,
        ):
            print("FAIL: local disconnect did not purge credentials and block reads.")
            return 1
        print("PASS: local credentials were purged and new provider reads are blocked.")

        observation_budget = max(
            0.0,
            MAX_REMOTE_OBSERVATION_SECONDS - (time.monotonic() - disconnect_started),
        )
        remote_workspace = GoogleWorkspaceClient()
        remote_rejected = await poll_for_remote_rejection(
            lambda: remote_workspace.probe_gmail_access_token(snapshot.access_token),
            expires_at=snapshot.access_expires_at,
            timeout_seconds=observation_budget,
        )
        if remote_rejected:
            print("PASS: Google rejected the pre-disconnect access token.")
            return 0
        print("PENDING: remote revocation was not confirmed before the safe cutoff.")
        return 2
    except Exception:
        print("PENDING: local Google smoke could not complete.")
        return 2
    finally:
        await dispose_database_engine(engine)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_smoke()))
