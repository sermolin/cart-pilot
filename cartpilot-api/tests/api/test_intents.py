"""Tests for intent API endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.application.intent_service import (
    _intent_repo,
    _offer_repo,
    get_intent_repository,
    get_offer_repository,
)
from app.infrastructure.config import settings
from app.main import app


@pytest.fixture
def auth_client() -> TestClient:
    """Create test client with authentication."""
    return TestClient(
        app,
        headers={"Authorization": f"Bearer {settings.cartpilot_api_key}"},
    )


@pytest.fixture(autouse=True)
def reset_repositories():
    """Reset in-memory repositories before each test."""
    # Clear existing data
    import app.application.intent_service as intent_service
    intent_service._intent_repo = None
    intent_service._offer_repo = None
    yield
    # Clean up after test
    intent_service._intent_repo = None
    intent_service._offer_repo = None


class TestCreateIntent:
    """Tests for POST /intents endpoint."""

    def test_create_intent_success(self, auth_client: TestClient) -> None:
        """Should create intent with valid query."""
        response = auth_client.post(
            "/intents",
            json={"query": "I need wireless headphones under $100"},
        )
        assert response.status_code == 201
        data = response.json()

        assert "id" in data
        assert data["query"] == "I need wireless headphones under $100"
        assert data["offers_collected"] is False
        assert data["offer_count"] == 0
        assert "created_at" in data
        assert "updated_at" in data

    def test_create_intent_with_session_id(self, auth_client: TestClient) -> None:
        """Should create intent with session ID."""
        response = auth_client.post(
            "/intents",
            json={
                "query": "laptop for coding",
                "session_id": "session-123",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["session_id"] == "session-123"

    def test_create_intent_with_metadata(self, auth_client: TestClient) -> None:
        """Should create intent with metadata."""
        response = auth_client.post(
            "/intents",
            json={
                "query": "gaming keyboard",
                "metadata": {"category": "electronics", "max_price": 15000},
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["metadata"]["category"] == "electronics"
        assert data["metadata"]["max_price"] == 15000

    def test_create_intent_empty_query_rejected(self, auth_client: TestClient) -> None:
        """Should reject empty query."""
        response = auth_client.post(
            "/intents",
            json={"query": ""},
        )
        assert response.status_code == 422  # Validation error

    def test_create_intent_requires_auth(self) -> None:
        """Should require authentication."""
        client = TestClient(app)
        response = client.post(
            "/intents",
            json={"query": "test"},
        )
        assert response.status_code == 401


class TestGetIntent:
    """Tests for GET /intents/{intent_id} endpoint."""

    def test_get_intent_success(self, auth_client: TestClient) -> None:
        """Should get existing intent."""
        # Create intent first
        create_response = auth_client.post(
            "/intents",
            json={"query": "office chair"},
        )
        intent_id = create_response.json()["id"]

        # Get intent
        response = auth_client.get(f"/intents/{intent_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == intent_id
        assert data["query"] == "office chair"

    def test_get_intent_not_found(self, auth_client: TestClient) -> None:
        """Should return 404 for non-existent intent."""
        response = auth_client.get("/intents/non-existent-id")
        assert response.status_code == 404
        data = response.json()
        assert data["error_code"] == "INTENT_NOT_FOUND"


class TestGetIntentOffers:
    """Tests for GET /intents/{intent_id}/offers endpoint."""

    def test_get_offers_for_intent(self, auth_client: TestClient) -> None:
        """Should get offers for intent."""
        # Create intent first
        create_response = auth_client.post(
            "/intents",
            json={"query": "headphones"},
        )
        intent_id = create_response.json()["id"]

        # Get offers (will trigger collection since none collected yet)
        # Note: This may fail if merchants are not available
        response = auth_client.get(f"/intents/{intent_id}/offers")

        # Should return 200 even if no offers collected
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["intent_id"] == intent_id

    def test_get_offers_intent_not_found(self, auth_client: TestClient) -> None:
        """Should return 404 for non-existent intent."""
        response = auth_client.get("/intents/non-existent-id/offers")
        assert response.status_code == 404
        data = response.json()
        assert data["error_code"] == "INTENT_NOT_FOUND"

    def test_get_offers_with_pagination(self, auth_client: TestClient) -> None:
        """Should support pagination parameters."""
        # Create intent
        create_response = auth_client.post(
            "/intents",
            json={"query": "laptop"},
        )
        intent_id = create_response.json()["id"]

        # Get offers with pagination
        response = auth_client.get(
            f"/intents/{intent_id}/offers",
            params={"page": 1, "page_size": 5},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 5
