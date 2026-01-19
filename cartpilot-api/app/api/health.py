"""Health check endpoints.

Provides endpoints for monitoring service health and readiness.
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: str
    service: str
    version: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Check service health.

    Returns:
        Health status with service name and version.
    """
    from app.infrastructure.config import settings

    return HealthResponse(
        status="healthy",
        service="cartpilot-api",
        version=settings.api_version,
    )


@router.get("/ready")
async def readiness_check() -> dict[str, str]:
    """Check if service is ready to accept requests.

    Returns:
        Readiness status.
    """
    # TODO: Add database connectivity check
    return {"status": "ready"}
