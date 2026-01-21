"""Tests for API middleware."""

import pytest
from fastapi.testclient import TestClient

from app.infrastructure.config import settings
from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


class TestRequestIdMiddleware:
    """Tests for request ID correlation middleware."""

    def test_generates_request_id_if_not_provided(self, client: TestClient) -> None:
        """Should generate request ID if not in request headers."""
        response = client.get("/health")
        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        # UUID format
        request_id = response.headers["X-Request-ID"]
        assert len(request_id) == 36

    def test_uses_provided_request_id(self, client: TestClient) -> None:
        """Should use request ID from request headers."""
        custom_id = "custom-request-id-12345"
        response = client.get(
            "/health",
            headers={"X-Request-ID": custom_id},
        )
        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == custom_id


class TestApiKeyMiddleware:
    """Tests for API key authentication middleware."""

    def test_public_endpoints_dont_require_auth(self, client: TestClient) -> None:
        """Public endpoints should work without authentication."""
        # Health endpoints are public
        response = client.get("/health")
        assert response.status_code == 200

        response = client.get("/ready")
        assert response.status_code == 200

    def test_protected_endpoints_require_auth(self, client: TestClient) -> None:
        """Protected endpoints should require authentication."""
        response = client.post(
            "/intents",
            json={"query": "test query"},
        )
        assert response.status_code == 401
        data = response.json()
        assert data["error_code"] == "UNAUTHORIZED"

    def test_invalid_auth_format_rejected(self, client: TestClient) -> None:
        """Invalid authorization header format should be rejected."""
        response = client.post(
            "/intents",
            json={"query": "test query"},
            headers={"Authorization": "InvalidFormat"},
        )
        assert response.status_code == 401
        data = response.json()
        assert data["error_code"] == "UNAUTHORIZED"

    def test_invalid_api_key_rejected(self, client: TestClient) -> None:
        """Invalid API key should be rejected."""
        response = client.post(
            "/intents",
            json={"query": "test query"},
            headers={"Authorization": "Bearer invalid-key"},
        )
        assert response.status_code == 401
        data = response.json()
        assert data["error_code"] == "INVALID_API_KEY"

    def test_valid_api_key_accepted(self, client: TestClient) -> None:
        """Valid API key should be accepted."""
        response = client.post(
            "/intents",
            json={"query": "test query"},
            headers={"Authorization": f"Bearer {settings.cartpilot_api_key}"},
        )
        # Should not be 401
        assert response.status_code in (200, 201, 400, 404, 500)
