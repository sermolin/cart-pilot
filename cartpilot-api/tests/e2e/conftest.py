"""Shared fixtures for E2E tests.

These fixtures set up the test environment for integration testing
with mocked merchant services.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any, Generator

from fastapi.testclient import TestClient

from app.infrastructure.config import settings
from app.main import app
from app.domain.entities import Offer, OfferItem, Intent
from app.domain.value_objects import IntentId, MerchantId, Money


# ============================================================================
# Client Fixtures
# ============================================================================


@pytest.fixture
def client() -> TestClient:
    """Create test client without authentication."""
    return TestClient(app)


@pytest.fixture
def auth_client() -> TestClient:
    """Create test client with valid API key authentication."""
    return TestClient(
        app,
        headers={
            "Authorization": f"Bearer {settings.cartpilot_api_key}",
            "X-Request-ID": "e2e-test-request",
        },
    )


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Get authentication headers."""
    return {
        "Authorization": f"Bearer {settings.cartpilot_api_key}",
        "X-Request-ID": "e2e-test-request",
    }


# ============================================================================
# Sample Data Fixtures
# ============================================================================


@pytest.fixture
def sample_intent() -> Intent:
    """Create a sample intent for testing."""
    return Intent.create(
        query="wireless headphones under $100",
        session_id="e2e-test-session",
        metadata={"category": "electronics"},
    )


@pytest.fixture
def sample_offer_merchant_a() -> Offer:
    """Create a sample offer from Merchant A (happy path)."""
    return Offer.create(
        intent_id=IntentId.generate(),
        merchant_id=MerchantId("merchant-a"),
        items=[
            OfferItem(
                product_id="prod-headphones-001",
                title="Acme Wireless Headphones Pro",
                description="Premium wireless headphones with noise cancellation",
                brand="Acme",
                category_path="Electronics > Audio > Headphones",
                unit_price=Money(amount_cents=7999, currency="USD"),
                quantity_available=50,
                sku="ACME-HP-001",
                rating=4.5,
                review_count=128,
            ),
            OfferItem(
                product_id="prod-headphones-002",
                title="Contoso Bluetooth Earbuds",
                description="True wireless earbuds with 24h battery",
                brand="Contoso",
                category_path="Electronics > Audio > Earbuds",
                unit_price=Money(amount_cents=4999, currency="USD"),
                quantity_available=100,
                sku="CONT-EB-002",
                rating=4.2,
                review_count=256,
            ),
        ],
    )


@pytest.fixture
def sample_offer_merchant_b() -> Offer:
    """Create a sample offer from Merchant B (chaos mode)."""
    return Offer.create(
        intent_id=IntentId.generate(),
        merchant_id=MerchantId("merchant-b"),
        items=[
            OfferItem(
                product_id="prod-headphones-b01",
                title="Northwind Studio Headphones",
                description="Studio-quality wireless headphones",
                brand="Northwind",
                category_path="Electronics > Audio > Headphones",
                unit_price=Money(amount_cents=8999, currency="USD"),
                quantity_available=10,  # Low inventory for chaos testing
                sku="NW-SH-001",
                rating=4.7,
                review_count=64,
            ),
        ],
    )


# ============================================================================
# Mock Merchant Client
# ============================================================================


def create_mock_quote(
    checkout_id: str = "merchant-checkout-001",
    product_id: str = "prod-headphones-001",
    title: str = "Acme Wireless Headphones Pro",
    unit_price_cents: int = 7999,
    quantity: int = 1,
    tax_percent: float = 0.08,
    shipping_cents: int = 0,
) -> MagicMock:
    """Create a mock quote response."""
    subtotal = unit_price_cents * quantity
    tax = int(subtotal * tax_percent)
    total = subtotal + tax + shipping_cents

    mock_quote = MagicMock()
    mock_quote.checkout_id = checkout_id
    mock_quote.status = "quoted"
    mock_quote.items = [
        MagicMock(
            product_id=product_id,
            variant_id=None,
            sku="SKU-001",
            title=title,
            unit_price_cents=unit_price_cents,
            quantity=quantity,
            line_total_cents=unit_price_cents * quantity,
            currency="USD",
        )
    ]
    mock_quote.subtotal_cents = subtotal
    mock_quote.tax_cents = tax
    mock_quote.shipping_cents = shipping_cents
    mock_quote.total_cents = total
    mock_quote.currency = "USD"
    mock_quote.receipt_hash = f"hash-{checkout_id}"
    mock_quote.expires_at = None

    return mock_quote


