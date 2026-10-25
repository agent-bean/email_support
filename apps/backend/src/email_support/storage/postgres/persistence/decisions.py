"""Typed approval, knowledge and explicit preference operations."""

from datetime import UTC, datetime
from itertools import groupby
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from email_support.models.persistence import (
    ActionKind,
    ActionRecord,
    ApprovalCreate,
    ApprovalRecord,
    KnowledgeCreate,
    KnowledgeRecord,
    PreferenceCreate,
    PreferenceRecord,
)
from email_support.storage.postgres.persistence.core import (
    PersistenceConflict,
    PersistenceNotFound,
)
from email_support.storage.postgres.persistence.tables import (
    ActionRow,
    ApprovalRow,
    BriefingRow,
    KnowledgeEvidenceRow,
    KnowledgeRow,
    PreferenceRow,
)


async def _flush(session: AsyncSession) -> None:
    try:
        await session.flush()
    except DBAPIError as error:
        sqlstate = getattr(error.orig, "sqlstate", None)
        if sqlstate == "23505":
            raise PersistenceConflict(
                "canonical decision key already exists"
            ) from error
        if sqlstate == "P0001":
            raise PersistenceConflict(
                "canonical approval or knowledge invariant failed"
            ) from error
        raise


def _approval_record(row: ApprovalRow) -> ApprovalRecord:
    return ApprovalRecord.model_validate(
        {
            "id": row.id,
            "briefing_id": row.briefing_id,
            "briefing_version_id": row.briefing_version_id,
            "action_kind": row.action_kind,
            "recipient_emails": row.recipient_emails,
            "selected_knowledge": row.selected_knowledge,
            "approved_at": row.approved_at,
        }
    )


def _action_record(row: ActionRow) -> ActionRecord:
    return ActionRecord.model_validate(
        {"id": row.id, "approval_id": row.approval_id, "created_at": row.created_at}
    )


async def record_approval_and_action(
    session: AsyncSession, value: ApprovalCreate
) -> tuple[ApprovalRecord, ActionRecord]:
    approval = ApprovalRow(
        briefing_id=value.briefing_id,
        briefing_version_id=value.briefing_version_id,
        action_kind=value.action_kind.value,
        recipient_emails=value.recipient_emails,
        selected_knowledge=value.selected_knowledge,
    )
    session.add(approval)
    await _flush(session)

    action = ActionRow(approval_id=approval.id)
    session.add(action)
    await _flush(session)
    return _approval_record(approval), _action_record(action)


async def get_approval(session: AsyncSession, approval_id: UUID) -> ApprovalRecord:
    row = await session.get(ApprovalRow, approval_id)
    if row is None:
        raise PersistenceNotFound("approval not found")
    return _approval_record(row)


async def get_action(session: AsyncSession, approval_id: UUID) -> ActionRecord:
    row = await session.scalar(
        select(ActionRow).where(ActionRow.approval_id == approval_id)
    )
    if row is None:
        raise PersistenceNotFound("action not found")
    return _action_record(row)


async def _evidence_ids(session: AsyncSession, knowledge_id: UUID) -> list[UUID]:
    return list(
        await session.scalars(
            select(KnowledgeEvidenceRow.evidence_id)
            .where(KnowledgeEvidenceRow.knowledge_id == knowledge_id)
            .order_by(KnowledgeEvidenceRow.evidence_id)
        )
    )


def _knowledge_record(
    row: KnowledgeRow, approval: ApprovalRow, evidence_ids: list[UUID]
) -> KnowledgeRecord:
    if row.selection_index >= len(approval.selected_knowledge):
        raise RuntimeError("knowledge selection no longer matches its approval")
    return KnowledgeRecord.model_validate(
        {
            "id": row.id,
            "company_id": row.company_id,
            "approval_id": row.approval_id,
            "selection_index": row.selection_index,
            "briefing_version_id": row.briefing_version_id,
            "content": approval.selected_knowledge[row.selection_index],
            "created_at": row.created_at,
            "invalidated_at": row.invalidated_at,
            "evidence_ids": evidence_ids,
        }
    )


async def _knowledge_record_for(
    session: AsyncSession, row: KnowledgeRow
) -> KnowledgeRecord:
    approval = await session.get(ApprovalRow, row.approval_id)
    if approval is None:
        raise RuntimeError("knowledge approval is missing")
    return _knowledge_record(row, approval, await _evidence_ids(session, row.id))


