"""Shared fixtures for API tests."""

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.config import settings
from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Create test client without authentication."""
    return TestClient(app)


@pytest.fixture
def auth_client() -> TestClient:
    """Create test client with valid API key authentication."""
    return TestClient(
        app,
        headers={"Authorization": f"Bearer {settings.cartpilot_api_key}"},
    )


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Get authentication headers."""
    return {"Authorization": f"Bearer {settings.cartpilot_api_key}"}
