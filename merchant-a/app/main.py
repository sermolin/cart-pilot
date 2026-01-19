"""Merchant A Simulator main application.

A stable, happy-path merchant simulator implementing UCP-like contract.
"""

from fastapi import FastAPI
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Merchant A settings."""

    merchant_id: str = "merchant-a"
    webhook_url: str = "http://cartpilot-api:8000/webhooks/merchant"
    webhook_secret: str = "dev-webhook-secret-change-in-production"
    log_level: str = "INFO"

    class Config:
        """Pydantic configuration."""

        env_file = ".env"


settings = Settings()

app = FastAPI(
    title="Merchant A Simulator",
    description="Happy path merchant simulator (stable pricing, high inventory)",
    version="0.1.0",
)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str
    merchant_id: str
    ucp_version: str


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Check service health.

    Returns:
        Health status with merchant info.
    """
    return HealthResponse(
        status="healthy",
        service="merchant-a",
        merchant_id=settings.merchant_id,
        ucp_version="1.0.0",
    )
