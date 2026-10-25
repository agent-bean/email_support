"""Shared types and validators for persistence contracts."""

from datetime import UTC, datetime
from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, StringConstraints

type NonBlankText = Annotated[
    str, StringConstraints(min_length=1, strip_whitespace=True)
]
type ExactText = str
type EmailAddress = Annotated[str, StringConstraints(min_length=3, max_length=320)]


class PersistenceContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include a UTC offset")
    return value.astimezone(UTC)


def _normalize_optional_utc(value: datetime | None) -> datetime | None:
    return None if value is None else _normalize_utc(value)


def _normalize_email_domain(value: str) -> str:
    try:
        validate_email(value, check_deliverability=False)
    except EmailNotValidError as error:
        raise ValueError("invalid email address") from error
    local, domain = value.rsplit("@", maxsplit=1)
    return f"{local}@{domain.lower()}"


def _normalize_optional_email_domain(value: str | None) -> str | None:
    return None if value is None else _normalize_email_domain(value)
