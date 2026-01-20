"""Tests for checkout store."""

from datetime import datetime, timedelta, timezone

import pytest

from app.checkout import CheckoutStore
from app.products import ProductStore
from app.schemas import CheckoutItemRequest, CheckoutStatus


class TestCheckoutStore:
    """Tests for CheckoutStore class."""

    def test_create_quote_success(self, checkout_store: CheckoutStore):
        """Test successful quote creation."""
        # Get a product ID
        product_id = list(checkout_store.product_store._products.keys())[0]

        items = [CheckoutItemRequest(product_id=product_id, quantity=2)]
        session = checkout_store.create_quote(items)

        assert session is not None
        assert session.status == CheckoutStatus.QUOTED
        assert len(session.items) == 1
        assert session.items[0].quantity == 2
        assert session.total > 0
        assert session.receipt_hash is not None

    def test_create_quote_multiple_items(self, checkout_store: CheckoutStore):
        """Test quote with multiple items."""
        product_ids = list(checkout_store.product_store._products.keys())[:3]

        items = [
            CheckoutItemRequest(product_id=pid, quantity=1)
            for pid in product_ids
        ]
        session = checkout_store.create_quote(items)

        assert len(session.items) == 3
        assert session.subtotal == sum(item.line_total for item in session.items)

    def test_create_quote_with_customer_email(self, checkout_store: CheckoutStore):
        """Test quote with customer email."""
        product_id = list(checkout_store.product_store._products.keys())[0]

        items = [CheckoutItemRequest(product_id=product_id, quantity=1)]
        session = checkout_store.create_quote(
            items, customer_email="test@example.com"
        )

        assert session.customer_email == "test@example.com"

    def test_create_quote_idempotency(self, checkout_store: CheckoutStore):
        """Test idempotent quote creation."""
        product_id = list(checkout_store.product_store._products.keys())[0]

        items = [CheckoutItemRequest(product_id=product_id, quantity=1)]
        session1 = checkout_store.create_quote(
            items, idempotency_key="test-key-123"
        )
        session2 = checkout_store.create_quote(
            items, idempotency_key="test-key-123"
        )

        assert session1.id == session2.id

    def test_create_quote_product_not_found(self, checkout_store: CheckoutStore):
        """Test quote with non-existent product."""
        items = [CheckoutItemRequest(product_id="non-existent", quantity=1)]

        with pytest.raises(ValueError, match="Product not found"):
            checkout_store.create_quote(items)

    def test_create_quote_calculates_tax(self, checkout_store: CheckoutStore):
        """Test that tax is calculated correctly."""
        product_id = list(checkout_store.product_store._products.keys())[0]

        items = [CheckoutItemRequest(product_id=product_id, quantity=1)]
        session = checkout_store.create_quote(items)

        expected_tax = int(session.subtotal * 0.08)
        assert session.tax == expected_tax

    def test_create_quote_shipping_calculation(self, checkout_store: CheckoutStore):
        """Test shipping calculation."""
        product_id = list(checkout_store.product_store._products.keys())[0]
        product = checkout_store.product_store._products[product_id]

        # Test with low subtotal (should have shipping)
        if product.base_price < 5000:
            items = [CheckoutItemRequest(product_id=product_id, quantity=1)]
            session = checkout_store.create_quote(items)
            if session.subtotal < 5000:
                assert session.shipping == 999  # $9.99 flat

    def test_create_quote_free_shipping_threshold(
        self, checkout_store: CheckoutStore
    ):
        """Test free shipping over threshold."""
        # Find a product with high enough price or use multiple
        products = list(checkout_store.product_store._products.values())

        # Calculate quantity needed to exceed threshold
        product = products[0]
        quantity_needed = (5000 // product.base_price) + 1

        items = [
            CheckoutItemRequest(product_id=product.id, quantity=quantity_needed)
        ]
        session = checkout_store.create_quote(items)

        if session.subtotal >= 5000:
            assert session.shipping == 0

    def test_get_checkout(self, checkout_store: CheckoutStore):
        """Test getting checkout by ID."""
        product_id = list(checkout_store.product_store._products.keys())[0]

        items = [CheckoutItemRequest(product_id=product_id, quantity=1)]
        created = checkout_store.create_quote(items)

        retrieved = checkout_store.get_checkout(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id

    def test_get_checkout_not_found(self, checkout_store: CheckoutStore):
        """Test getting non-existent checkout."""
        result = checkout_store.get_checkout("non-existent")
        assert result is None

    def test_confirm_checkout_success(self, checkout_store: CheckoutStore):
        """Test successful checkout confirmation."""
        product_id = list(checkout_store.product_store._products.keys())[0]

        items = [CheckoutItemRequest(product_id=product_id, quantity=1)]
        session = checkout_store.create_quote(items)

        confirmed = checkout_store.confirm_checkout(session.id)

        assert confirmed.status == CheckoutStatus.CONFIRMED
        assert confirmed.merchant_order_id is not None
        assert confirmed.merchant_order_id.startswith("ORD-")

    def test_confirm_checkout_idempotent(self, checkout_store: CheckoutStore):
        """Test that confirmation is idempotent."""
        product_id = list(checkout_store.product_store._products.keys())[0]

        items = [CheckoutItemRequest(product_id=product_id, quantity=1)]
        session = checkout_store.create_quote(items)

        confirmed1 = checkout_store.confirm_checkout(session.id)
        confirmed2 = checkout_store.confirm_checkout(session.id)

        assert confirmed1.merchant_order_id == confirmed2.merchant_order_id

    def test_confirm_checkout_not_found(self, checkout_store: CheckoutStore):
        """Test confirming non-existent checkout."""
        with pytest.raises(ValueError, match="Checkout not found"):
            checkout_store.confirm_checkout("non-existent")

    def test_fail_checkout(self, checkout_store: CheckoutStore):
        """Test marking checkout as failed."""
        product_id = list(checkout_store.product_store._products.keys())[0]

        items = [CheckoutItemRequest(product_id=product_id, quantity=1)]
        session = checkout_store.create_quote(items)

        failed = checkout_store.fail_checkout(session.id, "Test failure")

        assert failed.status == CheckoutStatus.FAILED
        assert failed.failure_reason == "Test failure"

    def test_to_schema(self, checkout_store: CheckoutStore):
        """Test conversion to schema."""
        product_id = list(checkout_store.product_store._products.keys())[0]

        items = [CheckoutItemRequest(product_id=product_id, quantity=1)]
        session = checkout_store.create_quote(items)

        schema = checkout_store.to_schema(session)

        assert schema.id == session.id
        assert schema.ucp_version == "1.0.0"
        assert len(schema.items) == 1


class TestCheckoutWithVariants:
    """Tests for checkout with product variants."""

    def test_create_quote_with_variant(self, checkout_store: CheckoutStore):
        """Test quote with product variant."""
        # Find a product with variants
        for product in checkout_store.product_store._products.values():
            if product.variants:
                variant_id = product.variants[0]["id"]
                items = [
                    CheckoutItemRequest(
                        product_id=product.id,
                        variant_id=variant_id,
                        quantity=1,
                    )
                ]
                session = checkout_store.create_quote(items)

                assert len(session.items) == 1
                assert session.items[0].variant_id == variant_id
                return

        pytest.skip("No products with variants found")
