"""Real PostgreSQL tests for one-use auth attempts and opaque sessions."""

import asyncio
import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from email_support.integrations.google_oidc import GoogleIdentity
from email_support.services.auth import issue_owner_session
from email_support.storage.postgres.persistence.auth import (
    consume_attempt,
    create_attempt,
    create_owner_session,
    delete_owner_session,
    get_owner_session,
)
from email_support.storage.postgres.persistence.tables.auth import (
    OwnerSessionRow,
)


def digest(value: str) -> bytes:
    return hashlib.sha256(value.encode()).digest()


@pytest.mark.asyncio
async def test_attempt_claim_is_one_use_and_bound_to_browser(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    state = secrets.token_urlsafe(32)
    async with database_sessions() as session, session.begin():
        await create_attempt(
            session,
            purpose="login",
            state_digest=digest(state),
            csrf_digest=None,
            browser_digest=digest("browser-a"),
            expires_at=now + timedelta(minutes=5),
            nonce="nonce",
            code_verifier="verifier",
        )

    async def consume(browser: str) -> bool:
        async with database_sessions() as session, session.begin():
            row = await consume_attempt(
                session,
                purpose="login",
                browser_digest=digest(browser),
                state_digest=digest(state),
            )
            return row is not None

    wrong_browser = await consume("browser-b")
    first, second = await asyncio.gather(consume("browser-a"), consume("browser-a"))

    assert wrong_browser is False
    assert sorted([first, second]) == [False, True]


@pytest.mark.asyncio
async def test_expired_attempt_cannot_be_consumed(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    state = secrets.token_urlsafe(32)
    async with database_sessions() as session, session.begin():
        await create_attempt(
            session,
            purpose="login",
            state_digest=digest(state),
            csrf_digest=None,
            browser_digest=digest("browser"),
            expires_at=now - timedelta(seconds=1),
            nonce="nonce",
            code_verifier="verifier",
        )

    async with database_sessions() as session, session.begin():
        result = await consume_attempt(
            session,
            purpose="login",
            browser_digest=digest("browser"),
            state_digest=digest(state),
        )

    assert result is None


@pytest.mark.asyncio
async def test_login_attempt_requires_all_protocol_fields(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(IntegrityError):
        async with database_sessions() as session, session.begin():
            await create_attempt(
                session,
                purpose="login",
                state_digest=None,
                csrf_digest=None,
                browser_digest=digest("browser"),
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
                nonce="nonce",
                code_verifier="verifier",
            )


@pytest.mark.asyncio
async def test_session_stores_only_digest_and_logout_invalidates_it(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    raw_token = secrets.token_urlsafe(32)
    token_digest = digest(raw_token)
    now = datetime.now(UTC)
    async with database_sessions() as session, session.begin():
        await create_owner_session(
            session,
            token_digest=token_digest,
            owner_sub="owner-subject",
            created_at=now,
            expires_at=now + timedelta(hours=12),
            csrf_secret=secrets.token_urlsafe(32),
        )
    async with database_sessions() as session:
        row = await get_owner_session(session, token_digest)
        stored = await session.scalar(select(OwnerSessionRow.token_digest))
        stored_raw = await session.scalar(select(OwnerSessionRow.owner_sub))
    assert row is not None
    assert row.owner_sub == "owner-subject"
    assert stored == token_digest
    assert stored != raw_token.encode()
    assert stored_raw == "owner-subject"

    async with database_sessions() as session, session.begin():
        removed = await delete_owner_session(session, token_digest)
    async with database_sessions() as session:
        invalidated = await get_owner_session(session, token_digest)

    assert removed is True
    assert invalidated is None


@pytest.mark.asyncio
async def test_expired_and_isolated_sessions_are_enforced(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    active_token = secrets.token_urlsafe(32)
    expired_token = secrets.token_urlsafe(32)
    async with database_sessions() as session, session.begin():
        await create_owner_session(
            session,
            token_digest=digest(active_token),
            owner_sub="owner-a",
            created_at=now,
            expires_at=now + timedelta(hours=1),
            csrf_secret=secrets.token_urlsafe(32),
        )
        await create_owner_session(
            session,
            token_digest=digest(expired_token),
            owner_sub="owner-b",
            created_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),
            csrf_secret=secrets.token_urlsafe(32),
        )

    async with database_sessions() as session:
        active = await get_owner_session(session, digest(active_token))
        expired = await get_owner_session(session, digest(expired_token))

    assert active is not None and active.owner_sub == "owner-a"
    assert expired is None


@pytest.mark.asyncio
async def test_owner_login_rotates_the_presented_session(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    old_token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    async with database_sessions() as session, session.begin():
        await create_owner_session(
            session,
            token_digest=digest(old_token),
            owner_sub="owner-subject",
            created_at=now,
            expires_at=now + timedelta(hours=12),
            csrf_secret=secrets.token_urlsafe(32),
        )

    credentials = await issue_owner_session(
        database_sessions,
        identity=GoogleIdentity(sub="owner-subject", email=None),
        owner_sub="owner-subject",
        old_token=old_token,
    )
    async with database_sessions() as session:
        old_session = await get_owner_session(session, digest(old_token))
        new_session = await get_owner_session(session, digest(credentials.raw_token))

    assert old_session is None
    assert new_session is not None
    assert new_session.owner_sub == "owner-subject"
    assert credentials.expires_at > now


@pytest.mark.asyncio
async def test_logout_delete_waits_for_locked_session_row(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    raw_token = secrets.token_urlsafe(32)
    token_digest = digest(raw_token)
    now = datetime.now(UTC)
    async with database_sessions() as session, session.begin():
        await create_owner_session(
            session,
            token_digest=token_digest,
            owner_sub="owner-subject",
            created_at=now,
            expires_at=now + timedelta(hours=1),
            csrf_secret=secrets.token_urlsafe(32),
        )

    lock_session = database_sessions()
    lock_transaction = await lock_session.begin()
    locked = await get_owner_session(lock_session, token_digest, lock=True)
    assert locked is not None
    lock_backend_pid = await lock_session.scalar(text("SELECT pg_backend_pid()"))
    assert lock_backend_pid is not None
    delete_backend_pid: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    async def delete_session() -> bool:
        async with database_sessions() as session, session.begin():
            backend_pid = await session.scalar(text("SELECT pg_backend_pid()"))
            assert backend_pid is not None
            delete_backend_pid.set_result(backend_pid)
            return await delete_owner_session(session, token_digest)

    deletion = asyncio.create_task(delete_session())
    try:
        backend_pid = await asyncio.wait_for(delete_backend_pid, timeout=1)
        async with database_sessions() as monitor:
            deadline = asyncio.get_running_loop().time() + 1
            waiting_for_lock = False
            while asyncio.get_running_loop().time() < deadline:
                waiting_for_lock = bool(
                    await monitor.scalar(
                        text(
                            "SELECT :lock_backend_pid = ANY("
                            "pg_blocking_pids(:backend_pid))"
                        ),
                        {
                            "lock_backend_pid": lock_backend_pid,
                            "backend_pid": backend_pid,
                        },
                    )
                )
                if waiting_for_lock:
                    break
                await asyncio.sleep(0.01)
        assert waiting_for_lock
    finally:
        await lock_transaction.rollback()
        await lock_session.close()

    assert await asyncio.wait_for(deletion, timeout=2) is True
