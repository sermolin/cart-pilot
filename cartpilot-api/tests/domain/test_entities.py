"""Tests for domain entities."""

from datetime import datetime, timedelta, timezone

import pytest

from app.domain import (
    Address,
    Approval,
    ApprovalId,
    ApprovalStatus,
    Cart,
    CartId,
    CartItemId,
    CartStatus,
    CustomerInfo,
    MerchantId,
    Money,
    Order,
    OrderId,
    OrderStatus,
    ProductId,
    ProductRef,
)
from app.domain.exceptions import (
    ApprovalAlreadyResolvedError,
    CartEmptyError,
    CartItemNotFoundError,
    CartNotEditableError,
    InvalidQuantityError,
    InvalidStateTransitionError,
    OrderNotCancellableError,
)


# ============================================================================
# Test Fixtures
# ============================================================================


def make_product(
    product_id: str = "SKU-001",
    name: str = "Test Product",
    price: float = 29.99,
) -> ProductRef:
    """Create a test product reference."""
    return ProductRef(
        product_id=ProductId(product_id),
        merchant_id=MerchantId("merchant-a"),
        name=name,
        unit_price=Money.from_float(price),
    )


def make_customer() -> CustomerInfo:
    """Create a test customer."""
    return CustomerInfo(email="test@example.com", name="Test User")


def make_address() -> Address:
    """Create a test address."""
    return Address(
        line1="123 Main St",
        city="Austin",
        state="TX",
        postal_code="78701",
    )


# ============================================================================
# Cart Tests
# ============================================================================


class TestCartCreation:
    """Tests for cart creation."""

    def test_create_cart(self) -> None:
        """Cart can be created."""
        cart = Cart.create(MerchantId("merchant-a"))
        assert cart.id is not None
        assert cart.status == CartStatus.DRAFT
        assert cart.is_empty
        assert str(cart.merchant_id) == "merchant-a"

    def test_create_cart_with_session(self) -> None:
        """Cart can be created with session ID."""
        cart = Cart.create(MerchantId("merchant-a"), session_id="session-123")
        assert cart.session_id == "session-123"

    def test_create_cart_emits_event(self) -> None:
        """Creating cart emits CartCreated event."""
        cart = Cart.create(MerchantId("merchant-a"))
        events = cart.collect_events()
        assert len(events) == 1
        assert events[0].event_type == "cart.created"


class TestCartItems:
    """Tests for cart item operations."""

    def test_add_item(self) -> None:
        """Item can be added to cart."""
        cart = Cart.create(MerchantId("merchant-a"))
        product = make_product()
        
        item = cart.add_item(product, quantity=2)
        
        assert item.quantity == 2
        assert cart.item_count == 2
        assert not cart.is_empty

    def test_add_same_product_increases_quantity(self) -> None:
        """Adding same product increases quantity."""
        cart = Cart.create(MerchantId("merchant-a"))
        product = make_product()
        
        cart.add_item(product, quantity=2)
        cart.add_item(product, quantity=3)
        
        assert len(cart.items) == 1
        assert cart.items[0].quantity == 5
        assert cart.item_count == 5

    def test_add_different_products(self) -> None:
        """Different products are added as separate items."""
        cart = Cart.create(MerchantId("merchant-a"))
        
        cart.add_item(make_product("SKU-001", "Product 1", 10.00), quantity=1)
        cart.add_item(make_product("SKU-002", "Product 2", 20.00), quantity=2)
        
        assert len(cart.items) == 2
        assert cart.item_count == 3

    def test_add_item_invalid_quantity_raises(self) -> None:
        """Adding item with zero/negative quantity raises error."""
        cart = Cart.create(MerchantId("merchant-a"))
        
        with pytest.raises(InvalidQuantityError):
            cart.add_item(make_product(), quantity=0)
        
        with pytest.raises(InvalidQuantityError):
            cart.add_item(make_product(), quantity=-1)

    def test_remove_item(self) -> None:
        """Item can be removed from cart."""
        cart = Cart.create(MerchantId("merchant-a"))
        item = cart.add_item(make_product())
        
        removed = cart.remove_item(item.id)
        
        assert removed.id == item.id
        assert cart.is_empty

    def test_remove_nonexistent_item_raises(self) -> None:
        """Removing nonexistent item raises error."""
        cart = Cart.create(MerchantId("merchant-a"))
        
        with pytest.raises(CartItemNotFoundError):
            cart.remove_item(CartItemId.generate())

    def test_update_item_quantity(self) -> None:
        """Item quantity can be updated."""
        cart = Cart.create(MerchantId("merchant-a"))
        item = cart.add_item(make_product(), quantity=2)
        
        cart.update_item_quantity(item.id, quantity=5)
        
        assert item.quantity == 5

    def test_clear_cart(self) -> None:
        """Cart can be cleared."""
        cart = Cart.create(MerchantId("merchant-a"))
        cart.add_item(make_product("SKU-001"))
        cart.add_item(make_product("SKU-002"))
        
        count = cart.clear()
        
        assert count == 2
        assert cart.is_empty


