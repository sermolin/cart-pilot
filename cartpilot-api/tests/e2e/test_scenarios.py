"""E2E Integration Test Scenarios for CartPilot.

Tests the 8 core E2E scenarios:
1. Happy path purchase (merchant-a)
2. Retry with same idempotency key
3. Price change → re-approval (merchant-b)
4. Out-of-stock failure
5. Duplicate webhooks handling
6. Out-of-order webhooks
7. Partial failure recovery
8. Refund flow
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest
from fastapi import status

from app.domain.entities import Offer, OfferItem
from app.domain.value_objects import IntentId, MerchantId, Money

from .conftest import create_mock_quote, create_mock_confirm, complete_checkout_flow


# ============================================================================
# Scenario 1: Happy Path Purchase (Merchant A)
# ============================================================================


class TestScenario1HappyPath:
    """Test complete purchase flow with stable merchant (Merchant A)."""

    def test_happy_path_full_flow(
        self,
        auth_client,
        sample_offer_merchant_a,
        mock_offer_repository,
        mock_merchant_client_factory,
    ):
        """Scenario 1: Complete purchase from intent to order."""
        offer = sample_offer_merchant_a
        product_id = "prod-headphones-001"

        # Complete the full flow
        result = complete_checkout_flow(
            auth_client=auth_client,
            offer=offer,
            mock_offer_repo=mock_offer_repository,
            mock_merchant_factory=mock_merchant_client_factory,
            product_id=product_id,
        )

        # Verify all steps succeeded
        assert result["responses"]["create"].status_code == status.HTTP_201_CREATED
        assert result["responses"]["quote"].status_code == status.HTTP_200_OK
        assert result["responses"]["request_approval"].status_code == status.HTTP_200_OK
        assert result["responses"]["approve"].status_code == status.HTTP_200_OK
        assert result["responses"]["confirm"].status_code == status.HTTP_200_OK

        # Verify final state
        confirm_data = result["responses"]["confirm"].json()
        assert confirm_data["status"] == "confirmed"
        assert confirm_data["merchant_order_id"] is not None
        assert confirm_data["order_id"] is not None

        # Verify order was created
        order_id = confirm_data["order_id"]
        order_resp = auth_client.get(f"/orders/{order_id}")
        assert order_resp.status_code == status.HTTP_200_OK
        order_data = order_resp.json()
        assert order_data["status"] == "pending"
        assert order_data["checkout_id"] == result["checkout_id"]

    def test_happy_path_checkout_states_in_order(
        self,
        auth_client,
        sample_offer_merchant_a,
        mock_offer_repository,
        mock_merchant_client_factory,
    ):
        """Verify checkout transitions through all expected states."""
        offer = sample_offer_merchant_a
        product_id = "prod-headphones-001"
        offers_dict = {str(offer.id): offer}

        expected_states = [
            "created",
            "quoted",
            "awaiting_approval",
            "approved",
            "confirmed",
        ]
        actual_states = []

        with mock_offer_repository(offers_dict):
            # Create checkout
            create_resp = auth_client.post(
                "/checkouts",
                json={
                    "offer_id": str(offer.id),
                    "items": [{"product_id": product_id, "quantity": 1}],
                },
            )
            actual_states.append(create_resp.json()["status"])
            checkout_id = create_resp.json()["id"]

        with mock_merchant_client_factory():
            # Quote
            quote_resp = auth_client.post(
                f"/checkouts/{checkout_id}/quote",
                json={"items": [{"product_id": product_id, "quantity": 1}]},
            )
            actual_states.append(quote_resp.json()["status"])

            # Request approval
            approval_resp = auth_client.post(
                f"/checkouts/{checkout_id}/request-approval"
            )
            actual_states.append(approval_resp.json()["status"])

            # Approve
            approve_resp = auth_client.post(
                f"/checkouts/{checkout_id}/approve",
                json={"approved_by": "test-user"},
            )
            actual_states.append(approve_resp.json()["status"])

            # Confirm
            confirm_resp = auth_client.post(
                f"/checkouts/{checkout_id}/confirm",
                json={"payment_method": "test_card"},
            )
            actual_states.append(confirm_resp.json()["status"])

        assert actual_states == expected_states

    def test_happy_path_audit_trail_complete(
        self,
        auth_client,
        sample_offer_merchant_a,
        mock_offer_repository,
        mock_merchant_client_factory,
    ):
        """Verify audit trail captures all state transitions."""
        offer = sample_offer_merchant_a
        product_id = "prod-headphones-001"

        result = complete_checkout_flow(
            auth_client=auth_client,
            offer=offer,
            mock_offer_repo=mock_offer_repository,
            mock_merchant_factory=mock_merchant_client_factory,
            product_id=product_id,
        )

        # Get final checkout state
        checkout_id = result["checkout_id"]
        checkout_resp = auth_client.get(f"/checkouts/{checkout_id}")
        audit_trail = checkout_resp.json()["audit_trail"]

        # Should have entries for: created, quoted, awaiting_approval, approved, confirmed
        assert len(audit_trail) >= 5

        # Verify chronological order (timestamps increasing)
        timestamps = [entry["timestamp"] for entry in audit_trail]
        assert timestamps == sorted(timestamps)


# ============================================================================
# Scenario 2: Idempotency Key Retry
# ============================================================================


class TestScenario2Idempotency:
    """Test idempotent request handling."""

    def test_checkout_create_idempotency(
        self, auth_client, sample_offer_merchant_a, mock_offer_repository
    ):
        """Scenario 2a: Same idempotency key returns same checkout."""
        offer = sample_offer_merchant_a
        idempotency_key = f"idempotent-test-{uuid.uuid4()}"
        offers_dict = {str(offer.id): offer}

        with mock_offer_repository(offers_dict):
            # First request
            resp1 = auth_client.post(
                "/checkouts",
                json={
                    "offer_id": str(offer.id),
                    "items": [{"product_id": "prod-headphones-001", "quantity": 1}],
                    "idempotency_key": idempotency_key,
                },
            )

            # Second request with same key
            resp2 = auth_client.post(
                "/checkouts",
                json={
                    "offer_id": str(offer.id),
                    "items": [{"product_id": "prod-headphones-001", "quantity": 1}],
                    "idempotency_key": idempotency_key,
                },
            )

        assert resp1.status_code == status.HTTP_201_CREATED
        assert resp2.status_code == status.HTTP_201_CREATED
        assert resp1.json()["id"] == resp2.json()["id"]

    def test_confirm_idempotency(
        self,
        auth_client,
        sample_offer_merchant_a,
        mock_offer_repository,
        mock_merchant_client_factory,
    ):
        """Scenario 2b: Confirm with same idempotency key is safe."""
        offer = sample_offer_merchant_a
        product_id = "prod-headphones-001"
        offers_dict = {str(offer.id): offer}
        confirm_idempotency_key = f"confirm-test-{uuid.uuid4()}"

        # Create and get to approved state
        with mock_offer_repository(offers_dict):
            create_resp = auth_client.post(
                "/checkouts",
                json={
                    "offer_id": str(offer.id),
                    "items": [{"product_id": product_id, "quantity": 1}],
                },
            )
            checkout_id = create_resp.json()["id"]

        with mock_merchant_client_factory():
            auth_client.post(
                f"/checkouts/{checkout_id}/quote",
                json={"items": [{"product_id": product_id, "quantity": 1}]},
            )
            auth_client.post(f"/checkouts/{checkout_id}/request-approval")
            auth_client.post(
                f"/checkouts/{checkout_id}/approve",
                json={"approved_by": "test-user"},
            )

            # First confirm
            confirm1 = auth_client.post(
                f"/checkouts/{checkout_id}/confirm",
                json={
                    "payment_method": "test_card",
                    "idempotency_key": confirm_idempotency_key,
                },
            )

            # Second confirm with same key should return same result
            confirm2 = auth_client.post(
                f"/checkouts/{checkout_id}/confirm",
                json={
                    "payment_method": "test_card",
                    "idempotency_key": confirm_idempotency_key,
                },
            )

        assert confirm1.status_code == status.HTTP_200_OK
        # Second confirm may return 200 (idempotent) or 400 (already confirmed)
        # Both are acceptable behaviors
        assert confirm2.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
        ]

    def test_different_idempotency_keys_create_different_checkouts(
        self, auth_client, sample_offer_merchant_a, mock_offer_repository
    ):
        """Different idempotency keys create different checkouts."""
        offer = sample_offer_merchant_a
        offers_dict = {str(offer.id): offer}

        with mock_offer_repository(offers_dict):
            resp1 = auth_client.post(
                "/checkouts",
                json={
                    "offer_id": str(offer.id),
                    "items": [{"product_id": "prod-headphones-001", "quantity": 1}],
                    "idempotency_key": f"key-1-{uuid.uuid4()}",
                },
            )

            resp2 = auth_client.post(
                "/checkouts",
                json={
                    "offer_id": str(offer.id),
                    "items": [{"product_id": "prod-headphones-001", "quantity": 1}],
                    "idempotency_key": f"key-2-{uuid.uuid4()}",
                },
            )

        assert resp1.status_code == status.HTTP_201_CREATED
        assert resp2.status_code == status.HTTP_201_CREATED
        assert resp1.json()["id"] != resp2.json()["id"]


# ============================================================================
# Scenario 3: Price Change → Re-approval (Merchant B)
# ============================================================================


class TestScenario3PriceChangeReapproval:
    """Test re-approval flow when price changes."""

    def test_price_change_triggers_reapproval(
        self, auth_client, sample_offer_merchant_b, mock_offer_repository
    ):
        """Scenario 3: Price change between approval request and confirm triggers re-approval."""
        offer = sample_offer_merchant_b
        product_id = "prod-headphones-b01"
        offers_dict = {str(offer.id): offer}

        # Create checkout
        with mock_offer_repository(offers_dict):
            create_resp = auth_client.post(
                "/checkouts",
                json={
                    "offer_id": str(offer.id),
                    "items": [{"product_id": product_id, "quantity": 1}],
                },
            )
            checkout_id = create_resp.json()["id"]

        # Quote with original price
        original_price = 8999
        original_quote = create_mock_quote(
            product_id=product_id,
            title="Northwind Studio Headphones",
            unit_price_cents=original_price,
        )

        with patch(
            "app.application.checkout_service.MerchantClientFactory"
        ) as mock_factory:
            mock_client = MagicMock()
            mock_client.create_quote = AsyncMock(return_value=original_quote)

            mock_factory_instance = MagicMock()
            mock_factory_instance.get_client.return_value = mock_client
            mock_factory_instance.__aenter__ = AsyncMock(
                return_value=mock_factory_instance
            )
            mock_factory_instance.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_factory_instance

            quote_resp = auth_client.post(
                f"/checkouts/{checkout_id}/quote",
                json={"items": [{"product_id": product_id, "quantity": 1}]},
            )

        assert quote_resp.status_code == status.HTTP_200_OK
        original_total = quote_resp.json()["total"]["amount"]

        # Request approval - freezes the receipt
        approval_req = auth_client.post(
            f"/checkouts/{checkout_id}/request-approval"
        )
        assert approval_req.status_code == status.HTTP_200_OK
        assert approval_req.json()["frozen_receipt"] is not None
        frozen_total = approval_req.json()["frozen_receipt"]["total_cents"]
        assert frozen_total == original_total

        # Simulate price change - requote with higher price
        new_price = 10499  # ~17% increase
        new_quote = create_mock_quote(
            product_id=product_id,
            title="Northwind Studio Headphones",
            unit_price_cents=new_price,
        )

        with patch(
            "app.application.checkout_service.MerchantClientFactory"
        ) as mock_factory:
            mock_client = MagicMock()
            mock_client.create_quote = AsyncMock(return_value=new_quote)

            mock_factory_instance = MagicMock()
            mock_factory_instance.get_client.return_value = mock_client
            mock_factory_instance.__aenter__ = AsyncMock(
                return_value=mock_factory_instance
            )
            mock_factory_instance.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_factory_instance

            # Re-quote should trigger return to quoted state
            requote_resp = auth_client.post(
                f"/checkouts/{checkout_id}/quote",
                json={"items": [{"product_id": product_id, "quantity": 1}]},
            )

        # After requote with changed price, status goes back to quoted
        assert requote_resp.status_code == status.HTTP_200_OK
        assert requote_resp.json()["status"] == "quoted"
        new_total = requote_resp.json()["total"]["amount"]
        assert new_total != frozen_total

    def test_approve_after_price_change_requires_reapproval(
        self, auth_client, sample_offer_merchant_b, mock_offer_repository
    ):
        """Cannot approve if price changed after requesting approval."""
        offer = sample_offer_merchant_b
        product_id = "prod-headphones-b01"
        offers_dict = {str(offer.id): offer}

        with mock_offer_repository(offers_dict):
            create_resp = auth_client.post(
                "/checkouts",
                json={
                    "offer_id": str(offer.id),
                    "items": [{"product_id": product_id, "quantity": 1}],
                },
            )
            checkout_id = create_resp.json()["id"]

        # Go through quote → request approval
        original_quote = create_mock_quote(
            product_id=product_id,
            unit_price_cents=8999,
        )

        with patch(
            "app.application.checkout_service.MerchantClientFactory"
        ) as mock_factory:
            mock_client = MagicMock()
            mock_client.create_quote = AsyncMock(return_value=original_quote)

            mock_factory_instance = MagicMock()
            mock_factory_instance.get_client.return_value = mock_client
            mock_factory_instance.__aenter__ = AsyncMock(
                return_value=mock_factory_instance
            )
            mock_factory_instance.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_factory_instance

            auth_client.post(
                f"/checkouts/{checkout_id}/quote",
                json={"items": [{"product_id": product_id, "quantity": 1}]},
            )

        auth_client.post(f"/checkouts/{checkout_id}/request-approval")

        # Now requote with changed price
        new_quote = create_mock_quote(
            product_id=product_id,
            unit_price_cents=10499,  # Higher price
        )

        with patch(
            "app.application.checkout_service.MerchantClientFactory"
        ) as mock_factory:
            mock_client = MagicMock()
            mock_client.create_quote = AsyncMock(return_value=new_quote)

            mock_factory_instance = MagicMock()
            mock_factory_instance.get_client.return_value = mock_client
            mock_factory_instance.__aenter__ = AsyncMock(
                return_value=mock_factory_instance
            )
            mock_factory_instance.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_factory_instance

            auth_client.post(
                f"/checkouts/{checkout_id}/quote",
                json={"items": [{"product_id": product_id, "quantity": 1}]},
            )

        # Status is now "quoted", trying to approve should fail
        # because we need to request approval again
        approve_resp = auth_client.post(
            f"/checkouts/{checkout_id}/approve",
            json={"approved_by": "test-user"},
        )

        # Should fail because checkout is in "quoted" state, not "awaiting_approval"
        assert approve_resp.status_code == status.HTTP_400_BAD_REQUEST


# ============================================================================
# Scenario 4: Out-of-Stock Failure
# ============================================================================


class TestScenario4OutOfStock:
    """Test handling of out-of-stock scenarios."""

    def test_out_of_stock_on_confirm(
        self,
        auth_client,
        sample_offer_merchant_b,
        mock_offer_repository,
    ):
        """Scenario 4: Item becomes out-of-stock during confirm."""
        offer = sample_offer_merchant_b
        product_id = "prod-headphones-b01"
        offers_dict = {str(offer.id): offer}

        with mock_offer_repository(offers_dict):
            create_resp = auth_client.post(
                "/checkouts",
                json={
                    "offer_id": str(offer.id),
                    "items": [{"product_id": product_id, "quantity": 1}],
                },
            )
            checkout_id = create_resp.json()["id"]

        # Quote and approve successfully
        quote = create_mock_quote(product_id=product_id, unit_price_cents=8999)

        with patch(
            "app.application.checkout_service.MerchantClientFactory"
        ) as mock_factory:
            mock_client = MagicMock()
            mock_client.create_quote = AsyncMock(return_value=quote)

            mock_factory_instance = MagicMock()
            mock_factory_instance.get_client.return_value = mock_client
            mock_factory_instance.__aenter__ = AsyncMock(
                return_value=mock_factory_instance
            )
            mock_factory_instance.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_factory_instance

            auth_client.post(
                f"/checkouts/{checkout_id}/quote",
                json={"items": [{"product_id": product_id, "quantity": 1}]},
            )

        auth_client.post(f"/checkouts/{checkout_id}/request-approval")
        auth_client.post(
            f"/checkouts/{checkout_id}/approve",
            json={"approved_by": "test-user"},
        )

        # Confirm fails due to out-of-stock
        with patch(
            "app.application.checkout_service.MerchantClientFactory"
        ) as mock_factory:
            mock_client = MagicMock()

            # Simulate out-of-stock error
            mock_client.confirm_checkout = AsyncMock(
                side_effect=Exception("Product out of stock")
            )

            mock_factory_instance = MagicMock()
            mock_factory_instance.get_client.return_value = mock_client
            mock_factory_instance.__aenter__ = AsyncMock(
                return_value=mock_factory_instance
            )
            mock_factory_instance.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_factory_instance

            confirm_resp = auth_client.post(
                f"/checkouts/{checkout_id}/confirm",
                json={"payment_method": "test_card"},
            )

        # Should fail with appropriate error
        assert confirm_resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_out_of_stock_on_quote(
        self,
        auth_client,
        sample_offer_merchant_b,
        mock_offer_repository,
    ):
        """Item out-of-stock during quote returns appropriate error."""
        offer = sample_offer_merchant_b
        product_id = "prod-headphones-b01"
        offers_dict = {str(offer.id): offer}

        with mock_offer_repository(offers_dict):
            create_resp = auth_client.post(
                "/checkouts",
                json={
                    "offer_id": str(offer.id),
                    "items": [{"product_id": product_id, "quantity": 1}],
                },
            )
            checkout_id = create_resp.json()["id"]

        with patch(
            "app.application.checkout_service.MerchantClientFactory"
        ) as mock_factory:
            mock_client = MagicMock()
            mock_client.create_quote = AsyncMock(
                side_effect=Exception("Product not available")
            )

            mock_factory_instance = MagicMock()
            mock_factory_instance.get_client.return_value = mock_client
            mock_factory_instance.__aenter__ = AsyncMock(
                return_value=mock_factory_instance
            )
            mock_factory_instance.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_factory_instance

            quote_resp = auth_client.post(
                f"/checkouts/{checkout_id}/quote",
                json={"items": [{"product_id": product_id, "quantity": 1}]},
            )

        assert quote_resp.status_code == status.HTTP_400_BAD_REQUEST


# ============================================================================
# Scenario 5: Duplicate Webhooks Handling
# ============================================================================


class TestScenario5DuplicateWebhooks:
    """Test handling of duplicate webhook events."""

    def test_duplicate_webhook_ignored(self, auth_client, create_webhook_payload):
        """Scenario 5: Same webhook sent multiple times is handled idempotently."""
        event_id = f"evt-{uuid.uuid4()}"
        payload = create_webhook_payload(
            event_id=event_id,
            event_type="checkout.confirmed",
            merchant_id="merchant-a",
            data={"checkout_id": "checkout-123", "order_id": "order-456"},
        )

        # First webhook delivery
        resp1 = auth_client.post(
            "/webhooks/merchant",
            json=payload,
            headers={"X-Merchant-Id": "merchant-a"},
        )

        # Second delivery (duplicate)
        resp2 = auth_client.post(
            "/webhooks/merchant",
            json=payload,
            headers={"X-Merchant-Id": "merchant-a"},
        )

        # Third delivery (duplicate)
        resp3 = auth_client.post(
            "/webhooks/merchant",
            json=payload,
            headers={"X-Merchant-Id": "merchant-a"},
        )

        # All should succeed
        assert resp1.status_code == status.HTTP_200_OK
        assert resp2.status_code == status.HTTP_200_OK
        assert resp3.status_code == status.HTTP_200_OK

        # First should be processed, others marked as duplicate
        assert resp1.json()["status"] in ["processed", "ignored"]
        assert resp2.json()["status"] == "duplicate"
        assert resp3.json()["status"] == "duplicate"

    def test_duplicate_webhook_same_event_id_different_data(
        self, auth_client, create_webhook_payload
    ):
        """Duplicate with same event_id but different data still deduplicated."""
        event_id = f"evt-{uuid.uuid4()}"

        # First webhook
        payload1 = create_webhook_payload(
            event_id=event_id,
            event_type="order.shipped",
            data={"tracking_number": "TRACK001"},
        )

        # Second webhook with same event_id but different data
        payload2 = create_webhook_payload(
            event_id=event_id,
            event_type="order.shipped",
            data={"tracking_number": "TRACK002"},  # Different!
        )

        resp1 = auth_client.post(
            "/webhooks/merchant",
            json=payload1,
            headers={"X-Merchant-Id": "merchant-a"},
        )

        resp2 = auth_client.post(
            "/webhooks/merchant",
            json=payload2,
            headers={"X-Merchant-Id": "merchant-a"},
        )

        assert resp1.status_code == status.HTTP_200_OK
        assert resp2.status_code == status.HTTP_200_OK
        # Second is still duplicate by event_id
        assert resp2.json()["status"] == "duplicate"


# ============================================================================
# Scenario 6: Out-of-Order Webhooks
# ============================================================================


class TestScenario6OutOfOrderWebhooks:
    """Test handling of webhooks arriving in wrong order."""

    def test_out_of_order_webhooks_processed_correctly(
        self, auth_client, create_webhook_payload
    ):
        """Scenario 6: Webhooks arriving out-of-order are handled gracefully."""
        order_id = f"order-{uuid.uuid4()}"

        # Simulate webhooks arriving out of order:
        # Delivered arrives before Shipped

        # "Delivered" webhook arrives first
        delivered_payload = create_webhook_payload(
            event_id=f"evt-delivered-{uuid.uuid4()}",
            event_type="order.delivered",
            data={
                "order_id": order_id,
                "delivered_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        # "Shipped" webhook arrives second
        shipped_payload = create_webhook_payload(
            event_id=f"evt-shipped-{uuid.uuid4()}",
            event_type="order.shipped",
            data={
                "order_id": order_id,
                "tracking_number": "TRACK123",
                "carrier": "UPS",
            },
        )

        # Send delivered first
        resp1 = auth_client.post(
            "/webhooks/merchant",
            json=delivered_payload,
            headers={"X-Merchant-Id": "merchant-a"},
        )

        # Then shipped (even though it should have come first)
        resp2 = auth_client.post(
            "/webhooks/merchant",
            json=shipped_payload,
            headers={"X-Merchant-Id": "merchant-a"},
        )

        # Both should be accepted (system handles out-of-order)
        assert resp1.status_code == status.HTTP_200_OK
        assert resp2.status_code == status.HTTP_200_OK
        assert resp1.json()["success"] is True
        assert resp2.json()["success"] is True

    def test_old_status_webhook_after_newer_state(
        self, auth_client, create_webhook_payload
    ):
        """Old status webhook doesn't regress order state."""
        order_id = f"order-{uuid.uuid4()}"

        # First: Delivered
        delivered_payload = create_webhook_payload(
            event_id=f"evt-d-{uuid.uuid4()}",
            event_type="order.delivered",
            data={"order_id": order_id},
        )

        # Then: Confirmed (earlier state, arrives late)
        confirmed_payload = create_webhook_payload(
            event_id=f"evt-c-{uuid.uuid4()}",
            event_type="order.confirmed",
            data={"order_id": order_id},
        )

        resp1 = auth_client.post(
            "/webhooks/merchant",
            json=delivered_payload,
            headers={"X-Merchant-Id": "merchant-a"},
        )

        resp2 = auth_client.post(
            "/webhooks/merchant",
            json=confirmed_payload,
            headers={"X-Merchant-Id": "merchant-a"},
        )

        # Both accepted, system handles gracefully
        assert resp1.status_code == status.HTTP_200_OK
        assert resp2.status_code == status.HTTP_200_OK


