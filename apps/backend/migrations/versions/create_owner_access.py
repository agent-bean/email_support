"""Add owner login attempts and opaque sessions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b17e9a4d2c61"
down_revision: str | None = "da3c8e14f627"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oauth_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=24), nullable=False),
        sa.Column("state_digest", sa.LargeBinary(length=32), nullable=True),
        sa.Column("csrf_digest", sa.LargeBinary(length=32), nullable=True),
        sa.Column("browser_digest", sa.LargeBinary(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("nonce", sa.String(length=128), nullable=True),
        sa.Column("code_verifier", sa.String(length=128), nullable=True),
        sa.Column("return_target", sa.String(length=8), nullable=False),
        sa.CheckConstraint(
            "(purpose = 'login_bootstrap' AND state_digest IS NULL "
            "AND csrf_digest IS NOT NULL AND nonce IS NULL "
            "AND code_verifier IS NULL) OR "
            "(purpose = 'login' AND state_digest IS NOT NULL "
            "AND csrf_digest IS NULL AND nonce IS NOT NULL "
            "AND code_verifier IS NOT NULL)",
            name="ck_oauth_attempt_protocol_fields",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("csrf_digest"),
        sa.UniqueConstraint("state_digest"),
    )
    op.create_index("ix_oauth_attempts_expires_at", "oauth_attempts", ["expires_at"])
    op.create_table(
        "owner_sessions",
        sa.Column("token_digest", sa.LargeBinary(length=32), nullable=False),
        sa.Column("owner_sub", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("csrf_secret", sa.String(length=128), nullable=False),
        sa.CheckConstraint(
            "length(owner_sub) > 0", name="ck_owner_session_sub_nonblank"
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_owner_session_expiry"),
        sa.PrimaryKeyConstraint("token_digest"),
    )
    op.create_index("ix_owner_sessions_expires_at", "owner_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_owner_sessions_expires_at", table_name="owner_sessions")
    op.drop_table("owner_sessions")
    op.drop_index("ix_oauth_attempts_expires_at", table_name="oauth_attempts")
    op.drop_table("oauth_attempts")
