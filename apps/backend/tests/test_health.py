from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from email_support.main import app
from email_support.models.health import HealthResponse, HealthStatus


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def test_health_endpoint_returns_typed_ok(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert HealthResponse.model_validate(response.json()).status is HealthStatus.OK


@pytest.mark.parametrize("payload", [{}, {"status": "degraded"}])
def test_health_response_rejects_missing_or_unknown_status(payload: object) -> None:
    with pytest.raises(ValidationError):
        HealthResponse.model_validate(payload)
