import pytest
from pydantic import ValidationError

from email_support.models.health import HealthResponse


@pytest.mark.parametrize("payload", [{}, {"status": "degraded"}])
def test_health_response_rejects_missing_or_unknown_status(payload: object) -> None:
    with pytest.raises(ValidationError):
        HealthResponse.model_validate(payload)
