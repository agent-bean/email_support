"""PostgreSQL mappings for normalized, provider-neutral inputs."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class NormalizedInputRow(Base):
    __tablename__ = "normalized_inputs"
    __table_args__ = (
        UniqueConstraint(
            "origin_kind", "origin_key", name="uq_normalized_inputs_origin"
        ),
        CheckConstraint(
            "origin_kind IN ('local_import', 'evaluation', 'provider')",
            name="ck_normalized_inputs_origin_kind",
        ),
        CheckConstraint(
            "length(regexp_replace(origin_key, '[[:space:]]', '', 'g')) > 0",
            name="ck_normalized_inputs_origin_key_nonblank",
        ),
        CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'",
            name="ck_normalized_inputs_hash_sha256",
        ),
        CheckConstraint(
            "jsonb_typeof(payload) = 'object'",
            name="ck_normalized_inputs_payload_object",
        ),
        CheckConstraint(
            "(origin_kind = 'provider' AND provider_source IS NOT NULL) OR "
            "(origin_kind != 'provider' AND provider_source IS NULL)",
            name="ck_normalized_inputs_provider_source",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )
    origin_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    origin_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    provider_source: Mapped[dict[str, object] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = ["NormalizedInputRow"]
