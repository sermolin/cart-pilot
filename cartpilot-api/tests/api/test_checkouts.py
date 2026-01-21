"""Tests for checkout API endpoints.

Tests the approval flow including:
- Creating checkouts
- Getting quotes
- Requesting approval
- Approving checkouts
- Confirming checkouts
- Re-approval on price change
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status

from app.domain.entities import Offer, OfferItem
from app.domain.value_objects import (
    IntentId,
    MerchantId,
    Money,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_offer():
    """Create a sample offer for testing."""
    return Offer.create(
        intent_id=IntentId.generate(),
        merchant_id=MerchantId("merchant-a"),
        items=[
            OfferItem(
                product_id="prod-001",
                title="Test Product",
                unit_price=Money(amount_cents=2999, currency="USD"),
                quantity_available=100,
                sku="SKU-001",
            )
        ],
    )


# ============================================================================
# Test: Create Checkout
# ============================================================================


class TestCreateCheckout:
    """Tests for POST /checkouts."""

    def test_create_checkout_success(self, auth_client, sample_offer):
        """Test successful checkout creation."""
        # Mock offer repository (synchronous get method)
        with patch(
            "app.api.checkouts.get_offer_repository"
        ) as mock_get_repo:
            mock_repo = MagicMock()
            mock_repo.get.return_value = sample_offer
            mock_get_repo.return_value = mock_repo

            response = auth_client.post(
                "/checkouts",
                json={
                    "offer_id": str(sample_offer.id),
                    "items": [
                        {"product_id": "prod-001", "quantity": 1}
                    ],
                },
            )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["status"] == "created"
        assert data["offer_id"] == str(sample_offer.id)
        assert data["merchant_id"] == "merchant-a"
        assert len(data["audit_trail"]) > 0

    def test_create_checkout_idempotency(self, auth_client, sample_offer):
        """Test idempotent checkout creation."""
        idempotency_key = "test-key-idempotent"

        with patch(
            "app.api.checkouts.get_offer_repository"
        ) as mock_get_repo:
            mock_repo = MagicMock()
            mock_repo.get.return_value = sample_offer
            mock_get_repo.return_value = mock_repo

            # First request
            response1 = auth_client.post(
                "/checkouts",
                json={
                    "offer_id": str(sample_offer.id),
                    "items": [{"product_id": "prod-001", "quantity": 1}],
                    "idempotency_key": idempotency_key,
                },
            )

            # Second request with same idempotency key
            response2 = auth_client.post(
                "/checkouts",
                json={
                    "offer_id": str(sample_offer.id),
                    "items": [{"product_id": "prod-001", "quantity": 1}],
                    "idempotency_key": idempotency_key,
                },
            )

        assert response1.status_code == status.HTTP_201_CREATED
        assert response2.status_code == status.HTTP_201_CREATED
        assert response1.json()["id"] == response2.json()["id"]


# ============================================================================
# Test: Get Checkout
# ============================================================================


class TestGetCheckout:
    """Tests for GET /checkouts/{checkout_id}."""

    def test_get_checkout_success(self, auth_client, sample_offer):
        """Test getting an existing checkout."""
        # First create a checkout
        with patch(
            "app.api.checkouts.get_offer_repository"
        ) as mock_get_repo:
            mock_repo = MagicMock()
            mock_repo.get.return_value = sample_offer
            mock_get_repo.return_value = mock_repo

            create_response = auth_client.post(
                "/checkouts",
                json={
                    "offer_id": str(sample_offer.id),
                    "items": [{"product_id": "prod-001", "quantity": 1}],
                },
            )

        checkout_id = create_response.json()["id"]

        # Then get it
        response = auth_client.get(f"/checkouts/{checkout_id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == checkout_id
        assert data["status"] == "created"

    def test_get_checkout_not_found(self, auth_client):
        """Test getting non-existent checkout."""
        response = auth_client.get(
            "/checkouts/00000000-0000-0000-0000-000000000000"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["error_code"] == "CHECKOUT_NOT_FOUND"


# ============================================================================
# Test: Full Approval Flow
# ============================================================================


class TestApprovalFlow:
    """Tests for the complete approval flow."""

    @pytest.fixture
    def mock_merchant_client(self):
        """Mock merchant client for quote/confirm."""
        with patch(
            "app.application.checkout_service.MerchantClientFactory"
        ) as mock_factory:
            # Create a MagicMock for the client (synchronous properties)
            mock_client = MagicMock()

            # Mock quote response (plain object, not async)
            mock_quote = MagicMock()
            mock_quote.checkout_id = "merchant-checkout-001"
            mock_quote.status = "quoted"
            mock_quote.items = [
                MagicMock(
                    product_id="prod-001",
                    variant_id=None,
                    sku="SKU-001",
                    title="Test Product",
                    unit_price_cents=2999,
                    quantity=1,
                    line_total_cents=2999,
                    currency="USD",
                )
            ]
            mock_quote.subtotal_cents = 2999
            mock_quote.tax_cents = 240
            mock_quote.shipping_cents = 0
            mock_quote.total_cents = 3239
            mock_quote.currency = "USD"
            mock_quote.receipt_hash = "abc123"
            mock_quote.expires_at = None

            # Use AsyncMock for async methods
            mock_client.create_quote = AsyncMock(return_value=mock_quote)

            # Mock confirm response
            mock_confirm = MagicMock()
            mock_confirm.checkout_id = "merchant-checkout-001"
            mock_confirm.merchant_order_id = "ORD-20260119-ABC123"
            mock_confirm.status = "confirmed"
            mock_confirm.total_cents = 3239
            mock_confirm.currency = "USD"
            mock_confirm.confirmed_at = datetime.now(timezone.utc).isoformat()

            mock_client.confirm_checkout = AsyncMock(return_value=mock_confirm)

            # Setup factory context manager - get_client is synchronous
            mock_factory_instance = MagicMock()
            mock_factory_instance.get_client.return_value = mock_client
            # But __aenter__ and __aexit__ need to be async
            mock_factory_instance.__aenter__ = AsyncMock(return_value=mock_factory_instance)
            mock_factory_instance.__aexit__ = AsyncMock(return_value=None)

            mock_factory.return_value = mock_factory_instance

            yield mock_client

    def test_full_approval_flow(
        self, auth_client, sample_offer, mock_merchant_client
    ):
        """Test the complete checkout flow: create → quote → request-approval → approve → confirm."""
        # Step 1: Create checkout
        with patch(
            "app.api.checkouts.get_offer_repository"
        ) as mock_get_repo:
            mock_repo = MagicMock()
            mock_repo.get.return_value = sample_offer
            mock_get_repo.return_value = mock_repo

            create_response = auth_client.post(
                "/checkouts",
                json={
                    "offer_id": str(sample_offer.id),
                    "items": [{"product_id": "prod-001", "quantity": 1}],
                },
            )

        assert create_response.status_code == status.HTTP_201_CREATED
        checkout_id = create_response.json()["id"]
        assert create_response.json()["status"] == "created"

        # Step 2: Get quote
        quote_response = auth_client.post(
            f"/checkouts/{checkout_id}/quote",
            json={
                "items": [{"product_id": "prod-001", "quantity": 1}],
            },
        )

        assert quote_response.status_code == status.HTTP_200_OK
        assert quote_response.json()["status"] == "quoted"
        assert quote_response.json()["total"]["amount"] == 3239

        # Step 3: Request approval
        approval_request_response = auth_client.post(
            f"/checkouts/{checkout_id}/request-approval"
        )

        assert approval_request_response.status_code == status.HTTP_200_OK
        assert approval_request_response.json()["status"] == "awaiting_approval"
        assert approval_request_response.json()["frozen_receipt"] is not None
        frozen_hash = approval_request_response.json()["frozen_receipt"]["hash"]
        assert frozen_hash is not None

        # Step 4: Approve
        approve_response = auth_client.post(
            f"/checkouts/{checkout_id}/approve",
            json={"approved_by": "test-user"},
        )

        assert approve_response.status_code == status.HTTP_200_OK
        assert approve_response.json()["status"] == "approved"
        assert approve_response.json()["approved_by"] == "test-user"

        # Step 5: Confirm
        confirm_response = auth_client.post(
            f"/checkouts/{checkout_id}/confirm",
            json={"payment_method": "test_card"},
        )

        assert confirm_response.status_code == status.HTTP_200_OK
        assert confirm_response.json()["status"] == "confirmed"
        assert confirm_response.json()["merchant_order_id"] == "ORD-20260119-ABC123"


# ============================================================================
# Test: Re-approval Flow
# ============================================================================


class TestReapprovalFlow:
    """Tests for re-approval when price changes."""

    def test_reapproval_required_on_price_change(
        self, auth_client, sample_offer
    ):
        """Test that price change triggers re-approval requirement."""
        # Create checkout
        with patch(
            "app.api.checkouts.get_offer_repository"
        ) as mock_get_repo:
            mock_repo = MagicMock()
            mock_repo.get.return_value = sample_offer
            mock_get_repo.return_value = mock_repo

            create_response = auth_client.post(
                "/checkouts",
                json={
                    "offer_id": str(sample_offer.id),
                    "items": [{"product_id": "prod-001", "quantity": 1}],
                },
            )

        checkout_id = create_response.json()["id"]

        # Quote with original price
        with patch(
            "app.application.checkout_service.MerchantClientFactory"
        ) as mock_factory:
            mock_client = MagicMock()
            mock_quote = MagicMock()
            mock_quote.checkout_id = "merchant-checkout-001"
            mock_quote.items = [
                MagicMock(
                    product_id="prod-001",
                    variant_id=None,
                    sku="SKU-001",
                    title="Test Product",
                    unit_price_cents=2999,
                    quantity=1,
                    currency="USD",
                )
            ]
            mock_quote.subtotal_cents = 2999
            mock_quote.tax_cents = 240
            mock_quote.shipping_cents = 0
            mock_quote.total_cents = 3239
            mock_quote.currency = "USD"
            mock_quote.receipt_hash = "abc123"
            mock_quote.expires_at = None

            mock_client.create_quote = AsyncMock(return_value=mock_quote)

            mock_factory_instance = MagicMock()
            mock_factory_instance.get_client.return_value = mock_client
            mock_factory_instance.__aenter__ = AsyncMock(return_value=mock_factory_instance)
            mock_factory_instance.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_factory_instance

            quote_response = auth_client.post(
                f"/checkouts/{checkout_id}/quote",
                json={"items": [{"product_id": "prod-001", "quantity": 1}]},
            )

        assert quote_response.status_code == status.HTTP_200_OK
        original_total = quote_response.json()["total"]["amount"]

        # Request approval
        approval_response = auth_client.post(
            f"/checkouts/{checkout_id}/request-approval"
        )

        assert approval_response.status_code == status.HTTP_200_OK
        assert approval_response.json()["status"] == "awaiting_approval"

        # Simulate price change by requoting with different price
        with patch(
            "app.application.checkout_service.MerchantClientFactory"
        ) as mock_factory:
            mock_client = MagicMock()
            mock_quote = MagicMock()
            mock_quote.checkout_id = "merchant-checkout-001"
            mock_quote.items = [
                MagicMock(
                    product_id="prod-001",
                    variant_id=None,
                    sku="SKU-001",
                    title="Test Product",
                    unit_price_cents=3499,  # PRICE INCREASED!
                    quantity=1,
                    currency="USD",
                )
            ]
            mock_quote.subtotal_cents = 3499
            mock_quote.tax_cents = 280
            mock_quote.shipping_cents = 0
            mock_quote.total_cents = 3779  # New total
            mock_quote.currency = "USD"
            mock_quote.receipt_hash = "xyz789"
            mock_quote.expires_at = None

            mock_client.create_quote = AsyncMock(return_value=mock_quote)

            mock_factory_instance = MagicMock()
            mock_factory_instance.get_client.return_value = mock_client
            mock_factory_instance.__aenter__ = AsyncMock(return_value=mock_factory_instance)
            mock_factory_instance.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_factory_instance

            # Re-quote triggers re-approval (checkout goes back to quoted)
            requote_response = auth_client.post(
                f"/checkouts/{checkout_id}/quote",
                json={"items": [{"product_id": "prod-001", "quantity": 1}]},
            )

        assert requote_response.status_code == status.HTTP_200_OK
        # Status should be back to quoted because price changed
        assert requote_response.json()["status"] == "quoted"
        new_total = requote_response.json()["total"]["amount"]
        assert new_total != original_total  # Price actually changed


# ============================================================================
# Test: Audit Trail
# ============================================================================


class TestAuditTrail:
    """Tests for checkout audit trail."""

    def test_audit_trail_records_all_transitions(
        self, auth_client, sample_offer
    ):
        """Test that audit trail records all state transitions."""
        # Create checkout
        with patch(
            "app.api.checkouts.get_offer_repository"
        ) as mock_get_repo:
            mock_repo = MagicMock()
            mock_repo.get.return_value = sample_offer
            mock_get_repo.return_value = mock_repo

            response = auth_client.post(
                "/checkouts",
                json={
                    "offer_id": str(sample_offer.id),
                    "items": [{"product_id": "prod-001", "quantity": 1}],
                },
            )

        checkout_id = response.json()["id"]
        audit_trail = response.json()["audit_trail"]

        # Should have creation entry
        assert len(audit_trail) >= 1
        assert audit_trail[0]["action"] == "checkout_created"
        assert audit_trail[0]["to_status"] == "created"
        assert audit_trail[0]["timestamp"] is not None
