"""Canonical ownership and immutable identity of briefing runs."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class BriefingRunRow(Base):
    __tablename__ = "briefing_runs"
    __table_args__ = (
        CheckConstraint(
            "input_hash ~ '^[0-9a-f]{64}$'", name="ck_briefing_runs_input_hash"
        ),
        CheckConstraint(
            "config_hash ~ '^[0-9a-f]{64}$'", name="ck_briefing_runs_config_hash"
        ),
        CheckConstraint(
            "identity_revision IS NULL OR identity_revision > 0",
            name="ck_briefing_runs_revision",
        ),
        CheckConstraint(
            "status IN ('interpreting', 'running', 'pending_review', 'stopped')",
            name="ck_briefing_runs_status",
        ),
        CheckConstraint(
            "(status = 'stopped') = (stop_reason IS NOT NULL)",
            name="ck_briefing_runs_stop_reason",
        ),
        CheckConstraint(
            "(briefing_id IS NULL) = (briefing_version_id IS NULL)",
            name="ck_briefing_runs_binding_pair",
        ),
        CheckConstraint(
            "status <> 'pending_review' OR briefing_version_id IS NOT NULL",
            name="ck_briefing_runs_pending_binding",
        ),
        CheckConstraint(
            "jsonb_typeof(dependencies) = 'array'", name="ck_briefing_runs_dependencies"
        ),
        CheckConstraint(
            "jsonb_typeof(attempts) = 'array'", name="ck_briefing_runs_attempts"
        ),
        CheckConstraint(
            "status NOT IN ('running', 'pending_review') OR "
            "(company_id IS NOT NULL AND contact_id IS NOT NULL "
            "AND identity_revision IS NOT NULL)",
            name="ck_briefing_runs_resolved_identity",
        ),
        ForeignKeyConstraint(
            ["briefing_id", "company_id"],
            ["briefings.id", "briefings.company_id"],
            name="fk_briefing_runs_briefing_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["briefing_id", "briefing_version_id"],
            ["briefing_versions.briefing_id", "briefing_versions.id"],
            name="fk_briefing_runs_version",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    input_id: Mapped[UUID] = mapped_column(
        ForeignKey("normalized_inputs.id", ondelete="RESTRICT"), nullable=False
    )
    company_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=True
    )
    contact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="RESTRICT"), nullable=True
    )
    identity_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    stop_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dependencies: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    attempts: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    briefing_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    briefing_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
