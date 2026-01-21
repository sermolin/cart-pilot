"""Tests for offer API endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.application.intent_service import (
    IntentService,
    get_intent_repository,
    get_offer_repository,
)
from app.domain.entities import Offer, OfferItem
from app.domain.value_objects import IntentId, MerchantId, Money, OfferId
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
    import app.application.intent_service as intent_service
    intent_service._intent_repo = None
    intent_service._offer_repo = None
    yield
    intent_service._intent_repo = None
    intent_service._offer_repo = None


class TestGetOffer:
    """Tests for GET /offers/{offer_id} endpoint."""

    def test_get_offer_not_found(self, auth_client: TestClient) -> None:
        """Should return 404 for non-existent offer."""
        response = auth_client.get("/offers/non-existent-id")
        assert response.status_code == 404
        data = response.json()
        assert data["error_code"] == "OFFER_NOT_FOUND"

    def test_get_offer_success(self, auth_client: TestClient) -> None:
        """Should get existing offer."""
        # Create an offer directly in repository
        offer_repo = get_offer_repository()

        intent_id = IntentId.generate()
        offer = Offer.create(
            intent_id=intent_id,
            merchant_id=MerchantId("test-merchant"),
            items=[
                OfferItem(
                    product_id="prod-1",
                    title="Test Product",
                    unit_price=Money(amount_cents=9999, currency="USD"),
                    quantity_available=10,
                )
            ],
        )
        offer_repo.save(offer)

        # Get offer
        response = auth_client.get(f"/offers/{offer.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == str(offer.id)
        assert data["merchant_id"] == "test-merchant"
        assert data["item_count"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["product_id"] == "prod-1"
        assert data["items"][0]["title"] == "Test Product"
        assert data["items"][0]["price"]["amount"] == 9999

    def test_get_offer_requires_auth(self) -> None:
        """Should require authentication."""
        client = TestClient(app)
        response = client.get("/offers/some-id")
        assert response.status_code == 401
