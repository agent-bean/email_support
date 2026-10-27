"""Add encrypted Google connection state and generation-bound consent."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "3c0f6a9b21e8"
down_revision: str | None = "b17e9a4d2c61"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "google_connections",
        sa.Column("provider_account_id", sa.Uuid(), nullable=False),
        sa.Column("owner_sub", sa.Text(), nullable=False),
        sa.Column(
            "granted_scopes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("encrypted_token_bundle", sa.LargeBinary(), nullable=True),
        sa.Column("encryption_key_version", sa.String(length=32), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="disconnected",
            nullable=False,
        ),
        sa.Column("generation", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "credential_version", sa.BigInteger(), server_default="0", nullable=False
        ),
        sa.Column("refresh_lease_owner", sa.Uuid(), nullable=True),
        sa.Column(
            "refresh_lease_expires_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("revoke_operation_id", sa.Uuid(), nullable=True),
        sa.Column("revoke_state", sa.String(length=16), nullable=True),
        sa.Column("revoke_outcome", sa.String(length=16), nullable=True),
        sa.Column("revoke_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=32), nullable=True),
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
            "length(regexp_replace(owner_sub, '[[:space:]]', '', 'g')) > 0",
            name="ck_google_connection_owner_nonblank",
        ),
        sa.CheckConstraint(
            "status IN ('connected', 'reconnect_required', 'disconnected')",
            name="ck_google_connection_status",
        ),
        sa.CheckConstraint(
            "generation >= 0 AND credential_version >= 0",
            name="ck_google_connection_versions_nonnegative",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(granted_scopes) = 'array'",
            name="ck_google_connection_scopes_array",
        ),
        sa.CheckConstraint(
            "(encrypted_token_bundle IS NULL) = (encryption_key_version IS NULL)",
            name="ck_google_connection_ciphertext_key_version",
        ),
        sa.CheckConstraint(
            "status != 'connected' OR encrypted_token_bundle IS NOT NULL",
            name="ck_google_connection_connected_encrypted",
        ),
        sa.CheckConstraint(
            "(refresh_lease_owner IS NULL) = (refresh_lease_expires_at IS NULL)",
            name="ck_google_connection_refresh_lease_pair",
        ),
        sa.CheckConstraint(
            "revoke_state IS NULL OR "
            "revoke_state IN ('in_progress', 'unknown', 'resolved')",
            name="ck_google_connection_revoke_state",
        ),
        sa.CheckConstraint(
            "(revoke_state IS NULL AND revoke_operation_id IS NULL "
            "AND revoke_outcome IS NULL) OR "
            "(revoke_state = 'in_progress' AND revoke_operation_id IS NOT NULL "
            "AND revoke_outcome = 'unknown') OR "
            "(revoke_state = 'unknown' AND revoke_operation_id IS NOT NULL "
            "AND revoke_outcome = 'unknown') OR "
            "(revoke_state = 'resolved' AND revoke_operation_id IS NOT NULL "
            "AND revoke_outcome = 'confirmed') OR "
            "(revoke_state = 'resolved' AND revoke_operation_id IS NULL "
            "AND revoke_outcome = 'not_attempted')",
            name="ck_google_connection_revoke_record",
        ),
        sa.CheckConstraint(
            "revoke_state NOT IN ('in_progress', 'unknown') OR "
            "(status = 'disconnected' AND encrypted_token_bundle IS NULL)",
            name="ck_google_connection_unresolved_revoke_disabled",
        ),
        sa.CheckConstraint(
            "last_error IS NULL OR last_error IN "
            "('partial_scope', 'consent_denied', 'identity_mismatch', "
            "'session_expired', 'invalid_callback', 'refresh_invalid', "
            "'provider_unavailable', 'refresh_busy', "
            "'credentials_unavailable', 'revocation_pending')",
            name="ck_google_connection_safe_error",
        ),
        sa.ForeignKeyConstraint(
            ["provider_account_id"],
            ["provider_accounts.id"],
            name="fk_google_connections_provider_account",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("provider_account_id"),
        sa.UniqueConstraint("owner_sub", name="uq_google_connections_owner_sub"),
    )
    op.create_index(
        "ix_google_connections_refresh_lease",
        "google_connections",
        ["refresh_lease_expires_at"],
    )

    op.drop_constraint(
        "ck_oauth_attempt_protocol_fields", "oauth_attempts", type_="check"
    )
    op.add_column(
        "oauth_attempts", sa.Column("connection_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "oauth_attempts",
        sa.Column("session_digest", sa.LargeBinary(length=32), nullable=True),
    )
    op.add_column(
        "oauth_attempts", sa.Column("generation", sa.BigInteger(), nullable=True)
    )
    op.create_foreign_key(
        "fk_oauth_attempts_google_connection",
        "oauth_attempts",
        "google_connections",
        ["connection_id"],
        ["provider_account_id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_oauth_attempt_protocol_fields",
        "oauth_attempts",
        "(purpose = 'login_bootstrap' AND state_digest IS NULL "
        "AND csrf_digest IS NOT NULL AND nonce IS NULL AND code_verifier IS NULL "
        "AND connection_id IS NULL AND session_digest IS NULL "
        "AND generation IS NULL) OR "
        "(purpose = 'login' AND state_digest IS NOT NULL "
        "AND csrf_digest IS NULL AND nonce IS NOT NULL AND code_verifier IS NOT NULL "
        "AND connection_id IS NULL AND session_digest IS NULL "
        "AND generation IS NULL) OR "
        "(purpose = 'google_consent' AND state_digest IS NOT NULL "
        "AND csrf_digest IS NULL AND nonce IS NOT NULL AND code_verifier IS NOT NULL "
        "AND connection_id IS NOT NULL AND session_digest IS NOT NULL "
        "AND generation >= 0)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_oauth_attempt_protocol_fields", "oauth_attempts", type_="check"
    )
    op.drop_constraint(
        "fk_oauth_attempts_google_connection", "oauth_attempts", type_="foreignkey"
    )
    op.drop_column("oauth_attempts", "generation")
    op.drop_column("oauth_attempts", "session_digest")
    op.drop_column("oauth_attempts", "connection_id")
    op.create_check_constraint(
        "ck_oauth_attempt_protocol_fields",
        "oauth_attempts",
        "(purpose = 'login_bootstrap' AND state_digest IS NULL "
        "AND csrf_digest IS NOT NULL AND nonce IS NULL AND code_verifier IS NULL) OR "
        "(purpose = 'login' AND state_digest IS NOT NULL "
        "AND csrf_digest IS NULL AND nonce IS NOT NULL AND code_verifier IS NOT NULL)",
    )
    op.drop_index(
        "ix_google_connections_refresh_lease", table_name="google_connections"
    )
    op.drop_table("google_connections")