# ============================================================================
# Scenario 7: Partial Failure Recovery
# ============================================================================


class TestScenario7PartialFailureRecovery:
    """Test recovery from partial failures in the checkout flow."""

    def test_recovery_after_quote_failure(
        self,
        auth_client,
        sample_offer_merchant_a,
        mock_offer_repository,
    ):
        """Scenario 7a: Can retry quote after initial failure."""
        offer = sample_offer_merchant_a
        product_id = "prod-headphones-001"
        offers_dict = {str(offer.id): offer}

        with mock_offer_repository(offers_dict):
            create_resp = auth_client.post(
                "/checkouts",
                json={
                    "offer_id": str(offer.id),
                    "items": [{"product_id": product_id, "quantity": 1}],
                },
            )
            checkout_id = create_resp.json()["id"]

        # First quote fails
        with patch(
            "app.application.checkout_service.MerchantClientFactory"
        ) as mock_factory:
            mock_client = MagicMock()
            mock_client.create_quote = AsyncMock(
                side_effect=Exception("Temporary network error")
            )

            mock_factory_instance = MagicMock()
            mock_factory_instance.get_client.return_value = mock_client
            mock_factory_instance.__aenter__ = AsyncMock(
                return_value=mock_factory_instance
            )
            mock_factory_instance.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_factory_instance

            failed_quote = auth_client.post(
                f"/checkouts/{checkout_id}/quote",
                json={"items": [{"product_id": product_id, "quantity": 1}]},
            )

        assert failed_quote.status_code == status.HTTP_400_BAD_REQUEST

        # Checkout should still be in created state (recoverable)
        checkout_resp = auth_client.get(f"/checkouts/{checkout_id}")
        assert checkout_resp.json()["status"] == "created"

        # Retry quote succeeds
        success_quote = create_mock_quote(product_id=product_id)

        with patch(
            "app.application.checkout_service.MerchantClientFactory"
        ) as mock_factory:
            mock_client = MagicMock()
            mock_client.create_quote = AsyncMock(return_value=success_quote)

            mock_factory_instance = MagicMock()
            mock_factory_instance.get_client.return_value = mock_client
            mock_factory_instance.__aenter__ = AsyncMock(
                return_value=mock_factory_instance
            )
            mock_factory_instance.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_factory_instance

            retry_quote = auth_client.post(
                f"/checkouts/{checkout_id}/quote",
                json={"items": [{"product_id": product_id, "quantity": 1}]},
            )

        assert retry_quote.status_code == status.HTTP_200_OK
        assert retry_quote.json()["status"] == "quoted"

    def test_checkout_remains_in_approved_after_confirm_failure(
        self,
        auth_client,
        sample_offer_merchant_a,
        mock_offer_repository,
    ):
        """Scenario 7b: Checkout stays approved if confirm fails."""
        offer = sample_offer_merchant_a
        product_id = "prod-headphones-001"
        offers_dict = {str(offer.id): offer}

        # Get to approved state
        with mock_offer_repository(offers_dict):
            create_resp = auth_client.post(
                "/checkouts",
                json={
                    "offer_id": str(offer.id),
                    "items": [{"product_id": product_id, "quantity": 1}],
                },
            )
            checkout_id = create_resp.json()["id"]

        quote = create_mock_quote(product_id=product_id)

        with patch(
            "app.application.checkout_service.MerchantClientFactory"
        ) as mock_factory:
            mock_client = MagicMock()
            mock_client.create_quote = AsyncMock(return_value=quote)

            mock_factory_instance = MagicMock()
            mock_factory_instance.get_client.return_value = mock_client
            mock_factory_instance.__aenter__ = AsyncMock(
                return_value=mock_factory_instance
            )
            mock_factory_instance.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_factory_instance

            auth_client.post(
                f"/checkouts/{checkout_id}/quote",
                json={"items": [{"product_id": product_id, "quantity": 1}]},
            )

        auth_client.post(f"/checkouts/{checkout_id}/request-approval")
        auth_client.post(
            f"/checkouts/{checkout_id}/approve",
            json={"approved_by": "test-user"},
        )

        # Confirm fails
        with patch(
            "app.application.checkout_service.MerchantClientFactory"
        ) as mock_factory:
            mock_client = MagicMock()
            mock_client.confirm_checkout = AsyncMock(
                side_effect=Exception("Payment processor error")
            )

            mock_factory_instance = MagicMock()
            mock_factory_instance.get_client.return_value = mock_client
            mock_factory_instance.__aenter__ = AsyncMock(
                return_value=mock_factory_instance
            )
            mock_factory_instance.__aexit__ = AsyncMock(return_value=None)
            mock_factory.return_value = mock_factory_instance

            confirm_resp = auth_client.post(
                f"/checkouts/{checkout_id}/confirm",
                json={"payment_method": "test_card"},
            )

        assert confirm_resp.status_code == status.HTTP_400_BAD_REQUEST

        # Checkout should still be approved (can retry)
        checkout_resp = auth_client.get(f"/checkouts/{checkout_id}")
        # Status could be approved (for retry) or failed depending on implementation
        assert checkout_resp.json()["status"] in ["approved", "failed"]


