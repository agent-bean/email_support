"""Caller-owned transactions for Google connections and refresh fencing."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from email_support.storage.postgres.persistence.tables.auth import (
    OAuthAttemptRow,
    OwnerSessionRow,
)
from email_support.storage.postgres.persistence.tables.core import ProviderAccountRow
from email_support.storage.postgres.persistence.tables.google_connection import (
    GoogleConnectionRow,
)


async def lock_live_owner_session(
    session: AsyncSession, session_digest: bytes, owner_sub: str
) -> OwnerSessionRow | None:
    return await session.scalar(
        select(OwnerSessionRow)
        .where(
            OwnerSessionRow.token_digest == session_digest,
            OwnerSessionRow.owner_sub == owner_sub,
            OwnerSessionRow.expires_at > func.now(),
        )
        .with_for_update()
    )


async def ensure_google_connection(
    session: AsyncSession, owner_sub: str
) -> GoogleConnectionRow:
    await session.execute(
        insert(ProviderAccountRow)
        .values(id=uuid4(), provider="google", external_account_id=owner_sub)
        .on_conflict_do_nothing(constraint="uq_provider_accounts_external")
    )
    provider_account_id = await session.scalar(
        select(ProviderAccountRow.id).where(
            ProviderAccountRow.provider == "google",
            ProviderAccountRow.external_account_id == owner_sub,
        )
    )
    if provider_account_id is None:
        raise RuntimeError("Google provider account could not be resolved")
    await session.execute(
        insert(GoogleConnectionRow)
        .values(provider_account_id=provider_account_id, owner_sub=owner_sub)
        .on_conflict_do_nothing(
            index_elements=[GoogleConnectionRow.provider_account_id]
        )
    )
    connection = await session.scalar(
        select(GoogleConnectionRow)
        .where(GoogleConnectionRow.provider_account_id == provider_account_id)
        .with_for_update()
    )
    if connection is None or connection.owner_sub != owner_sub:
        raise RuntimeError("Google connection identity could not be resolved")
    return connection


async def get_google_connection(
    session: AsyncSession, owner_sub: str, *, lock: bool = False
) -> GoogleConnectionRow | None:
    query = select(GoogleConnectionRow).where(
        GoogleConnectionRow.owner_sub == owner_sub
    )
    if lock:
        query = query.with_for_update()
    return await session.scalar(query)


async def create_google_consent_attempt(
    session: AsyncSession,
    *,
    state_digest: bytes,
    browser_digest: bytes,
    session_digest: bytes,
    expires_at: datetime,
    nonce: str,
    code_verifier: str,
    connection_id: UUID,
    generation: int,
) -> UUID:
    attempt_id = uuid4()
    session.add(
        OAuthAttemptRow(
            id=attempt_id,
            purpose="google_consent",
            state_digest=state_digest,
            csrf_digest=None,
            browser_digest=browser_digest,
            expires_at=expires_at,
            nonce=nonce,
            code_verifier=code_verifier,
            return_target="/",
            connection_id=connection_id,
            session_digest=session_digest,
            generation=generation,
        )
    )
    return attempt_id


async def get_google_consent_attempt(
    session: AsyncSession,
    *,
    state_digest: bytes,
    browser_digest: bytes,
    session_digest: bytes,
) -> OAuthAttemptRow | None:
    return await session.scalar(
        select(OAuthAttemptRow).where(
            OAuthAttemptRow.purpose == "google_consent",
            OAuthAttemptRow.state_digest == state_digest,
            OAuthAttemptRow.browser_digest == browser_digest,
            OAuthAttemptRow.session_digest == session_digest,
            OAuthAttemptRow.expires_at > func.now(),
        )
    )


async def delete_google_consent_attempt(
    session: AsyncSession, attempt_id: UUID
) -> None:
    await session.execute(
        delete(OAuthAttemptRow).where(
            OAuthAttemptRow.id == attempt_id,
            OAuthAttemptRow.purpose == "google_consent",
        )
    )


async def claim_refresh_lease(
    session: AsyncSession,
    *,
    connection_id: UUID,
    generation: int,
    credential_version: int,
    lease_owner: UUID,
    lease_duration: timedelta,
) -> bool:
    result = await session.execute(
        update(GoogleConnectionRow)
        .where(
            GoogleConnectionRow.provider_account_id == connection_id,
            GoogleConnectionRow.status == "connected",
            GoogleConnectionRow.generation == generation,
            GoogleConnectionRow.credential_version == credential_version,
            (
                GoogleConnectionRow.refresh_lease_owner.is_(None)
                | (GoogleConnectionRow.refresh_lease_expires_at <= func.now())
            ),
        )
        .values(
            refresh_lease_owner=lease_owner,
            refresh_lease_expires_at=func.now() + lease_duration,
            updated_at=func.now(),
        )
        .returning(GoogleConnectionRow.provider_account_id)
    )
    return result.scalar_one_or_none() is not None


async def save_refreshed_bundle(
    session: AsyncSession,
    *,
    connection_id: UUID,
    generation: int,
    credential_version: int,
    lease_owner: UUID,
    encrypted_bundle: bytes,
    key_version: str,
) -> bool:
    result = await session.execute(
        update(GoogleConnectionRow)
        .where(
            GoogleConnectionRow.provider_account_id == connection_id,
            GoogleConnectionRow.status == "connected",
            GoogleConnectionRow.generation == generation,
            GoogleConnectionRow.credential_version == credential_version,
            GoogleConnectionRow.refresh_lease_owner == lease_owner,
            GoogleConnectionRow.refresh_lease_expires_at > func.now(),
        )
        .values(
            encrypted_token_bundle=encrypted_bundle,
            encryption_key_version=key_version,
            credential_version=credential_version + 1,
            refresh_lease_owner=None,
            refresh_lease_expires_at=None,
            last_error=None,
            updated_at=func.now(),
        )
        .returning(GoogleConnectionRow.provider_account_id)
    )
    return result.scalar_one_or_none() is not None


async def release_refresh_lease(
    session: AsyncSession,
    *,
    connection_id: UUID,
    generation: int,
    credential_version: int,
    lease_owner: UUID,
) -> bool:
    result = await session.execute(
        update(GoogleConnectionRow)
        .where(
            GoogleConnectionRow.provider_account_id == connection_id,
            GoogleConnectionRow.generation == generation,
            GoogleConnectionRow.credential_version == credential_version,
            GoogleConnectionRow.refresh_lease_owner == lease_owner,
        )
        .values(
            refresh_lease_owner=None,
            refresh_lease_expires_at=None,
            updated_at=func.now(),
        )
        .returning(GoogleConnectionRow.provider_account_id)
    )
    return result.scalar_one_or_none() is not None


async def invalidate_refresh_grant(
    session: AsyncSession,
    *,
    connection_id: UUID,
    generation: int,
    credential_version: int,
    lease_owner: UUID,
) -> bool:
    result = await session.execute(
        update(GoogleConnectionRow)
        .where(
            GoogleConnectionRow.provider_account_id == connection_id,
            GoogleConnectionRow.status == "connected",
            GoogleConnectionRow.generation == generation,
            GoogleConnectionRow.credential_version == credential_version,
            GoogleConnectionRow.refresh_lease_owner == lease_owner,
        )
        .values(
            status="reconnect_required",
            encrypted_token_bundle=None,
            encryption_key_version=None,
            generation=generation + 1,
            credential_version=credential_version + 1,
            refresh_lease_owner=None,
            refresh_lease_expires_at=None,
            last_error="refresh_invalid",
            updated_at=func.now(),
        )
        .returning(GoogleConnectionRow.provider_account_id)
    )
    return result.scalar_one_or_none() is not None


async def is_connection_generation_current(
    session: AsyncSession,
    *,
    connection_id: UUID,
    generation: int,
) -> bool:
    row = await session.scalar(
        select(GoogleConnectionRow.provider_account_id).where(
            GoogleConnectionRow.provider_account_id == connection_id,
            GoogleConnectionRow.generation == generation,
            GoogleConnectionRow.status == "connected",
        )
    )
    return row is not None


def utc_now() -> datetime:
    return datetime.now(UTC)
