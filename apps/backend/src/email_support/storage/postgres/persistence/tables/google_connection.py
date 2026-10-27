"""Encrypted Google connection state and cross-process fencing metadata."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
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


class GoogleConnectionRow(Base):
    __tablename__ = "google_connections"
    __table_args__ = (
        CheckConstraint(
            "length(regexp_replace(owner_sub, '[[:space:]]', '', 'g')) > 0",
            name="ck_google_connection_owner_nonblank",
        ),
        CheckConstraint(
            "status IN ('connected', 'reconnect_required', 'disconnected')",
            name="ck_google_connection_status",
        ),
        CheckConstraint(
            "generation >= 0 AND credential_version >= 0",
            name="ck_google_connection_versions_nonnegative",
        ),
        CheckConstraint(
            "jsonb_typeof(granted_scopes) = 'array'",
            name="ck_google_connection_scopes_array",
        ),
        CheckConstraint(
            "(encrypted_token_bundle IS NULL) = (encryption_key_version IS NULL)",
            name="ck_google_connection_ciphertext_key_version",
        ),
        CheckConstraint(
            "status != 'connected' OR encrypted_token_bundle IS NOT NULL",
            name="ck_google_connection_connected_encrypted",
        ),
        CheckConstraint(
            "(refresh_lease_owner IS NULL) = (refresh_lease_expires_at IS NULL)",
            name="ck_google_connection_refresh_lease_pair",
        ),
        CheckConstraint(
            "revoke_state IS NULL OR "
            "revoke_state IN ('in_progress', 'unknown', 'resolved')",
            name="ck_google_connection_revoke_state",
        ),
        CheckConstraint(
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
        CheckConstraint(
            "revoke_state NOT IN ('in_progress', 'unknown') OR "
            "(status = 'disconnected' AND encrypted_token_bundle IS NULL)",
            name="ck_google_connection_unresolved_revoke_disabled",
        ),
        CheckConstraint(
            "last_error IS NULL OR last_error IN "
            "('partial_scope', 'consent_denied', 'identity_mismatch', "
            "'session_expired', 'invalid_callback', 'refresh_invalid', "
            "'provider_unavailable', 'refresh_busy', "
            "'credentials_unavailable', 'revocation_pending')",
            name="ck_google_connection_safe_error",
        ),
        UniqueConstraint("owner_sub", name="uq_google_connections_owner_sub"),
        Index("ix_google_connections_refresh_lease", "refresh_lease_expires_at"),
    )

    provider_account_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "provider_accounts.id",
            name="fk_google_connections_provider_account",
            ondelete="RESTRICT",
        ),
        primary_key=True,
    )
    owner_sub: Mapped[str] = mapped_column(Text, nullable=False)
    granted_scopes: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    encrypted_token_bundle: Mapped[bytes | None] = mapped_column(LargeBinary)
    encryption_key_version: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="disconnected"
    )
    generation: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    credential_version: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    refresh_lease_owner: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    refresh_lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    revoke_operation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    revoke_state: Mapped[str | None] = mapped_column(String(16))
    revoke_outcome: Mapped[str | None] = mapped_column(String(16))
    revoke_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
