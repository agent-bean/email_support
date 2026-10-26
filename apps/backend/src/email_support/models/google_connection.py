"""Google connection contracts and in-memory credential values."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

if TYPE_CHECKING:
    from email_support.integrations.google_oidc import GoogleIdentity


class GoogleConnectionStatus(StrEnum):
    CONNECTED = "connected"
    RECONNECT_REQUIRED = "reconnect_required"
    DISCONNECTED = "disconnected"


class GoogleConnectionErrorCode(StrEnum):
    PARTIAL_SCOPE = "partial_scope"
    CONSENT_DENIED = "consent_denied"
    IDENTITY_MISMATCH = "identity_mismatch"
    SESSION_EXPIRED = "session_expired"
    INVALID_CALLBACK = "invalid_callback"
    REFRESH_INVALID = "refresh_invalid"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    REFRESH_BUSY = "refresh_busy"
    CREDENTIALS_UNAVAILABLE = "credentials_unavailable"
    REVOCATION_PENDING = "revocation_pending"


class RevokeOutcome(StrEnum):
    CONFIRMED = "confirmed"
    UNKNOWN = "unknown"
    NOT_ATTEMPTED = "not_attempted"


class GoogleConnectionFailure(RuntimeError):
    """Sanitized typed failure suitable for mapping at the API boundary."""

    def __init__(self, code: GoogleConnectionErrorCode | str) -> None:
        self.code = GoogleConnectionErrorCode(code)
        super().__init__(self.code.value)


@dataclass(frozen=True, slots=True)
class GoogleTokenBundle:
    access_token: str = field(repr=False)
    refresh_token: str | None = field(repr=False)
    access_expires_at: datetime

    def __repr__(self) -> str:
        return (
            "GoogleTokenBundle(access_token=..., refresh_token=..., "
            "access_expires_at=...)"
        )


@dataclass(frozen=True, slots=True)
class GoogleConnectionGrant:
    identity: GoogleIdentity = field(repr=False)
    token_bundle: GoogleTokenBundle = field(repr=False)
    granted_scopes: frozenset[str]

    def __repr__(self) -> str:
        return "GoogleConnectionGrant(identity=..., token_bundle=...)"


@dataclass(frozen=True, slots=True)
class ScopeDecision:
    status: GoogleConnectionStatus
    missing_scopes: tuple[str, ...]
    unexpected_scopes: tuple[str, ...]


class GoogleConnectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: GoogleConnectionStatus
    granted_scopes: list[str] = Field(default_factory=list)
    missing_scopes: list[str] = Field(default_factory=list)
    unexpected_scopes: list[str] = Field(default_factory=list)
    error: GoogleConnectionErrorCode | None = None
    revoke_outcome: RevokeOutcome | None = None
    revoke_recorded_at: datetime | None = None
    reconnect_blocked: bool = False


class GoogleConsentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authorization_url: HttpUrl


class GoogleDisconnectResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: GoogleConnectionStatus
    revoke_outcome: RevokeOutcome
    revoke_recorded_at: datetime | None = None
    reconnect_blocked: bool


class GoogleConnectionErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: GoogleConnectionErrorCode
    message: str
