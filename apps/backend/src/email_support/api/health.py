"""Health endpoint."""

from fastapi import APIRouter

from email_support.models.health import HealthResponse, HealthStatus

router = APIRouter(prefix="/api")


@router.get(
    "/health",
    response_model=HealthResponse,
    operation_id="get_health",
    tags=["health"],
)
def get_health() -> HealthResponse:
    """Return the API's liveness state."""
    return HealthResponse(status=HealthStatus.OK)
