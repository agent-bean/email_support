"""Validated health response contract."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class HealthStatus(StrEnum):
    """Closed health states returned by the API."""

    OK = "ok"


class HealthResponse(BaseModel):
    """Credential-free liveness response."""

    model_config = ConfigDict(extra="forbid")

    status: HealthStatus
