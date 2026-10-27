"""Conditional PostgreSQL operations for login attempts and owner sessions."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from email_support.storage.postgres.persistence.tables.auth import (
    OAuthAttemptRow,
    OwnerSessionRow,
)


async def create_attempt(
    session: AsyncSession,
    *,
    purpose: str,
    state_digest: bytes | None,
    csrf_digest: bytes | None,
    browser_digest: bytes,
    expires_at: datetime,
    nonce: str | None = None,
    code_verifier: str | None = None,
) -> UUID:
    attempt_id = uuid4()
    session.add(
        OAuthAttemptRow(
            id=attempt_id,
            purpose=purpose,
            state_digest=state_digest,
            csrf_digest=csrf_digest,
            browser_digest=browser_digest,
            expires_at=expires_at,
            nonce=nonce,
            code_verifier=code_verifier,
            return_target="/",
        )
    )
    return attempt_id


async def consume_attempt(
    session: AsyncSession,
    *,
    purpose: str,
    browser_digest: bytes,
    state_digest: bytes | None = None,
    csrf_digest: bytes | None = None,
) -> OAuthAttemptRow | None:
    conditions = [
        OAuthAttemptRow.purpose == purpose,
        OAuthAttemptRow.browser_digest == browser_digest,
        OAuthAttemptRow.expires_at > datetime.now(UTC),
    ]
    if state_digest is not None:
        conditions.append(OAuthAttemptRow.state_digest == state_digest)
    if csrf_digest is not None:
        conditions.append(OAuthAttemptRow.csrf_digest == csrf_digest)
    result = await session.execute(
        delete(OAuthAttemptRow).where(*conditions).returning(OAuthAttemptRow)
    )
    return result.scalar_one_or_none()


async def remove_expired_attempts(session: AsyncSession) -> None:
    await session.execute(
        delete(OAuthAttemptRow)
        .where(OAuthAttemptRow.expires_at <= datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )


async def create_owner_session(
    session: AsyncSession,
    *,
    token_digest: bytes,
    owner_sub: str,
    created_at: datetime,
    expires_at: datetime,
    csrf_secret: str,
) -> None:
    session.add(
        OwnerSessionRow(
            token_digest=token_digest,
            owner_sub=owner_sub,
            created_at=created_at,
            expires_at=expires_at,
            csrf_secret=csrf_secret,
        )
    )


async def get_owner_session(
    session: AsyncSession, token_digest: bytes, *, lock: bool = False
) -> OwnerSessionRow | None:
    query = select(OwnerSessionRow).where(
        OwnerSessionRow.token_digest == token_digest,
        OwnerSessionRow.expires_at > datetime.now(UTC),
    )
    if lock:
        query = query.with_for_update()
    return await session.scalar(query)


async def delete_owner_session(session: AsyncSession, token_digest: bytes) -> bool:
    result = await session.execute(
        delete(OwnerSessionRow)
        .where(OwnerSessionRow.token_digest == token_digest)
        .returning(OwnerSessionRow.token_digest)
    )
    return result.scalar_one_or_none() is not None


async def remove_expired_sessions(session: AsyncSession, limit: int = 100) -> None:
    expired = (
        select(OwnerSessionRow.token_digest)
        .where(OwnerSessionRow.expires_at <= datetime.now(UTC))
        .limit(limit)
    )
    await session.execute(
        delete(OwnerSessionRow)
        .where(OwnerSessionRow.token_digest.in_(expired))
        .execution_options(synchronize_session=False)
    )
