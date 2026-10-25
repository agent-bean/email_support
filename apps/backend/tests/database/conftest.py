"""Function-scoped real PostgreSQL targets with guarded backups and cleanup."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from pydantic import AnyHttpUrl, TypeAdapter
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from email_support.models.persistence import (
    BriefingCreate,
    BriefingVersionCreate,
    CompanyCreate,
    EvidenceCreate,
    EvidenceKind,
)
from email_support.storage.postgres.persistence.core import (
    create_briefing,
    create_briefing_version,
    create_company,
    create_evidence,
)
from email_support.storage.postgres.persistence.database import (
    create_database_engine,
    create_session_factory,
    dispose_database_engine,
)
from scripts.test_database import DatabaseLifecycle, run_migrations
from tests.database.support import CanonicalSource

HTTP_URL_ADAPTER: TypeAdapter[AnyHttpUrl] = TypeAdapter(AnyHttpUrl)


@pytest.fixture(scope="session")
def database_lifecycle() -> DatabaseLifecycle:
    return DatabaseLifecycle.from_environment()


@pytest.fixture
def database_url(
    database_lifecycle: DatabaseLifecycle, request: pytest.FixtureRequest
) -> Iterator[str]:
    database_name = database_lifecycle.create_target(request.node.nodeid)
    target_url = database_lifecycle.target_url(database_name)
    try:
        run_migrations(target_url)
        database_lifecycle.backup_database(database_name, "before-scenario-seed")
        yield target_url
    finally:
        database_lifecycle.drop_target(database_name)


@pytest_asyncio.fixture
async def database_engine(database_url: str) -> AsyncGenerator[AsyncEngine]:
    engine = create_database_engine(database_url)
    try:
        yield engine
    finally:
        await dispose_database_engine(engine)


@pytest.fixture
def database_sessions(
    database_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(database_engine)


@pytest_asyncio.fixture
async def canonical_source(
    database_sessions: async_sessionmaker[AsyncSession],
) -> CanonicalSource:
    async with database_sessions() as session, session.begin():
        company = await create_company(
            session, CompanyCreate(name="Example Company", domain="example.com")
        )
        evidence = await create_evidence(
            session,
            EvidenceCreate(
                kind=EvidenceKind.WEB,
                mail_message_id=None,
                meeting_id=None,
                source_url=HTTP_URL_ADAPTER.validate_python(
                    "https://example.com/source"
                ),
                source_text="Evidence for the approved briefing.",
                retrieved_at=datetime.now(UTC),
            ),
        )
        briefing = await create_briefing(session, BriefingCreate(company_id=company.id))
        version = await create_briefing_version(
            session,
            BriefingVersionCreate(
                briefing_id=briefing.id,
                markdown="# Approved briefing\n\nSource-backed summary.",
                evidence_ids=[evidence.id],
            ),
        )
    return CanonicalSource(
        company=company,
        evidence=evidence,
        briefing=briefing,
        version=version,
    )
