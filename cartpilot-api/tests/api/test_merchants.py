"""Tests for merchant API endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.config import settings
from app.main import app


@pytest.fixture
def auth_client() -> TestClient:
    """Create test client with authentication."""
    return TestClient(
        app,
        headers={"Authorization": f"Bearer {settings.cartpilot_api_key}"},
    )


class TestListMerchants:
    """Tests for GET /merchants endpoint."""

    def test_list_merchants_success(self, auth_client: TestClient) -> None:
        """Should list all enabled merchants."""
        response = auth_client.get("/merchants")
        assert response.status_code == 200

        data = response.json()
        assert "merchants" in data
        assert "total" in data
        assert isinstance(data["merchants"], list)

        # Should have at least merchant-a configured
        if data["total"] > 0:
            merchant = data["merchants"][0]
            assert "id" in merchant
            assert "name" in merchant
            assert "url" in merchant
            assert "enabled" in merchant

    def test_list_merchants_requires_auth(self) -> None:
        """Should require authentication."""
        client = TestClient(app)
        response = client.get("/merchants")
        assert response.status_code == 401
