"""Owner login and opaque session invariants."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from email_support.config import AuthSettings
from email_support.integrations.google_oidc import (
    GoogleAuthorization,
    GoogleIdentity,
    create_authorization,
)
from email_support.storage.postgres.persistence.auth import (
    consume_attempt,
    create_attempt,
    create_owner_session,
    delete_owner_session,
    get_owner_session,
    remove_expired_attempts,
    remove_expired_sessions,
)
from email_support.storage.postgres.persistence.tables.auth import OAuthAttemptRow

ATTEMPT_TTL = timedelta(minutes=10)
SESSION_TTL = timedelta(hours=12)


def require_owner_subject(identity: GoogleIdentity, owner_sub: str) -> None:
    if not hmac.compare_digest(identity.sub, owner_sub):
        raise PermissionError("Google identity is not the configured owner")


def digest(secret: str) -> bytes:
    return hashlib.sha256(secret.encode("utf-8")).digest()


@dataclass(frozen=True, slots=True)
class SessionCredentials:
    raw_token: str
    csrf_token: str
    expires_at: datetime


async def create_preauth(
    sessions: async_sessionmaker[AsyncSession], browser_cookie: str | None
) -> tuple[str, str]:
    browser_secret = secrets.token_urlsafe(32)
    csrf_secret = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    async with sessions() as session, session.begin():
        if browser_cookie:
            await session.execute(
                delete(OAuthAttemptRow).where(
                    OAuthAttemptRow.browser_digest == digest(browser_cookie)
                )
            )
        await remove_expired_attempts(session)
        await create_attempt(
            session,
            purpose="login_bootstrap",
            state_digest=None,
            csrf_digest=digest(csrf_secret),
            browser_digest=digest(browser_secret),
            expires_at=now + ATTEMPT_TTL,
        )
    return browser_secret, csrf_secret


async def begin_login(
    settings: AuthSettings,
    sessions: async_sessionmaker[AsyncSession],
    *,
    browser_cookie: str,
    csrf_secret: str,
) -> GoogleAuthorization | None:
    authorization = create_authorization(
        settings.google_client_id,
        settings.google_client_secret,
        settings.callback_uri,
    )
    now = datetime.now(UTC)
    async with sessions() as session, session.begin():
        bootstrap = await consume_attempt(
            session,
            purpose="login_bootstrap",
            browser_digest=digest(browser_cookie),
            csrf_digest=digest(csrf_secret),
        )
        if bootstrap is None:
            return None
        await create_attempt(
            session,
            purpose="login",
            state_digest=digest(authorization.state),
            csrf_digest=None,
            browser_digest=digest(browser_cookie),
            expires_at=now + ATTEMPT_TTL,
            nonce=authorization.nonce,
            code_verifier=authorization.code_verifier,
        )
    return authorization


async def consume_login_callback(
    sessions: async_sessionmaker[AsyncSession], *, browser_cookie: str, state: str
) -> OAuthAttemptRow | None:
    async with sessions() as session, session.begin():
        return await consume_attempt(
            session,
            purpose="login",
            browser_digest=digest(browser_cookie),
            state_digest=digest(state),
        )


async def issue_owner_session(
    sessions: async_sessionmaker[AsyncSession],
    *,
    identity: GoogleIdentity,
    owner_sub: str,
    old_token: str | None,
) -> SessionCredentials:
    require_owner_subject(identity, owner_sub)
    raw_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    expires_at = now + SESSION_TTL
    async with sessions() as session, session.begin():
        await remove_expired_sessions(session)
        if old_token:
            await delete_owner_session(session, digest(old_token))
        await create_owner_session(
            session,
            token_digest=digest(raw_token),
            owner_sub=owner_sub,
            created_at=now,
            expires_at=expires_at,
            csrf_secret=csrf_token,
        )
    return SessionCredentials(raw_token, csrf_token, expires_at)


async def get_valid_session(
    sessions: async_sessionmaker[AsyncSession], raw_token: str | None
) -> tuple[str, datetime, str] | None:
    if not raw_token:
        return None
    async with sessions() as session:
        row = await get_owner_session(session, digest(raw_token))
        if row is None:
            return None
        return row.owner_sub, row.expires_at, row.csrf_secret


async def logout_session(
    sessions: async_sessionmaker[AsyncSession], raw_token: str
) -> None:
    async with sessions() as session, session.begin():
        await delete_owner_session(session, digest(raw_token))