class TestCartTotal:
    """Tests for cart total calculation."""

    def test_empty_cart_total_is_zero(self) -> None:
        """Empty cart has zero total."""
        cart = Cart.create(MerchantId("merchant-a"))
        assert cart.total.is_zero()

    def test_cart_total_single_item(self) -> None:
        """Cart total with single item."""
        cart = Cart.create(MerchantId("merchant-a"))
        cart.add_item(make_product(price=29.99), quantity=2)
        
        assert cart.total.amount_cents == 5998  # 29.99 * 2

    def test_cart_total_multiple_items(self) -> None:
        """Cart total with multiple items."""
        cart = Cart.create(MerchantId("merchant-a"))
        cart.add_item(make_product("SKU-001", price=10.00), quantity=2)
        cart.add_item(make_product("SKU-002", price=15.00), quantity=1)
        
        assert cart.total.amount_cents == 3500  # 10*2 + 15*1


class TestCartStateTransitions:
    """Tests for cart state transitions."""

    def test_start_checkout(self) -> None:
        """Cart can start checkout."""
        cart = Cart.create(MerchantId("merchant-a"))
        cart.add_item(make_product())
        
        cart.start_checkout(make_customer(), make_address())
        
        assert cart.status == CartStatus.CHECKOUT
        assert cart.customer is not None
        assert cart.shipping_address is not None

    def test_checkout_empty_cart_raises(self) -> None:
        """Checkout with empty cart raises error."""
        cart = Cart.create(MerchantId("merchant-a"))
        
        with pytest.raises(CartEmptyError):
            cart.start_checkout(make_customer(), make_address())

    def test_cannot_edit_after_submit(self) -> None:
        """Cannot edit cart after submission."""
        cart = Cart.create(MerchantId("merchant-a"))
        cart.add_item(make_product())
        cart.start_checkout(make_customer(), make_address())
        cart.request_approval()
        cart.submit(OrderId.generate())
        
        with pytest.raises(CartNotEditableError):
            cart.add_item(make_product())

    def test_complete_cart(self) -> None:
        """Cart can be completed."""
        cart = Cart.create(MerchantId("merchant-a"))
        cart.add_item(make_product())
        cart.start_checkout(make_customer(), make_address())
        cart.request_approval()
        cart.submit(OrderId.generate())
        
        cart.complete()
        
        assert cart.status == CartStatus.COMPLETED
        assert cart.status.is_terminal()

    def test_abandon_cart(self) -> None:
        """Cart can be abandoned."""
        cart = Cart.create(MerchantId("merchant-a"))
        
        cart.abandon(reason="timeout")
        
        assert cart.status == CartStatus.ABANDONED
        assert cart.failure_reason == "timeout"

    def test_fail_and_retry(self) -> None:
        """Failed cart can be reset to draft."""
        cart = Cart.create(MerchantId("merchant-a"))
        cart.add_item(make_product())
        cart.start_checkout(make_customer(), make_address())
        cart.request_approval()
        cart.submit(OrderId.generate())
        cart.fail("PAYMENT_FAILED", "Card declined")
        
        cart.reset_to_draft()
        
        assert cart.status == CartStatus.DRAFT
        assert cart.failure_reason is None