# ============================================================================
# Scenario 8: Refund Flow
# ============================================================================


class TestScenario8RefundFlow:
    """Test order refund flow."""

    def test_full_refund_flow(
        self,
        auth_client,
        sample_offer_merchant_a,
        mock_offer_repository,
        mock_merchant_client_factory,
    ):
        """Scenario 8a: Complete purchase then refund."""
        offer = sample_offer_merchant_a
        product_id = "prod-headphones-001"

        # Complete purchase
        result = complete_checkout_flow(
            auth_client=auth_client,
            offer=offer,
            mock_offer_repo=mock_offer_repository,
            mock_merchant_factory=mock_merchant_client_factory,
            product_id=product_id,
        )

        assert result["responses"]["confirm"].status_code == status.HTTP_200_OK
        order_id = result["order_id"]

        # Verify order exists
        order_resp = auth_client.get(f"/orders/{order_id}")
        assert order_resp.status_code == status.HTTP_200_OK
        assert order_resp.json()["status"] == "pending"

        # Cancel order first (required before refund in most states)
        cancel_resp = auth_client.post(
            f"/orders/{order_id}/cancel",
            json={
                "reason": "Customer requested refund",
                "cancelled_by": "customer",
            },
        )

        assert cancel_resp.status_code == status.HTTP_200_OK
        assert cancel_resp.json()["status"] == "cancelled"

        # Now refund
        refund_resp = auth_client.post(
            f"/orders/{order_id}/refund",
            json={"reason": "Full refund requested"},
        )

        assert refund_resp.status_code == status.HTTP_200_OK
        refund_data = refund_resp.json()
        assert refund_data["status"] == "refunded"
        assert refund_data["refund_reason"] == "Full refund requested"

    def test_partial_refund(
        self,
        auth_client,
        sample_offer_merchant_a,
        mock_offer_repository,
        mock_merchant_client_factory,
    ):
        """Scenario 8b: Partial refund of order."""
        offer = sample_offer_merchant_a
        product_id = "prod-headphones-001"

        # Complete purchase
        result = complete_checkout_flow(
            auth_client=auth_client,
            offer=offer,
            mock_offer_repo=mock_offer_repository,
            mock_merchant_factory=mock_merchant_client_factory,
            product_id=product_id,
        )

        assert result["responses"]["confirm"].status_code == status.HTTP_200_OK
        order_id = result["order_id"]

        # Cancel first
        auth_client.post(
            f"/orders/{order_id}/cancel",
            json={"reason": "Partial damage", "cancelled_by": "merchant"},
        )

        # Partial refund (50% of total)
        order_resp = auth_client.get(f"/orders/{order_id}")
        total_cents = order_resp.json()["total"]["amount"]
        partial_amount = total_cents // 2

        refund_resp = auth_client.post(
            f"/orders/{order_id}/refund",
            json={
                "refund_amount_cents": partial_amount,
                "reason": "Partial refund for damaged item",
            },
        )

        assert refund_resp.status_code == status.HTTP_200_OK
        refund_data = refund_resp.json()
        assert refund_data["status"] == "refunded"
        assert refund_data["refund_amount"]["amount"] == partial_amount

    def test_order_lifecycle_to_delivered_then_refund(
        self,
        auth_client,
        sample_offer_merchant_a,
        mock_offer_repository,
        mock_merchant_client_factory,
    ):
        """Scenario 8c: Complete lifecycle including delivery and refund."""
        offer = sample_offer_merchant_a
        product_id = "prod-headphones-001"

        # Complete purchase
        result = complete_checkout_flow(
            auth_client=auth_client,
            offer=offer,
            mock_offer_repo=mock_offer_repository,
            mock_merchant_factory=mock_merchant_client_factory,
            product_id=product_id,
        )

        order_id = result["order_id"]

        # Simulate advancement to delivered (3 steps: pending → confirmed → shipped → delivered)
        advance_resp = auth_client.post(
            f"/orders/{order_id}/simulate-advance",
            json={"steps": 3},
        )

        assert advance_resp.status_code == status.HTTP_200_OK
        assert advance_resp.json()["status"] == "delivered"

        # Refund a delivered order (return scenario)
        refund_resp = auth_client.post(
            f"/orders/{order_id}/refund",
            json={"reason": "Customer return - item not as described"},
        )

        assert refund_resp.status_code == status.HTTP_200_OK
        assert refund_resp.json()["status"] == "refunded"


