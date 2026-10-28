"""Add immutable normalized input provenance and versioned contact identity."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e7a21c4f9b30"
down_revision: str | None = "3c0f6a9b21e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "contacts",
        sa.Column(
            "identity_revision",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_contacts_identity_revision", "contacts", "identity_revision > 0"
    )
    op.create_table(
        "normalized_inputs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("origin_kind", sa.String(length=24), nullable=False),
        sa.Column("origin_key", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "provider_source", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "origin_kind IN ('local_import', 'evaluation', 'provider')",
            name="ck_normalized_inputs_origin_kind",
        ),
        sa.CheckConstraint(
            "length(regexp_replace(origin_key, '[[:space:]]', '', 'g')) > 0",
            name="ck_normalized_inputs_origin_key_nonblank",
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_normalized_inputs_hash_sha256",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object'",
            name="ck_normalized_inputs_payload_object",
        ),
        sa.CheckConstraint(
            "(origin_kind = 'provider' AND provider_source IS NOT NULL) OR "
            "(origin_kind != 'provider' AND provider_source IS NULL)",
            name="ck_normalized_inputs_provider_source",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_normalized_inputs"),
        sa.UniqueConstraint(
            "origin_kind", "origin_key", name="uq_normalized_inputs_origin"
        ),
    )
    op.add_column(
        "evidence", sa.Column("normalized_input_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_evidence_normalized_input_id",
        "evidence",
        "normalized_inputs",
        ["normalized_input_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint("ck_evidence_source_matches_kind", "evidence", type_="check")
    op.create_check_constraint(
        "ck_evidence_source_matches_kind",
        "evidence",
        "(kind = 'mail' AND mail_message_id IS NOT NULL AND meeting_id IS NULL "
        "AND source_url IS NULL AND normalized_input_id IS NULL) OR "
        "(kind = 'meeting' AND mail_message_id IS NULL AND meeting_id IS NOT NULL "
        "AND source_url IS NULL AND normalized_input_id IS NULL) OR "
        "(kind = 'web' AND mail_message_id IS NULL AND meeting_id IS NULL "
        "AND source_url IS NOT NULL AND normalized_input_id IS NULL) OR "
        "(kind = 'normalized_input' AND mail_message_id IS NULL "
        "AND meeting_id IS NULL AND source_url IS NULL "
        "AND normalized_input_id IS NOT NULL)",
    )


def downgrade() -> None:
    connection = op.get_bind()
    has_new_records = connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM normalized_inputs) OR "
            "EXISTS (SELECT 1 FROM evidence WHERE normalized_input_id IS NOT NULL) OR "
            "EXISTS (SELECT 1 FROM contacts WHERE identity_revision != 1)"
        )
    )
    if has_new_records:
        raise RuntimeError(
            "identity data exists; restore a verified backup instead of downgrading"
        )
    op.drop_constraint("ck_evidence_source_matches_kind", "evidence", type_="check")
    op.create_check_constraint(
        "ck_evidence_source_matches_kind",
        "evidence",
        "(kind = 'mail' AND mail_message_id IS NOT NULL AND meeting_id IS NULL "
        "AND source_url IS NULL) OR "
        "(kind = 'meeting' AND mail_message_id IS NULL AND meeting_id IS NOT NULL "
        "AND source_url IS NULL) OR "
        "(kind = 'web' AND mail_message_id IS NULL AND meeting_id IS NULL "
        "AND source_url IS NOT NULL)",
    )
    op.drop_constraint(
        "fk_evidence_normalized_input_id", "evidence", type_="foreignkey"
    )
    op.drop_column("evidence", "normalized_input_id")
    op.drop_table("normalized_inputs")
    op.drop_constraint("ck_contacts_identity_revision", "contacts", type_="check")
    op.drop_column("contacts", "identity_revision")