async def create_knowledge(
    session: AsyncSession, value: KnowledgeCreate
) -> KnowledgeRecord:
    approval = await session.get(ApprovalRow, value.approval_id)
    if approval is None:
        raise PersistenceNotFound("knowledge approval not found")
    if approval.action_kind != ActionKind.SAVE_KNOWLEDGE.value:
        raise PersistenceConflict("knowledge requires a save-knowledge approval")
    if value.selection_index >= len(approval.selected_knowledge):
        raise PersistenceConflict("knowledge selection index is outside its approval")

    company_id = await session.scalar(
        select(BriefingRow.company_id).where(BriefingRow.id == approval.briefing_id)
    )
    row = KnowledgeRow(
        company_id=company_id,
        approval_id=approval.id,
        selection_index=value.selection_index,
        briefing_version_id=approval.briefing_version_id,
        sealed=False,
    )
    session.add(row)
    await _flush(session)

    session.add_all(
        KnowledgeEvidenceRow(knowledge_id=row.id, evidence_id=evidence_id)
        for evidence_id in value.evidence_ids
    )
    await _flush(session)

    row.sealed = True
    await _flush(session)
    return _knowledge_record(row, approval, await _evidence_ids(session, row.id))


async def get_knowledge(session: AsyncSession, knowledge_id: UUID) -> KnowledgeRecord:
    row = await session.get(KnowledgeRow, knowledge_id)
    if row is None or not row.sealed:
        raise PersistenceNotFound("sealed knowledge not found")
    return await _knowledge_record_for(session, row)


async def list_eligible_knowledge(
    session: AsyncSession, company_id: UUID | None = None
) -> list[KnowledgeRecord]:
    statement = (
        select(KnowledgeRow, ApprovalRow, KnowledgeEvidenceRow.evidence_id)
        .join(ApprovalRow, ApprovalRow.id == KnowledgeRow.approval_id)
        .outerjoin(
            KnowledgeEvidenceRow,
            KnowledgeEvidenceRow.knowledge_id == KnowledgeRow.id,
        )
        .where(KnowledgeRow.sealed.is_(True), KnowledgeRow.invalidated_at.is_(None))
        .order_by(
            KnowledgeRow.created_at,
            KnowledgeRow.id,
            KnowledgeEvidenceRow.evidence_id,
        )
    )
    if company_id is not None:
        statement = statement.where(KnowledgeRow.company_id == company_id)

    knowledge_rows = (await session.execute(statement)).all()
    records: list[KnowledgeRecord] = []
    for _knowledge_id, grouped_rows in groupby(
        knowledge_rows, key=lambda result: result[0].id
    ):
        group = list(grouped_rows)
        row, approval, _evidence_id = group[0]
        evidence_ids = [
            evidence_id
            for _row, _approval, evidence_id in group
            if evidence_id is not None
        ]
        records.append(_knowledge_record(row, approval, evidence_ids))
    return records


async def invalidate_knowledge(
    session: AsyncSession, knowledge_id: UUID
) -> KnowledgeRecord:
    row = await session.get(KnowledgeRow, knowledge_id)
    if row is None or not row.sealed:
        raise PersistenceNotFound("sealed knowledge not found")
    if row.invalidated_at is None:
        row.invalidated_at = datetime.now(UTC)
        await _flush(session)
    return await _knowledge_record_for(session, row)


def _preference_record(row: PreferenceRow) -> PreferenceRecord:
    return PreferenceRecord.model_validate(
        {
            "id": row.id,
            "key": row.key,
            "value": row.value,
            "updated_at": row.updated_at,
        }
    )


async def set_preference(
    session: AsyncSession, value: PreferenceCreate
) -> PreferenceRecord:
    statement = (
        insert(PreferenceRow)
        .values(key=value.key, value=value.value)
        .on_conflict_do_update(
            index_elements=[PreferenceRow.key],
            set_={"value": value.value, "updated_at": func.now()},
        )
        .returning(PreferenceRow)
    )
    row = await session.scalar(statement)
    if row is None:
        raise RuntimeError("preference upsert returned no row")
    return _preference_record(row)


async def get_preference(session: AsyncSession, key: str) -> PreferenceRecord:
    row = await session.scalar(select(PreferenceRow).where(PreferenceRow.key == key))
    if row is None:
        raise PersistenceNotFound("preference not found")
    return _preference_record(row)
