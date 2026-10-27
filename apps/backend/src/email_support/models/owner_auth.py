"""Typed owner authentication contracts and errors."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class OwnerAuthErrorCode(StrEnum):
    AUTH_UNAVAILABLE = "auth_unavailable"
    AUTH_REQUIRED = "auth_required"
    CSRF_REJECTED = "csrf_rejected"
    LOGIN_REJECTED = "login_rejected"
    LOGIN_RESTART = "login_restart"


class OwnerAuthError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: OwnerAuthErrorCode
    message: str


class PreauthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    csrf_token: str = Field(min_length=32)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    authorization_url: HttpUrl


class OwnerSession(BaseModel):
    model_config = ConfigDict(extra="forbid")
    authenticated: bool = True
    expires_at: datetime
    csrf_token: str = Field(min_length=32)