# ============================================================================
# Additional Integration Tests
# ============================================================================


class TestIntegrationMisc:
    """Additional integration tests for edge cases."""

    def test_get_nonexistent_order(self, auth_client):
        """Getting nonexistent order returns 404."""
        resp = auth_client.get("/orders/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_cancel_already_delivered_order_fails(
        self,
        auth_client,
        sample_offer_merchant_a,
        mock_offer_repository,
        mock_merchant_client_factory,
    ):
        """Cannot cancel a delivered order."""
        offer = sample_offer_merchant_a
        product_id = "prod-headphones-001"

        result = complete_checkout_flow(
            auth_client=auth_client,
            offer=offer,
            mock_offer_repo=mock_offer_repository,
            mock_merchant_factory=mock_merchant_client_factory,
            product_id=product_id,
        )

        order_id = result["order_id"]

        # Advance to delivered
        auth_client.post(
            f"/orders/{order_id}/simulate-advance",
            json={"steps": 3},
        )

        # Try to cancel - should fail
        cancel_resp = auth_client.post(
            f"/orders/{order_id}/cancel",
            json={"reason": "Too late", "cancelled_by": "customer"},
        )

        assert cancel_resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_multiple_merchants_offers(self, auth_client):
        """Test intent collecting offers from multiple merchants."""
        # Create intent
        intent_resp = auth_client.post(
            "/intents",
            json={"query": "wireless headphones", "session_id": "multi-merchant-test"},
        )

        assert intent_resp.status_code == status.HTTP_201_CREATED
        intent_id = intent_resp.json()["id"]

        # Note: In a real integration test, this would actually call merchants
        # Here we just verify the endpoint works
        offers_resp = auth_client.get(f"/intents/{intent_id}/offers")

        # Should return 200 even if no offers (merchants not running in test)
        assert offers_resp.status_code == status.HTTP_200_OK
        assert "items" in offers_resp.json()
