"""Canonical run creation, eligibility and idempotent briefing binding."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from email_support.models.persistence import BriefingCreate, BriefingVersionCreate
from email_support.models.persistence.briefing_runs import (
    BriefingRunCreate,
    KnowledgeDependency,
)
from email_support.models.research import ProviderUsage
from email_support.storage.postgres.persistence.core import (
    PersistenceConflict,
    PersistenceNotFound,
    create_briefing,
    create_briefing_version,
)
from email_support.storage.postgres.persistence.tables import (
    ApprovalRow,
    BriefingRunRow,
    BriefingVersionRow,
    ContactRow,
    KnowledgeRow,
    NormalizedInputRow,
)


def row_identity_missing(run: BriefingRunRow) -> bool:
    return (
        run.contact_id is None
        or run.company_id is None
        or run.identity_revision is None
    )


async def _current_dependencies(session: AsyncSession, run: BriefingRunRow) -> None:
    if row_identity_missing(run):
        raise PersistenceConflict("run identity is unresolved")
    contact = await session.scalar(
        select(ContactRow).where(ContactRow.id == run.contact_id).with_for_update()
    )
    if (
        contact is None
        or contact.company_id != run.company_id
        or contact.identity_revision != run.identity_revision
    ):
        raise PersistenceConflict("contact identity is stale")
    source = await session.get(NormalizedInputRow, run.input_id)
    if source is None or source.content_hash != run.input_hash:
        raise PersistenceConflict("normalized input is stale")
    dependencies = [
        KnowledgeDependency.model_validate(item) for item in run.dependencies
    ]
    for dependency in sorted(dependencies, key=lambda value: str(value.knowledge_id)):
        row = await session.scalar(
            select(KnowledgeRow)
            .where(KnowledgeRow.id == dependency.knowledge_id)
            .with_for_update()
        )
        if (
            row is None
            or row.company_id != run.company_id
            or not row.sealed
            or row.invalidated_at is not None
            or row.briefing_version_id != dependency.briefing_version_id
            or row.approval_id != dependency.approval_id
        ):
            raise PersistenceConflict("knowledge dependency is stale")
        approval = await session.get(ApprovalRow, row.approval_id)
        version = await session.get(BriefingVersionRow, row.briefing_version_id)
        if (
            approval is None
            or approval.briefing_version_id != row.briefing_version_id
            or version is None
            or not version.sealed
        ):
            raise PersistenceConflict("knowledge approval is invalid")


async def current_run(session: AsyncSession, run_id: UUID) -> BriefingRunRow:
    """Lock and validate canonical state before consuming cached context."""
    row = await session.scalar(
        select(BriefingRunRow).where(BriefingRunRow.id == run_id).with_for_update()
    )
    if row is None:
        raise PersistenceNotFound("run not found")
    await _current_dependencies(session, row)
    return row


async def stop_run(session: AsyncSession, run_id: UUID, reason: str) -> None:
    if reason not in {
        "irrelevant",
        "uncertain",
        "unresolved",
        "ambiguous",
        "public_research_company_mismatch",
    }:
        raise ValueError("invalid stop reason")
    row = await session.scalar(
        select(BriefingRunRow).where(BriefingRunRow.id == run_id).with_for_update()
    )
    if row is None:
        raise PersistenceNotFound("run not found")
    if row.status != "interpreting":
        raise PersistenceConflict("run cannot be stopped")
    row.status = "stopped"
    row.stop_reason = reason
    row.updated_at = datetime.now(UTC)
    await session.flush()


async def begin_run(
    session: AsyncSession,
    run_id: UUID,
    input_id: UUID,
    input_hash: str,
    config_hash: str,
) -> BriefingRunRow:
    source = await session.get(NormalizedInputRow, input_id)
    if source is None or source.content_hash != input_hash:
        raise PersistenceConflict("normalized input is stale")
    await session.execute(
        insert(BriefingRunRow)
        .values(
            id=run_id,
            input_id=input_id,
            input_hash=input_hash,
            config_hash=config_hash,
            status="interpreting",
            dependencies=[],
            attempts=[],
        )
        .on_conflict_do_nothing(index_elements=[BriefingRunRow.id])
    )
    row = await session.scalar(
        select(BriefingRunRow).where(BriefingRunRow.id == run_id).with_for_update()
    )
    if row is None:
        raise PersistenceNotFound("run not found")
    if (
        row.input_id != input_id
        or row.input_hash != input_hash
        or row.config_hash != config_hash
    ):
        raise PersistenceConflict("run identity differs from stored request")
    return row


async def resolve_run(
    session: AsyncSession, value: BriefingRunCreate
) -> BriefingRunRow:
    row = await session.scalar(
        select(BriefingRunRow).where(BriefingRunRow.id == value.id).with_for_update()
    )
    if row is None:
        raise PersistenceNotFound("run not found")
    if row.status != "interpreting":
        raise PersistenceConflict("run is not awaiting interpretation")
    if (
        row.input_id != value.input_id
        or row.input_hash != value.input_hash
        or row.config_hash != value.config_hash
    ):
        raise PersistenceConflict("run identity differs from stored request")
    row.company_id = value.company_id
    row.contact_id = value.contact_id
    row.identity_revision = value.identity_revision
    row.dependencies = [item.model_dump(mode="json") for item in value.dependencies]
    row.status = "running"
    await _current_dependencies(session, row)
    await session.flush()
    return row


async def create_run(session: AsyncSession, value: BriefingRunCreate) -> BriefingRunRow:
    data = value.model_dump(mode="json")
    dependencies = data["dependencies"]
    statement = (
        insert(BriefingRunRow)
        .values(
            id=value.id,
            input_id=value.input_id,
            company_id=value.company_id,
            contact_id=value.contact_id,
            identity_revision=value.identity_revision,
            input_hash=value.input_hash,
            config_hash=value.config_hash,
            status="running",
            dependencies=dependencies,
            attempts=[],
        )
        .on_conflict_do_nothing(index_elements=[BriefingRunRow.id])
    )
    await session.execute(statement)
    row = await session.scalar(
        select(BriefingRunRow).where(BriefingRunRow.id == value.id).with_for_update()
    )
    if row is None:
        raise PersistenceNotFound("run not found")
    existing = BriefingRunCreate.model_validate(
        {
            "id": row.id,
            "input_id": row.input_id,
            "company_id": row.company_id,
            "contact_id": row.contact_id,
            "identity_revision": row.identity_revision,
            "input_hash": row.input_hash,
            "config_hash": row.config_hash,
            "dependencies": row.dependencies,
        }
    )
    if existing != value:
        raise PersistenceConflict("run identity differs from stored request")
    await _current_dependencies(session, row)
    return row


async def bind_briefing(
    session: AsyncSession, run_id: UUID, markdown: str, evidence_ids: list[UUID]
) -> BriefingRunRow:
    row = await session.scalar(
        select(BriefingRunRow).where(BriefingRunRow.id == run_id).with_for_update()
    )
    if row is None:
        raise PersistenceNotFound("run not found")
    await _current_dependencies(session, row)
    if row.briefing_version_id is not None:
        return row
    if row.status != "running":
        raise PersistenceConflict("run cannot be bound")
    briefing = await create_briefing(session, BriefingCreate(company_id=row.company_id))
    version = await create_briefing_version(
        session,
        BriefingVersionCreate(
            briefing_id=briefing.id, markdown=markdown, evidence_ids=evidence_ids
        ),
    )
    row.briefing_id, row.briefing_version_id = briefing.id, version.id
    row.status = "pending_review"
    row.updated_at = datetime.now(UTC)
    await session.flush()
    return row


async def reserve_attempt(
    session: AsyncSession, run_id: UUID, attempt_id: UUID, limit: int, category: str
) -> None:
    if limit < 1 or not category or len(category) > 64:
        raise ValueError("invalid attempt limit or category")
    row = await session.scalar(
        select(BriefingRunRow).where(BriefingRunRow.id == run_id).with_for_update()
    )
    if row is None:
        raise PersistenceNotFound("run not found")
    if row.status not in {"interpreting", "running"} or len(row.attempts) >= limit:
        raise PersistenceConflict("run attempt budget exhausted or run not active")
    if any(item.get("id") == str(attempt_id) for item in row.attempts):
        raise PersistenceConflict("attempt already reserved")
    row.attempts = [
        *row.attempts,
        {
            "id": str(attempt_id),
            "category": category,
            "outcome": "unknown",
            "usage": None,
        },
    ]
    row.updated_at = datetime.now(UTC)
    await session.flush()


async def complete_attempt(
    session: AsyncSession,
    run_id: UUID,
    attempt_id: UUID,
    outcome: str,
    usage: ProviderUsage | None,
) -> None:
    if outcome not in {"succeeded", "failed"}:
        raise ValueError("invalid attempt outcome")
    row = await session.scalar(
        select(BriefingRunRow).where(BriefingRunRow.id == run_id).with_for_update()
    )
    if row is None:
        raise PersistenceNotFound("run not found")
    attempts = [dict(item) for item in row.attempts]
    for item in attempts:
        if item.get("id") == str(attempt_id):
            if item.get("outcome") != "unknown":
                raise PersistenceConflict("attempt already completed")
            item["outcome"] = outcome
            item["usage"] = usage.model_dump(mode="json") if usage else None
            row.attempts = attempts
            row.updated_at = datetime.now(UTC)
            await session.flush()
            return
    raise PersistenceNotFound("attempt not found")
