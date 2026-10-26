"""OAuth attempts and opaque owner sessions."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, LargeBinary, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class OAuthAttemptRow(Base):
    __tablename__ = "oauth_attempts"
    __table_args__ = (
        CheckConstraint(
            "(purpose = 'login_bootstrap' AND state_digest IS NULL "
            "AND csrf_digest IS NOT NULL AND nonce IS NULL "
            "AND code_verifier IS NULL) OR "
            "(purpose = 'login' AND state_digest IS NOT NULL "
            "AND csrf_digest IS NULL AND nonce IS NOT NULL "
            "AND code_verifier IS NOT NULL)",
            name="ck_oauth_attempt_protocol_fields",
        ),
        Index("ix_oauth_attempts_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    purpose: Mapped[str] = mapped_column(String(24), nullable=False)
    state_digest: Mapped[bytes | None] = mapped_column(LargeBinary(32), unique=True)
    csrf_digest: Mapped[bytes | None] = mapped_column(LargeBinary(32), unique=True)
    browser_digest: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    nonce: Mapped[str | None] = mapped_column(String(128))
    code_verifier: Mapped[str | None] = mapped_column(String(128))
    return_target: Mapped[str] = mapped_column(String(8), nullable=False)


class OwnerSessionRow(Base):
    __tablename__ = "owner_sessions"
    __table_args__ = (
        CheckConstraint("length(owner_sub) > 0", name="ck_owner_session_sub_nonblank"),
        CheckConstraint("expires_at > created_at", name="ck_owner_session_expiry"),
        Index("ix_owner_sessions_expires_at", "expires_at"),
    )

    token_digest: Mapped[bytes] = mapped_column(LargeBinary(32), primary_key=True)
    owner_sub: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    csrf_secret: Mapped[str] = mapped_column(String(128), nullable=False)
