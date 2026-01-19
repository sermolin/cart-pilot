"""Application configuration.

Loads settings from environment variables with sensible defaults.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API
    api_version: str = "0.1.0"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://cartpilot:cartpilot_dev_password@db:5432/cartpilot"

    # Authentication
    cartpilot_api_key: str = "dev-api-key-change-in-production"

    # Webhooks
    webhook_secret: str = "dev-webhook-secret-change-in-production"

    # Merchants
    merchant_a_url: str = "http://merchant-a:8001"
    merchant_a_id: str = "merchant-a"
    merchant_a_enabled: bool = True

    merchant_b_url: str = "http://merchant-b:8002"
    merchant_b_id: str = "merchant-b"
    merchant_b_enabled: bool = True

    # Logging
    log_level: str = "INFO"

    class Config:
        """Pydantic configuration."""

        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
