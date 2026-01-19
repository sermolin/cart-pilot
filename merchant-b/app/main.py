"""Merchant B Simulator main application.

A chaos-mode merchant simulator for testing edge cases and error handling.
"""

from fastapi import FastAPI
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Merchant B settings."""

    merchant_id: str = "merchant-b"
    webhook_url: str = "http://cartpilot-api:8000/webhooks/merchant"
    webhook_secret: str = "dev-webhook-secret-change-in-production"
    chaos_enabled: bool = False
    log_level: str = "INFO"

    class Config:
        """Pydantic configuration."""

        env_file = ".env"


settings = Settings()

app = FastAPI(
    title="Merchant B Simulator",
    description="Chaos mode merchant simulator (price changes, out-of-stock, webhook issues)",
    version="0.1.0",
)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str
    merchant_id: str
    ucp_version: str
    chaos_enabled: bool


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Check service health.

    Returns:
        Health status with merchant info and chaos mode status.
    """
    return HealthResponse(
        status="healthy",
        service="merchant-b",
        merchant_id=settings.merchant_id,
        ucp_version="1.0.0",
        chaos_enabled=settings.chaos_enabled,
    )