class TestCartEvents:
    """Tests for cart domain events."""

    def test_add_item_emits_event(self) -> None:
        """Adding item emits CartItemAdded event."""
        cart = Cart.create(MerchantId("merchant-a"))
        cart.collect_events()  # Clear creation event
        
        cart.add_item(make_product())
        
        events = cart.collect_events()
        assert len(events) == 1
        assert events[0].event_type == "cart.item_added"

    def test_checkout_emits_event(self) -> None:
        """Starting checkout emits CartCheckoutStarted event."""
        cart = Cart.create(MerchantId("merchant-a"))
        cart.add_item(make_product())
        cart.collect_events()
        
        cart.start_checkout(make_customer(), make_address())
        
        events = cart.collect_events()
        assert len(events) == 1
        assert events[0].event_type == "cart.checkout_started"


# ============================================================================
# Order Tests
# ============================================================================


class TestOrderCreation:
    """Tests for order creation."""

    def test_create_order_from_cart(self) -> None:
        """Order can be created from cart."""
        cart = Cart.create(MerchantId("merchant-a"))
        cart.add_item(make_product(price=50.00), quantity=2)
        cart.start_checkout(make_customer(), make_address())
        
        order = Order.create_from_cart(cart)
        
        assert order.status == OrderStatus.PENDING
        assert order.total.amount_cents == 10000
        assert order.item_count == 2
        assert len(order.items) == 1

    def test_order_snapshots_cart_data(self) -> None:
        """Order snapshots cart data."""
        cart = Cart.create(MerchantId("merchant-a"))
        cart.add_item(make_product(name="Widget", price=25.00))
        cart.start_checkout(make_customer(), make_address())
        
        order = Order.create_from_cart(cart)
        
        assert order.items[0].product_name == "Widget"
        assert order.customer.email == "test@example.com"

    def test_create_order_without_customer_raises(self) -> None:
        """Creating order without customer raises error."""
        cart = Cart.create(MerchantId("merchant-a"))
        cart.add_item(make_product())
        
        with pytest.raises(ValueError, match="customer"):
            Order.create_from_cart(cart)


class TestOrderStateTransitions:
    """Tests for order state transitions."""

    def make_order(self) -> Order:
        """Create a test order."""
        cart = Cart.create(MerchantId("merchant-a"))
        cart.add_item(make_product())
        cart.start_checkout(make_customer(), make_address())
        return Order.create_from_cart(cart)

    def test_confirm_order(self) -> None:
        """Order can be confirmed."""
        order = self.make_order()
        
        order.confirm("MERCH-12345")
        
        assert order.status == OrderStatus.CONFIRMED
        assert order.merchant_order_id == "MERCH-12345"

    def test_ship_order(self) -> None:
        """Order can be shipped."""
        order = self.make_order()
        order.confirm("MERCH-12345")
        
        order.ship(tracking_number="1Z999", carrier="UPS")
        
        assert order.status == OrderStatus.SHIPPED
        assert order.tracking_number == "1Z999"
        assert order.carrier == "UPS"

    def test_deliver_order(self) -> None:
        """Order can be delivered."""
        order = self.make_order()
        order.confirm("MERCH-12345")
        order.ship()
        
        order.deliver()
        
        assert order.status == OrderStatus.DELIVERED
        assert order.delivered_at is not None

    def test_cancel_pending_order(self) -> None:
        """Pending order can be cancelled."""
        order = self.make_order()
        
        order.cancel("Customer request", cancelled_by="customer")
        
        assert order.status == OrderStatus.CANCELLED
        assert order.cancelled_reason == "Customer request"

    def test_cancel_delivered_order_raises(self) -> None:
        """Delivered order cannot be cancelled."""
        order = self.make_order()
        order.confirm("MERCH-12345")
        order.ship()
        order.deliver()
        
        with pytest.raises(OrderNotCancellableError):
            order.cancel("Too late")

    def test_refund_order(self) -> None:
        """Order can be refunded."""
        order = self.make_order()
        order.confirm("MERCH-12345")
        order.ship()
        order.deliver()
        
        order.refund(reason="Customer complaint")
        
        assert order.status == OrderStatus.REFUNDED
        assert order.refund_amount == order.total


