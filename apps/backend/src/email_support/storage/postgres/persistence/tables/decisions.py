"""SQLAlchemy mappings for approvals, actions and reusable owner data."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ApprovalRow(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["briefing_id", "briefing_version_id"],
            ["briefing_versions.briefing_id", "briefing_versions.id"],
            name="fk_approvals_briefing_version",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "briefing_version_id", name="uq_approvals_id_version"),
        CheckConstraint(
            "action_kind IN ('send_email', 'save_knowledge')",
            name="ck_approvals_action_kind",
        ),
        CheckConstraint(
            "jsonb_typeof(recipient_emails) = 'array'",
            name="ck_approvals_recipient_array",
        ),
        CheckConstraint(
            "jsonb_typeof(selected_knowledge) = 'array'",
            name="ck_approvals_knowledge_array",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    briefing_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    briefing_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    action_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    recipient_emails: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    selected_knowledge: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ActionRow(Base):
    __tablename__ = "actions"
    __table_args__ = (UniqueConstraint("approval_id", name="uq_actions_approval_id"),)

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    approval_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("approvals.id", name="fk_actions_approval_id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class KnowledgeRow(Base):
    __tablename__ = "knowledge"
    __table_args__ = (
        ForeignKeyConstraint(
            ["approval_id", "briefing_version_id"],
            ["approvals.id", "approvals.briefing_version_id"],
            name="fk_knowledge_approval_version",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "approval_id", "selection_index", name="uq_knowledge_approval_selection"
        ),
        UniqueConstraint(
            "id", "briefing_version_id", name="uq_knowledge_id_source_version"
        ),
        CheckConstraint(
            "selection_index >= 0", name="ck_knowledge_selection_index_nonnegative"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", name="fk_knowledge_company_id", ondelete="RESTRICT"),
        nullable=True,
    )
    approval_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    selection_index: Mapped[int] = mapped_column(Integer, nullable=False)
    briefing_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    sealed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    invalidated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class KnowledgeEvidenceRow(Base):
    __tablename__ = "knowledge_evidence"

    knowledge_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "knowledge.id",
            name="fk_knowledge_evidence_knowledge_id",
            ondelete="RESTRICT",
        ),
        primary_key=True,
    )
    evidence_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "evidence.id", name="fk_knowledge_evidence_evidence_id", ondelete="RESTRICT"
        ),
        primary_key=True,
    )


class PreferenceRow(Base):
    __tablename__ = "preferences"
    __table_args__ = (
        UniqueConstraint("key", name="uq_preferences_key"),
        CheckConstraint("length(btrim(key)) > 0", name="ck_preferences_key_nonblank"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    key: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[object] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
