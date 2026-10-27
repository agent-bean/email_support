"""Private runtime settings for provider adapters and bounded research tools."""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlsplit

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
)


class ResearchConfigurationError(ValueError):
    """Safe configuration error that never includes credential values."""


class ResearchSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    gateway_base_url: AnyHttpUrl
    gateway_api_key: SecretStr
    gateway_model: str = Field(min_length=1, max_length=200)
    openrouter_api_key: SecretStr
    embedding_model: str = Field(min_length=1, max_length=200)
    tavily_api_key: SecretStr
    request_timeout_seconds: float = Field(default=12.0, gt=0, le=60)
    total_deadline_seconds: float = Field(default=30.0, gt=0, le=180)
    max_attempts: int = Field(default=2, ge=1, le=4)
    max_tool_calls: int = Field(default=8, ge=1, le=32)
    max_concurrency: int = Field(default=2, ge=1, le=8)
    max_search_results: int = Field(default=5, ge=1, le=5)
    max_fetch_bytes: int = Field(default=524_288, ge=1024, le=2_097_152)
    max_provider_response_bytes: int = Field(default=1_048_576, ge=1024, le=4_194_304)

    @field_validator("gateway_base_url")
    @classmethod
    def gateway_url_is_private_https(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        parsed = urlsplit(str(value))
        if parsed.scheme != "https" or parsed.username or parsed.password:
            raise ValueError("gateway URL must be HTTPS without embedded credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("gateway URL cannot include a query or fragment")
        return value

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> ResearchSettings:
        names = {
            "gateway_base_url": "RESEARCH_GATEWAY_URL",
            "gateway_api_key": "RESEARCH_GATEWAY_API_KEY",
            "gateway_model": "RESEARCH_GATEWAY_MODEL",
            "openrouter_api_key": "OPENROUTER_API_KEY",
            "embedding_model": "OPENROUTER_EMBEDDING_MODEL",
            "tavily_api_key": "TAVILY_API_KEY",
        }
        missing = [key for key, name in names.items() if not environment.get(name)]
        if missing:
            required_names = ", ".join(names[key] for key in missing)
            raise ResearchConfigurationError(
                f"Missing required research settings: {required_names}"
            )
        values = {key: environment[name] for key, name in names.items()}
        try:
            return cls.model_validate(values)
        except ValidationError as error:
            fields = ", ".join(
                str(item["loc"][0]) for item in error.errors(include_url=False)[:3]
            )
            raise ResearchConfigurationError(
                f"Invalid research settings: {fields or 'configuration'}"
            ) from error