def create_mock_confirm(
    checkout_id: str = "merchant-checkout-001",
    merchant_order_id: str = "ORD-E2E-001",
    total_cents: int = 8639,
) -> MagicMock:
    """Create a mock confirm response."""
    mock_confirm = MagicMock()
    mock_confirm.checkout_id = checkout_id
    mock_confirm.merchant_order_id = merchant_order_id
    mock_confirm.status = "confirmed"
    mock_confirm.total_cents = total_cents
    mock_confirm.currency = "USD"
    mock_confirm.confirmed_at = datetime.now(timezone.utc).isoformat()

    return mock_confirm


@pytest.fixture
def mock_merchant_client_factory():
    """Factory for creating mock merchant clients with configurable behavior."""

    def _create_client(
        quote_response: MagicMock | None = None,
        confirm_response: MagicMock | None = None,
        quote_error: Exception | None = None,
        confirm_error: Exception | None = None,
    ) -> Generator[MagicMock, None, None]:
        with patch(
            "app.application.checkout_service.MerchantClientFactory"
        ) as mock_factory:
            mock_client = MagicMock()

            if quote_error:
                mock_client.create_quote = AsyncMock(side_effect=quote_error)
            else:
                mock_client.create_quote = AsyncMock(
                    return_value=quote_response or create_mock_quote()
                )

            if confirm_error:
                mock_client.confirm_checkout = AsyncMock(side_effect=confirm_error)
            else:
                mock_client.confirm_checkout = AsyncMock(
                    return_value=confirm_response or create_mock_confirm()
                )

            mock_factory_instance = MagicMock()
            mock_factory_instance.get_client.return_value = mock_client
            mock_factory_instance.__aenter__ = AsyncMock(
                return_value=mock_factory_instance
            )
            mock_factory_instance.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_factory_instance

            yield mock_client

    return _create_client


@pytest.fixture
def mock_offer_repository():
    """Create a mock offer repository."""

    def _create_repo(offers: dict[str, Offer]) -> Generator[MagicMock, None, None]:
        with patch("app.api.checkouts.get_offer_repository") as mock_get_repo:
            mock_repo = MagicMock()
            mock_repo.get.side_effect = lambda offer_id: offers.get(str(offer_id))
            mock_get_repo.return_value = mock_repo
            yield mock_repo

    return _create_repo


# ============================================================================
# Webhook Fixtures
# ============================================================================


@pytest.fixture
def create_webhook_payload():
    """Factory for creating webhook payloads."""

    def _create(
        event_id: str,
        event_type: str,
        merchant_id: str = "merchant-a",
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "event_id": event_id,
            "event_type": event_type,
            "merchant_id": merchant_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data or {},
            "ucp_version": "1.0.0",
        }

    return _create


# ============================================================================
# Utility Functions
# ============================================================================


def complete_checkout_flow(
    auth_client: TestClient,
    offer: Offer,
    mock_offer_repo,
    mock_merchant_factory,
    product_id: str = "prod-headphones-001",
    quantity: int = 1,
) -> dict[str, Any]:
    """Complete the full checkout flow and return the result.

    Returns a dict with:
    - checkout_id
    - order_id (if created)
    - merchant_order_id
    - responses for each step
    """
    result = {"responses": {}}

    # Mock offer repository
    offers_dict = {str(offer.id): offer}
    with mock_offer_repo(offers_dict):
        # Create checkout
        create_resp = auth_client.post(
            "/checkouts",
            json={
                "offer_id": str(offer.id),
                "items": [{"product_id": product_id, "quantity": quantity}],
            },
        )
        result["responses"]["create"] = create_resp

        if create_resp.status_code != 201:
            return result

        checkout_id = create_resp.json()["id"]
        result["checkout_id"] = checkout_id

    # Get quote, request approval, approve, confirm
    with mock_merchant_factory():
        # Quote
        quote_resp = auth_client.post(
            f"/checkouts/{checkout_id}/quote",
            json={"items": [{"product_id": product_id, "quantity": quantity}]},
        )
        result["responses"]["quote"] = quote_resp

        if quote_resp.status_code != 200:
            return result

        # Request approval
        approval_req_resp = auth_client.post(
            f"/checkouts/{checkout_id}/request-approval"
        )
        result["responses"]["request_approval"] = approval_req_resp

        if approval_req_resp.status_code != 200:
            return result

        # Approve
        approve_resp = auth_client.post(
            f"/checkouts/{checkout_id}/approve",
            json={"approved_by": "e2e-test-user"},
        )
        result["responses"]["approve"] = approve_resp

        if approve_resp.status_code != 200:
            return result

        # Confirm
        confirm_resp = auth_client.post(
            f"/checkouts/{checkout_id}/confirm",
            json={"payment_method": "test_card"},
        )
        result["responses"]["confirm"] = confirm_resp

        if confirm_resp.status_code == 200:
            data = confirm_resp.json()
            result["merchant_order_id"] = data.get("merchant_order_id")
            result["order_id"] = data.get("order_id")

    return result
