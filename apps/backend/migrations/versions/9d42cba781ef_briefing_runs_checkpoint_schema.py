"""Add canonical briefing runs and an isolated checkpoint schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9d42cba781ef"
down_revision: str | None = "e7a21c4f9b30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_briefings_id_company", "briefings", ["id", "company_id"]
    )
    op.execute("CREATE SCHEMA briefing_checkpoints")
    op.create_table(
        "briefing_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "input_id",
            sa.Uuid(),
            sa.ForeignKey("normalized_inputs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "contact_id",
            sa.Uuid(),
            sa.ForeignKey("contacts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("identity_revision", sa.Integer(), nullable=True),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("config_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("stop_reason", sa.String(64), nullable=True),
        sa.Column("dependencies", postgresql.JSONB(), nullable=False),
        sa.Column("attempts", postgresql.JSONB(), nullable=False),
        sa.Column("briefing_id", sa.Uuid(), nullable=True),
        sa.Column("briefing_version_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "input_hash ~ '^[0-9a-f]{64}$'", name="ck_briefing_runs_input_hash"
        ),
        sa.CheckConstraint(
            "config_hash ~ '^[0-9a-f]{64}$'", name="ck_briefing_runs_config_hash"
        ),
        sa.CheckConstraint(
            "identity_revision IS NULL OR identity_revision > 0",
            name="ck_briefing_runs_revision",
        ),
        sa.CheckConstraint(
            "status IN ('interpreting', 'running', 'pending_review', 'stopped')",
            name="ck_briefing_runs_status",
        ),
        sa.CheckConstraint(
            "(status = 'stopped') = (stop_reason IS NOT NULL)",
            name="ck_briefing_runs_stop_reason",
        ),
        sa.CheckConstraint(
            "(briefing_id IS NULL) = (briefing_version_id IS NULL)",
            name="ck_briefing_runs_binding_pair",
        ),
        sa.CheckConstraint(
            "status <> 'pending_review' OR briefing_version_id IS NOT NULL",
            name="ck_briefing_runs_pending_binding",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(dependencies) = 'array'", name="ck_briefing_runs_dependencies"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(attempts) = 'array'", name="ck_briefing_runs_attempts"
        ),
        sa.CheckConstraint(
            "status NOT IN ('running', 'pending_review') OR "
            "(company_id IS NOT NULL AND contact_id IS NOT NULL "
            "AND identity_revision IS NOT NULL)",
            name="ck_briefing_runs_resolved_identity",
        ),
        sa.ForeignKeyConstraint(
            ["briefing_id", "company_id"],
            ["briefings.id", "briefings.company_id"],
            name="fk_briefing_runs_briefing_company",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["briefing_id", "briefing_version_id"],
            ["briefing_versions.briefing_id", "briefing_versions.id"],
            name="fk_briefing_runs_version",
            ondelete="RESTRICT",
        ),
    )


def downgrade() -> None:
    raise RuntimeError(
        "Briefing runs and checkpoint state must not be dropped by downgrade"
    )