# ============================================================================
# Approval Tests
# ============================================================================


class TestApprovalCreation:
    """Tests for approval creation."""

    def test_create_approval(self) -> None:
        """Approval can be created."""
        cart_id = CartId.generate()
        
        approval = Approval.create(
            cart_id=cart_id,
            amount=Money.from_float(500.00),
            reason="Amount exceeds limit",
        )
        
        assert approval.status == ApprovalStatus.PENDING
        assert approval.is_actionable

    def test_approval_has_expiration(self) -> None:
        """Approval has expiration time."""
        approval = Approval.create(
            cart_id=CartId.generate(),
            amount=Money.from_float(100.00),
            reason="Test",
            ttl_hours=2,
        )
        
        assert approval.expires_at > datetime.now(timezone.utc)
        assert approval.time_remaining.total_seconds() > 0


class TestApprovalStateTransitions:
    """Tests for approval state transitions."""

    def make_approval(self) -> Approval:
        """Create a test approval."""
        return Approval.create(
            cart_id=CartId.generate(),
            amount=Money.from_float(100.00),
            reason="Test approval",
        )

    def test_approve(self) -> None:
        """Approval can be approved."""
        approval = self.make_approval()
        
        approval.approve(approved_by="user@example.com")
        
        assert approval.status == ApprovalStatus.APPROVED
        assert approval.resolved_by == "user@example.com"
        assert approval.resolved_at is not None

    def test_reject(self) -> None:
        """Approval can be rejected."""
        approval = self.make_approval()
        
        approval.reject(rejected_by="admin@example.com", reason="Budget exceeded")
        
        assert approval.status == ApprovalStatus.REJECTED
        assert approval.resolution_reason == "Budget exceeded"

    def test_cannot_approve_twice(self) -> None:
        """Cannot approve already approved request."""
        approval = self.make_approval()
        approval.approve("user1")
        
        with pytest.raises(ApprovalAlreadyResolvedError):
            approval.approve("user2")

    def test_cannot_reject_after_approval(self) -> None:
        """Cannot reject after approval."""
        approval = self.make_approval()
        approval.approve("user1")
        
        with pytest.raises(ApprovalAlreadyResolvedError):
            approval.reject("user2", "Changed mind")


class TestApprovalEvents:
    """Tests for approval domain events."""

    def test_creation_emits_event(self) -> None:
        """Creating approval emits ApprovalRequested event."""
        approval = Approval.create(
            cart_id=CartId.generate(),
            amount=Money.from_float(100.00),
            reason="Test",
        )
        
        events = approval.collect_events()
        assert len(events) == 1
        assert events[0].event_type == "approval.requested"

    def test_approve_emits_event(self) -> None:
        """Approving emits ApprovalGranted event."""
        approval = Approval.create(
            cart_id=CartId.generate(),
            amount=Money.from_float(100.00),
            reason="Test",
        )
        approval.collect_events()
        
        approval.approve("user")
        
        events = approval.collect_events()
        assert len(events) == 1
        assert events[0].event_type == "approval.granted"
