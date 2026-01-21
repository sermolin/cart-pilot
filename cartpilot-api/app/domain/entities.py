"""Domain entities for the CartPilot system.

Entities are domain objects with identity that persists across state changes.
This module contains the core aggregates: Cart, Order, and Approval.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.domain.base import AggregateRoot, Entity
from app.domain.events import (
    ApprovalExpired,
    ApprovalGranted,
    ApprovalRejected,
    ApprovalRequested,
    CartAbandoned,
    CartCheckoutStarted,
    CartCompleted,
    CartCreated,
    CartFailed,
    CartItemAdded,
    CartItemQuantityUpdated,
    CartItemRemoved,
    CartSubmitted,
    CheckoutApprovalRequested,
    CheckoutApproved,
    CheckoutCancelled,
    CheckoutConfirmed,
    CheckoutCreated,
    CheckoutFailed,
    CheckoutQuoted,
    CheckoutReapprovalRequired,
    IntentCreated,
    OffersCollected,
    OrderCancelled,
    OrderConfirmed,
    OrderCreated,
    OrderDelivered,
    OrderRefunded,
    OrderShipped,
)
from app.domain.exceptions import (
    ApprovalAlreadyResolvedError,
    ApprovalExpiredError,
    CartEmptyError,
    CartItemNotFoundError,
    CartNotEditableError,
    CheckoutAlreadyConfirmedError,
    CheckoutExpiredError,
    CheckoutNotApprovedError,
    InvalidQuantityError,
    OrderNotCancellableError,
    ReapprovalRequiredError,
)
from app.domain.state_machines import (
    ApprovalStatus,
    CartStatus,
    CheckoutStatus,
    OrderStatus,
    validate_approval_transition,
    validate_cart_transition,
    validate_checkout_transition,
    validate_order_transition,
)
from app.domain.value_objects import (
    Address,
    ApprovalId,
    CartId,
    CartItemId,
    CheckoutId,
    CustomerInfo,
    FrozenReceipt,
    FrozenReceiptItem,
    IntentId,
    MerchantId,
    Money,
    OfferId,
    OrderId,
    ProductId,
    ProductRef,
)


# ============================================================================
# Cart Item Entity
# ============================================================================


@dataclass
class CartItem(Entity[CartItemId]):
    """An item in a shopping cart.

    CartItem is an entity (not an aggregate root) that belongs to
    the Cart aggregate. It maintains its own identity within the cart.

    Attributes:
        id: Unique identifier for this cart item.
        product: Reference to the product.
        quantity: Number of units.
        added_at: Timestamp when item was added.
    """

    id: CartItemId
    product: ProductRef
    quantity: int
    added_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        """Validate cart item constraints."""
        if self.quantity <= 0:
            raise InvalidQuantityError(self.quantity)

    @property
    def unit_price(self) -> Money:
        """Get unit price from product reference.

        Returns:
            Unit price of the product.
        """
        return self.product.unit_price

    @property
    def line_total(self) -> Money:
        """Calculate total price for this line item.

        Returns:
            Unit price multiplied by quantity.
        """
        return self.product.unit_price * self.quantity

    def update_quantity(self, new_quantity: int) -> int:
        """Update item quantity.

        Args:
            new_quantity: New quantity value.

        Returns:
            Previous quantity.

        Raises:
            InvalidQuantityError: If quantity is not positive.
        """
        if new_quantity <= 0:
            raise InvalidQuantityError(new_quantity)
        old_quantity = self.quantity
        self.quantity = new_quantity
        return old_quantity


# ============================================================================
# Cart Aggregate Root
# ============================================================================


@dataclass(kw_only=True)
class Cart(AggregateRoot[CartId]):
    """Shopping cart aggregate root.

    The Cart is the primary aggregate for managing shopping sessions.
    It maintains consistency of cart items and enforces business rules
    about cart operations based on its current state.

    Attributes:
        id: Unique cart identifier.
        merchant_id: Merchant this cart belongs to.
        status: Current cart status (state machine).
        items: List of cart items.
        session_id: Optional session identifier for the agent.
        customer: Customer information (set during checkout).
        shipping_address: Shipping address (set during checkout).
        billing_address: Billing address (set during checkout).
        order_id: Associated order ID (after submission).
        notes: Optional notes for the order.
    """

    id: CartId
    merchant_id: MerchantId
    status: CartStatus = CartStatus.DRAFT
    items: list[CartItem] = field(default_factory=list)
    session_id: str | None = None
    customer: CustomerInfo | None = None
    shipping_address: Address | None = None
    billing_address: Address | None = None
    order_id: OrderId | None = None
    notes: str | None = None
    failure_reason: str | None = None

    @classmethod
    def create(
        cls,
        merchant_id: MerchantId,
        session_id: str | None = None,
        cart_id: CartId | None = None,
    ) -> "Cart":
        """Create a new cart.

        Factory method that creates a cart and records the creation event.

        Args:
            merchant_id: Merchant this cart belongs to.
            session_id: Optional session identifier.
            cart_id: Optional pre-generated cart ID.

        Returns:
            New Cart instance.
        """
        cart = cls(
            id=cart_id or CartId.generate(),
            merchant_id=merchant_id,
            session_id=session_id,
        )
        cart._record_event(
            CartCreated(
                aggregate_id=str(cart.id),
                aggregate_type="Cart",
                cart_id=str(cart.id),
                merchant_id=str(merchant_id),
                session_id=session_id,
            )
        )
        return cart

    # -------------------------------------------------------------------------
    # Query Methods
    # -------------------------------------------------------------------------

    @property
    def total(self) -> Money:
        """Calculate total cart value.

        Returns:
            Sum of all line item totals.
        """
        if not self.items:
            return Money.zero()
        currency = self.items[0].unit_price.currency
        return Money(
            amount_cents=sum(item.line_total.amount_cents for item in self.items),
            currency=currency,
        )

    @property
    def item_count(self) -> int:
        """Get total number of items (sum of quantities).

        Returns:
            Total quantity across all items.
        """
        return sum(item.quantity for item in self.items)

    @property
    def is_empty(self) -> bool:
        """Check if cart has no items.

        Returns:
            True if cart has no items.
        """
        return len(self.items) == 0

    def get_item(self, item_id: CartItemId) -> CartItem | None:
        """Find item by ID.

        Args:
            item_id: Cart item identifier.

        Returns:
            CartItem if found, None otherwise.
        """
        for item in self.items:
            if item.id == item_id:
                return item
        return None

    def get_item_by_product(self, product_id: str) -> CartItem | None:
        """Find item by product ID.

        Args:
            product_id: Product identifier.

        Returns:
            CartItem if found, None otherwise.
        """
        for item in self.items:
            if str(item.product.product_id) == product_id:
                return item
        return None

    # -------------------------------------------------------------------------
    # Cart Item Operations
    # -------------------------------------------------------------------------

    def add_item(self, product: ProductRef, quantity: int = 1) -> CartItem:
        """Add an item to the cart.

        If the product already exists in the cart, its quantity is increased.
        Otherwise, a new cart item is created.

        Args:
            product: Product reference to add.
            quantity: Number of units to add.

        Returns:
            The new or updated CartItem.

        Raises:
            CartNotEditableError: If cart is not in editable state.
            InvalidQuantityError: If quantity is not positive.
        """
        if not self.status.is_editable():
            raise CartNotEditableError(str(self.id), self.status.value)

        if quantity <= 0:
            raise InvalidQuantityError(quantity)

        # Check if product already in cart
        existing_item = self.get_item_by_product(str(product.product_id))
        if existing_item:
            old_qty = existing_item.quantity
            existing_item.update_quantity(existing_item.quantity + quantity)
            self._touch()
            self._record_event(
                CartItemQuantityUpdated(
                    aggregate_id=str(self.id),
                    aggregate_type="Cart",
                    cart_id=str(self.id),
                    item_id=str(existing_item.id),
                    old_quantity=old_qty,
                    new_quantity=existing_item.quantity,
                )
            )
            return existing_item

        # Create new cart item
        item = CartItem(
            id=CartItemId.generate(),
            product=product,
            quantity=quantity,
        )
        self.items.append(item)
        self._touch()
        self._record_event(
            CartItemAdded(
                aggregate_id=str(self.id),
                aggregate_type="Cart",
                cart_id=str(self.id),
                item_id=str(item.id),
                product_id=str(product.product_id),
                product_name=product.name,
                quantity=quantity,
                unit_price_cents=product.unit_price.amount_cents,
                currency=product.unit_price.currency,
            )
        )
        return item

    def remove_item(self, item_id: CartItemId) -> CartItem:
        """Remove an item from the cart.

        Args:
            item_id: ID of item to remove.

        Returns:
            The removed CartItem.

        Raises:
            CartNotEditableError: If cart is not in editable state.
            CartItemNotFoundError: If item is not in cart.
        """
        if not self.status.is_editable():
            raise CartNotEditableError(str(self.id), self.status.value)

        item = self.get_item(item_id)
        if not item:
            raise CartItemNotFoundError(str(self.id), str(item_id))

        self.items.remove(item)
        self._touch()
        self._record_event(
            CartItemRemoved(
                aggregate_id=str(self.id),
                aggregate_type="Cart",
                cart_id=str(self.id),
                item_id=str(item_id),
                product_id=str(item.product.product_id),
            )
        )
        return item

    def update_item_quantity(self, item_id: CartItemId, quantity: int) -> CartItem:
        """Update quantity of an item.

        Args:
            item_id: ID of item to update.
            quantity: New quantity.

        Returns:
            Updated CartItem.

        Raises:
            CartNotEditableError: If cart is not in editable state.
            CartItemNotFoundError: If item is not in cart.
            InvalidQuantityError: If quantity is not positive.
        """
        if not self.status.is_editable():
            raise CartNotEditableError(str(self.id), self.status.value)

        item = self.get_item(item_id)
        if not item:
            raise CartItemNotFoundError(str(self.id), str(item_id))

        old_quantity = item.update_quantity(quantity)
        self._touch()
        self._record_event(
            CartItemQuantityUpdated(
                aggregate_id=str(self.id),
                aggregate_type="Cart",
                cart_id=str(self.id),
                item_id=str(item_id),
                old_quantity=old_quantity,
                new_quantity=quantity,
            )
        )
        return item

    def clear(self) -> int:
        """Remove all items from cart.

        Returns:
            Number of items removed.

        Raises:
            CartNotEditableError: If cart is not in editable state.
        """
        if not self.status.is_editable():
            raise CartNotEditableError(str(self.id), self.status.value)

        count = len(self.items)
        for item in self.items.copy():
            self._record_event(
                CartItemRemoved(
                    aggregate_id=str(self.id),
                    aggregate_type="Cart",
                    cart_id=str(self.id),
                    item_id=str(item.id),
                    product_id=str(item.product.product_id),
                )
            )
        self.items.clear()
        self._touch()
        return count

    # -------------------------------------------------------------------------
    # State Transitions
    # -------------------------------------------------------------------------

    def start_checkout(
        self,
        customer: CustomerInfo,
        shipping_address: Address,
        billing_address: Address | None = None,
    ) -> None:
        """Start checkout process.

        Args:
            customer: Customer information.
            shipping_address: Shipping address.
            billing_address: Billing address (defaults to shipping).

        Raises:
            InvalidStateTransitionError: If not in valid state.
            CartEmptyError: If cart is empty.
        """
        validate_cart_transition(str(self.id), self.status, CartStatus.CHECKOUT)

        if self.is_empty:
            raise CartEmptyError(str(self.id))

        self.customer = customer
        self.shipping_address = shipping_address
        self.billing_address = billing_address or shipping_address
        self.status = CartStatus.CHECKOUT
        self._touch()
        self._record_event(
            CartCheckoutStarted(
                aggregate_id=str(self.id),
                aggregate_type="Cart",
                cart_id=str(self.id),
                total_cents=self.total.amount_cents,
                currency=self.total.currency,
                item_count=self.item_count,
            )
        )

    def request_approval(self) -> None:
        """Transition to pending approval state.

        Used when the cart total exceeds approval threshold
        or requires human review.

        Raises:
            InvalidStateTransitionError: If not in valid state.
        """
        validate_cart_transition(str(self.id), self.status, CartStatus.PENDING_APPROVAL)
        self.status = CartStatus.PENDING_APPROVAL
        self._touch()

    def reject(self, reason: str = "") -> None:
        """Reject cart (approval denied).

        Args:
            reason: Reason for rejection.

        Raises:
            InvalidStateTransitionError: If not in valid state.
        """
        validate_cart_transition(str(self.id), self.status, CartStatus.REJECTED)
        self.status = CartStatus.REJECTED
        self.failure_reason = reason
        self._touch()

    def submit(self, order_id: OrderId) -> None:
        """Submit cart for order processing.

        Args:
            order_id: ID of the created order.

        Raises:
            InvalidStateTransitionError: If not in valid state.
        """
        # Can submit from CHECKOUT (no approval needed) or PENDING_APPROVAL (after approval)
        validate_cart_transition(str(self.id), self.status, CartStatus.SUBMITTED)
        self.order_id = order_id
        self.status = CartStatus.SUBMITTED
        self._touch()
        self._record_event(
            CartSubmitted(
                aggregate_id=str(self.id),
                aggregate_type="Cart",
                cart_id=str(self.id),
                order_id=str(order_id),
                total_cents=self.total.amount_cents,
                currency=self.total.currency,
            )
        )

    def complete(self) -> None:
        """Mark cart as completed.

        Raises:
            InvalidStateTransitionError: If not in valid state.
        """
        validate_cart_transition(str(self.id), self.status, CartStatus.COMPLETED)
        self.status = CartStatus.COMPLETED
        self._touch()
        self._record_event(
            CartCompleted(
                aggregate_id=str(self.id),
                aggregate_type="Cart",
                cart_id=str(self.id),
                order_id=str(self.order_id) if self.order_id else "",
            )
        )

    def fail(self, error_code: str, error_message: str) -> None:
        """Mark cart as failed.

        Args:
            error_code: Error code for the failure.
            error_message: Detailed error message.

        Raises:
            InvalidStateTransitionError: If not in valid state.
        """
        validate_cart_transition(str(self.id), self.status, CartStatus.FAILED)
        self.status = CartStatus.FAILED
        self.failure_reason = f"{error_code}: {error_message}"
        self._touch()
        self._record_event(
            CartFailed(
                aggregate_id=str(self.id),
                aggregate_type="Cart",
                cart_id=str(self.id),
                error_code=error_code,
                error_message=error_message,
            )
        )

    def abandon(self, reason: str = "expired") -> None:
        """Abandon the cart.

        Args:
            reason: Reason for abandonment.

        Raises:
            InvalidStateTransitionError: If not in valid state.
        """
        validate_cart_transition(str(self.id), self.status, CartStatus.ABANDONED)
        self.status = CartStatus.ABANDONED
        self.failure_reason = reason
        self._touch()
        self._record_event(
            CartAbandoned(
                aggregate_id=str(self.id),
                aggregate_type="Cart",
                cart_id=str(self.id),
                reason=reason,
            )
        )

    def reset_to_draft(self) -> None:
        """Reset cart back to draft state for retry.

        Raises:
            InvalidStateTransitionError: If not in valid state.
        """
        validate_cart_transition(str(self.id), self.status, CartStatus.DRAFT)
        self.status = CartStatus.DRAFT
        self.failure_reason = None
        self._touch()


# ============================================================================
# Order Aggregate Root
# ============================================================================


@dataclass
class OrderItem:
    """A line item in an order.

    Order items are immutable snapshots of cart items at the time
    of order creation.

    Attributes:
        product_id: Product identifier.
        product_name: Product name at time of order.
        sku: SKU if available.
        quantity: Ordered quantity.
        unit_price: Price per unit at time of order.
    """

    product_id: str
    product_name: str
    quantity: int
    unit_price: Money
    sku: str | None = None

    @property
    def line_total(self) -> Money:
        """Calculate line total.

        Returns:
            Unit price multiplied by quantity.
        """
        return self.unit_price * self.quantity

    @classmethod
    def from_cart_item(cls, cart_item: CartItem) -> "OrderItem":
        """Create order item from cart item.

        Args:
            cart_item: Cart item to convert.

        Returns:
            OrderItem snapshot.
        """
        return cls(
            product_id=str(cart_item.product.product_id),
            product_name=cart_item.product.name,
            quantity=cart_item.quantity,
            unit_price=cart_item.unit_price,
            sku=cart_item.product.sku,
        )


@dataclass(kw_only=True)
class Order(AggregateRoot[OrderId]):
    """Order aggregate root.

    Orders are created from carts and represent a confirmed purchase.
    They track the order lifecycle from creation through fulfillment.

    Attributes:
        id: Unique order identifier.
        cart_id: Source cart identifier.
        merchant_id: Merchant fulfilling the order.
        status: Current order status.
        items: Order line items.
        customer: Customer information.
        shipping_address: Shipping address.
        billing_address: Billing address.
        total: Order total at time of creation.
        merchant_order_id: Merchant's order reference.
        tracking_number: Shipping tracking number.
        carrier: Shipping carrier.
        cancelled_reason: Reason if cancelled.
        refund_amount: Refund amount if refunded.
    """

    id: OrderId
    cart_id: CartId
    merchant_id: MerchantId
    customer: CustomerInfo
    shipping_address: Address
    billing_address: Address
    total: Money
    status: OrderStatus = OrderStatus.PENDING
    items: list[OrderItem] = field(default_factory=list)
    merchant_order_id: str | None = None
    tracking_number: str | None = None
    carrier: str | None = None
    cancelled_reason: str | None = None
    refund_amount: Money | None = None
    shipped_at: datetime | None = None
    delivered_at: datetime | None = None

    @classmethod
    def create_from_cart(cls, cart: Cart, order_id: OrderId | None = None) -> "Order":
        """Create an order from a cart.

        Factory method that creates an order with snapshots of cart data.

        Args:
            cart: Cart to create order from.
            order_id: Optional pre-generated order ID.

        Returns:
            New Order instance.

        Raises:
            ValueError: If cart is missing required data.
        """
        if not cart.customer:
            raise ValueError("Cart must have customer information")
        if not cart.shipping_address:
            raise ValueError("Cart must have shipping address")
        if not cart.billing_address:
            raise ValueError("Cart must have billing address")
        if cart.is_empty:
            raise ValueError("Cannot create order from empty cart")

        order = cls(
            id=order_id or OrderId.generate(),
            cart_id=cart.id,
            merchant_id=cart.merchant_id,
            customer=cart.customer,
            shipping_address=cart.shipping_address,
            billing_address=cart.billing_address,
            total=cart.total,
            items=[OrderItem.from_cart_item(item) for item in cart.items],
        )
        order._record_event(
            OrderCreated(
                aggregate_id=str(order.id),
                aggregate_type="Order",
                order_id=str(order.id),
                cart_id=str(cart.id),
                merchant_id=str(cart.merchant_id),
                total_cents=order.total.amount_cents,
                currency=order.total.currency,
                customer_email=cart.customer.email,
            )
        )
        return order

    # -------------------------------------------------------------------------
    # Query Methods
    # -------------------------------------------------------------------------

    @property
    def item_count(self) -> int:
        """Get total number of items.

        Returns:
            Sum of all item quantities.
        """
        return sum(item.quantity for item in self.items)

    # -------------------------------------------------------------------------
    # State Transitions
    # -------------------------------------------------------------------------

    def confirm(self, merchant_order_id: str) -> None:
        """Confirm the order.

        Args:
            merchant_order_id: Merchant's order reference.

        Raises:
            InvalidStateTransitionError: If not in valid state.
        """
        validate_order_transition(str(self.id), self.status, OrderStatus.CONFIRMED)
        self.merchant_order_id = merchant_order_id
        self.status = OrderStatus.CONFIRMED
        self._touch()
        self._record_event(
            OrderConfirmed(
                aggregate_id=str(self.id),
                aggregate_type="Order",
                order_id=str(self.id),
                merchant_order_id=merchant_order_id,
            )
        )

    def ship(self, tracking_number: str | None = None, carrier: str | None = None) -> None:
        """Mark order as shipped.

        Args:
            tracking_number: Tracking number if available.
            carrier: Shipping carrier name.

        Raises:
            InvalidStateTransitionError: If not in valid state.
        """
        validate_order_transition(str(self.id), self.status, OrderStatus.SHIPPED)
        self.tracking_number = tracking_number
        self.carrier = carrier
        self.shipped_at = datetime.now(timezone.utc)
        self.status = OrderStatus.SHIPPED
        self._touch()
        self._record_event(
            OrderShipped(
                aggregate_id=str(self.id),
                aggregate_type="Order",
                order_id=str(self.id),
                tracking_number=tracking_number,
                carrier=carrier,
                shipped_at=self.shipped_at,
            )
        )

    def deliver(self) -> None:
        """Mark order as delivered.

        Raises:
            InvalidStateTransitionError: If not in valid state.
        """
        validate_order_transition(str(self.id), self.status, OrderStatus.DELIVERED)
        self.delivered_at = datetime.now(timezone.utc)
        self.status = OrderStatus.DELIVERED
        self._touch()
        self._record_event(
            OrderDelivered(
                aggregate_id=str(self.id),
                aggregate_type="Order",
                order_id=str(self.id),
                delivered_at=self.delivered_at,
            )
        )

    def cancel(self, reason: str, cancelled_by: str = "system") -> None:
        """Cancel the order.

        Args:
            reason: Cancellation reason.
            cancelled_by: Who initiated cancellation (customer/merchant/system).

        Raises:
            OrderNotCancellableError: If order cannot be cancelled.
        """
        if not self.status.is_cancellable():
            raise OrderNotCancellableError(str(self.id), self.status.value)

        validate_order_transition(str(self.id), self.status, OrderStatus.CANCELLED)
        self.cancelled_reason = reason
        self.status = OrderStatus.CANCELLED
        self._touch()
        self._record_event(
            OrderCancelled(
                aggregate_id=str(self.id),
                aggregate_type="Order",
                order_id=str(self.id),
                reason=reason,
                cancelled_by=cancelled_by,
            )
        )

    def refund(self, amount: Money | None = None, reason: str = "") -> None:
        """Refund the order.

        Args:
            amount: Refund amount (defaults to full order total).
            reason: Refund reason.

        Raises:
            InvalidStateTransitionError: If not in valid state.
        """
        validate_order_transition(str(self.id), self.status, OrderStatus.REFUNDED)
        self.refund_amount = amount or self.total
        self.status = OrderStatus.REFUNDED
        self._touch()
        self._record_event(
            OrderRefunded(
                aggregate_id=str(self.id),
                aggregate_type="Order",
                order_id=str(self.id),
                refund_amount_cents=self.refund_amount.amount_cents,
                currency=self.refund_amount.currency,
                reason=reason,
            )
        )

    def mark_returned(self) -> None:
        """Mark order as returned.

        Raises:
            InvalidStateTransitionError: If not in valid state.
        """
        validate_order_transition(str(self.id), self.status, OrderStatus.RETURNED)
        self.status = OrderStatus.RETURNED
        self._touch()


# ============================================================================
# Approval Aggregate Root
# ============================================================================


@dataclass(kw_only=True)
class Approval(AggregateRoot[ApprovalId]):
    """Approval request aggregate root.

    Approvals are required for agent-initiated purchases that exceed
    thresholds or require human review. They have an expiration time
    to prevent stale approvals.

    Attributes:
        id: Unique approval identifier.
        cart_id: Cart requiring approval.
        amount: Amount requiring approval.
        status: Current approval status.
        reason: Reason approval is required.
        expires_at: When approval expires.
        resolved_by: Who resolved the approval.
        resolution_reason: Reason for resolution (if rejected).
        resolved_at: When approval was resolved.
    """

    id: ApprovalId
    cart_id: CartId
    amount: Money
    reason: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    expires_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=24)
    )
    resolved_by: str | None = None
    resolution_reason: str | None = None
    resolved_at: datetime | None = None

    @classmethod
    def create(
        cls,
        cart_id: CartId,
        amount: Money,
        reason: str,
        ttl_hours: int = 24,
        approval_id: ApprovalId | None = None,
    ) -> "Approval":
        """Create a new approval request.

        Args:
            cart_id: Cart requiring approval.
            amount: Amount requiring approval.
            reason: Why approval is required.
            ttl_hours: Hours until expiration.
            approval_id: Optional pre-generated ID.

        Returns:
            New Approval instance.
        """
        now = datetime.now(timezone.utc)
        approval = cls(
            id=approval_id or ApprovalId.generate(),
            cart_id=cart_id,
            amount=amount,
            reason=reason,
            expires_at=now + timedelta(hours=ttl_hours),
        )
        approval._record_event(
            ApprovalRequested(
                aggregate_id=str(approval.id),
                aggregate_type="Approval",
                approval_id=str(approval.id),
                cart_id=str(cart_id),
                amount_cents=amount.amount_cents,
                currency=amount.currency,
                reason=reason,
                expires_at=approval.expires_at,
            )
        )
        return approval

    # -------------------------------------------------------------------------
    # Query Methods
    # -------------------------------------------------------------------------

    @property
    def is_expired(self) -> bool:
        """Check if approval has expired.

        Returns:
            True if current time is past expiration.
        """
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def is_actionable(self) -> bool:
        """Check if approval can still be acted upon.

        Returns:
            True if pending and not expired.
        """
        return self.status == ApprovalStatus.PENDING and not self.is_expired

    @property
    def time_remaining(self) -> timedelta:
        """Get time remaining until expiration.

        Returns:
            Time remaining (may be negative if expired).
        """
        return self.expires_at - datetime.now(timezone.utc)

    # -------------------------------------------------------------------------
    # State Transitions
    # -------------------------------------------------------------------------

    def approve(self, approved_by: str) -> None:
        """Approve the request.

        Args:
            approved_by: Identifier of approver.

        Raises:
            ApprovalExpiredError: If approval has expired.
            ApprovalAlreadyResolvedError: If already resolved.
        """
        if self.is_expired:
            # Auto-transition to expired if checking after expiration
            self._expire()
            raise ApprovalExpiredError(str(self.id))

        if self.status != ApprovalStatus.PENDING:
            raise ApprovalAlreadyResolvedError(str(self.id), self.status.value)

        validate_approval_transition(str(self.id), self.status, ApprovalStatus.APPROVED)
        self.resolved_by = approved_by
        self.resolved_at = datetime.now(timezone.utc)
        self.status = ApprovalStatus.APPROVED
        self._touch()
        self._record_event(
            ApprovalGranted(
                aggregate_id=str(self.id),
                aggregate_type="Approval",
                approval_id=str(self.id),
                cart_id=str(self.cart_id),
                approved_by=approved_by,
                approved_at=self.resolved_at,
            )
        )

    def reject(self, rejected_by: str, reason: str = "") -> None:
        """Reject the request.

        Args:
            rejected_by: Identifier of rejector.
            reason: Reason for rejection.

        Raises:
            ApprovalExpiredError: If approval has expired.
            ApprovalAlreadyResolvedError: If already resolved.
        """
        if self.is_expired:
            self._expire()
            raise ApprovalExpiredError(str(self.id))

        if self.status != ApprovalStatus.PENDING:
            raise ApprovalAlreadyResolvedError(str(self.id), self.status.value)

        validate_approval_transition(str(self.id), self.status, ApprovalStatus.REJECTED)
        self.resolved_by = rejected_by
        self.resolution_reason = reason
        self.resolved_at = datetime.now(timezone.utc)
        self.status = ApprovalStatus.REJECTED
        self._touch()
        self._record_event(
            ApprovalRejected(
                aggregate_id=str(self.id),
                aggregate_type="Approval",
                approval_id=str(self.id),
                cart_id=str(self.cart_id),
                rejected_by=rejected_by,
                reason=reason,
            )
        )

    def _expire(self) -> None:
        """Mark approval as expired (internal method)."""
        if self.status == ApprovalStatus.PENDING:
            self.status = ApprovalStatus.EXPIRED
            self.resolved_at = datetime.now(timezone.utc)
            self._touch()
            self._record_event(
                ApprovalExpired(
                    aggregate_id=str(self.id),
                    aggregate_type="Approval",
                    approval_id=str(self.id),
                    cart_id=str(self.cart_id),
                    expired_at=self.resolved_at,
                )
            )

    def check_expiration(self) -> bool:
        """Check and handle expiration.

        Call this method to check if the approval has expired
        and transition to expired state if necessary.

        Returns:
            True if approval was or is now expired.
        """
        if self.is_expired and self.status == ApprovalStatus.PENDING:
            self._expire()
            return True
        return self.status == ApprovalStatus.EXPIRED


# ============================================================================
# Intent Aggregate Root
# ============================================================================


@dataclass(kw_only=True)
class Intent(AggregateRoot[IntentId]):
    """Purchase intent aggregate root.

    An Intent represents a user's expressed desire to purchase something.
    It captures the natural language query and serves as a starting point
    for collecting offers from merchants.

    Attributes:
        id: Unique intent identifier.
        query: The natural language search/intent query.
        session_id: Optional session identifier for the agent.
        offers: List of offers collected for this intent.
        metadata: Additional metadata (category hints, filters, etc.).
    """

    id: IntentId
    query: str
    session_id: str | None = None
    offer_ids: list[OfferId] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)
    offers_collected: bool = False

    @classmethod
    def create(
        cls,
        query: str,
        session_id: str | None = None,
        metadata: dict[str, object] | None = None,
        intent_id: IntentId | None = None,
    ) -> "Intent":
        """Create a new purchase intent.

        Factory method that creates an intent and records the creation event.

        Args:
            query: Natural language search query.
            session_id: Optional session identifier.
            metadata: Optional metadata (filters, hints).
            intent_id: Optional pre-generated intent ID.

        Returns:
            New Intent instance.
        """
        intent = cls(
            id=intent_id or IntentId.generate(),
            query=query,
            session_id=session_id,
            metadata=metadata or {},
        )
        intent._record_event(
            IntentCreated(
                aggregate_id=str(intent.id),
                aggregate_type="Intent",
                intent_id=str(intent.id),
                query=query,
                session_id=session_id,
            )
        )
        return intent

    def add_offer(self, offer_id: OfferId) -> None:
        """Add an offer ID to this intent.

        Args:
            offer_id: Offer identifier to add.
        """
        if offer_id not in self.offer_ids:
            self.offer_ids.append(offer_id)
            self._touch()

    def mark_offers_collected(self, merchant_ids: list[str]) -> None:
        """Mark that offers have been collected.

        Args:
            merchant_ids: List of merchant IDs that were queried.
        """
        self.offers_collected = True
        self._touch()
        self._record_event(
            OffersCollected(
                aggregate_id=str(self.id),
                aggregate_type="Intent",
                intent_id=str(self.id),
                offer_count=len(self.offer_ids),
                merchant_ids=merchant_ids,
            )
        )


# ============================================================================
# Offer Entity
# ============================================================================


@dataclass(kw_only=True)
class OfferItem:
    """A product item within an offer.

    Represents a matched product from a merchant's catalog.

    Attributes:
        product_id: Merchant's product identifier.
        variant_id: Optional variant identifier.
        sku: Stock keeping unit.
        title: Product title.
        description: Product description.
        brand: Product brand.
        category_path: Category hierarchy path.
        unit_price: Price per unit.
        quantity_available: Available stock.
        image_url: Product image URL.
        rating: Product rating (0-5).
        review_count: Number of reviews.
    """

    product_id: str
    title: str
    unit_price: Money
    quantity_available: int
    variant_id: str | None = None
    sku: str | None = None
    description: str | None = None
    brand: str | None = None
    category_path: str | None = None
    image_url: str | None = None
    rating: float | None = None
    review_count: int | None = None


@dataclass(kw_only=True)
class Offer(AggregateRoot[OfferId]):
    """Offer aggregate root.

    An Offer represents a merchant's response to a purchase intent,
    containing available products with prices and availability.

    Attributes:
        id: Unique offer identifier.
        intent_id: Associated intent identifier.
        merchant_id: Merchant providing this offer.
        items: List of product items in this offer.
        expires_at: When this offer expires.
        metadata: Additional metadata from merchant.
    """

    id: OfferId
    intent_id: IntentId
    merchant_id: MerchantId
    items: list[OfferItem] = field(default_factory=list)
    expires_at: datetime | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        intent_id: IntentId,
        merchant_id: MerchantId,
        items: list[OfferItem],
        expires_at: datetime | None = None,
        metadata: dict[str, object] | None = None,
        offer_id: OfferId | None = None,
    ) -> "Offer":
        """Create a new offer.

        Factory method that creates an offer with items from a merchant.

        Args:
            intent_id: Associated intent ID.
            merchant_id: Merchant providing the offer.
            items: List of offer items.
            expires_at: Optional expiration time.
            metadata: Optional metadata.
            offer_id: Optional pre-generated offer ID.

        Returns:
            New Offer instance.
        """
        offer = cls(
            id=offer_id or OfferId.generate(),
            intent_id=intent_id,
            merchant_id=merchant_id,
            items=items,
            expires_at=expires_at,
            metadata=metadata or {},
        )
        return offer

    @property
    def item_count(self) -> int:
        """Get number of items in this offer.

        Returns:
            Number of items.
        """
        return len(self.items)

    @property
    def is_expired(self) -> bool:
        """Check if offer has expired.

        Returns:
            True if expired, False if still valid or no expiration set.
        """
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def lowest_price(self) -> Money | None:
        """Get the lowest price item.

        Returns:
            Lowest price or None if no items.
        """
        if not self.items:
            return None
        return min(self.items, key=lambda i: i.unit_price.amount_cents).unit_price

    @property
    def highest_price(self) -> Money | None:
        """Get the highest price item.

        Returns:
            Highest price or None if no items.
        """
        if not self.items:
            return None
        return max(self.items, key=lambda i: i.unit_price.amount_cents).unit_price

    def get_item(self, product_id: str) -> OfferItem | None:
        """Get item by product ID.

        Args:
            product_id: Product identifier.

        Returns:
            OfferItem if found, None otherwise.
        """
        for item in self.items:
            if item.product_id == product_id:
                return item
        return None


# ============================================================================
# Checkout Item Entity
# ============================================================================


@dataclass
class CheckoutItem:
    """An item in a checkout session.

    Checkout items are snapshots of offer items at the time they were
    added to the checkout, with current pricing from the merchant.

    Attributes:
        product_id: Merchant's product identifier.
        variant_id: Variant identifier if applicable.
        sku: Stock keeping unit.
        title: Product title.
        unit_price: Current unit price from merchant.
        quantity: Ordered quantity.
        currency: Currency code.
    """

    product_id: str
    sku: str
    title: str
    unit_price_cents: int
    quantity: int
    currency: str = "USD"
    variant_id: str | None = None

    @property
    def line_total_cents(self) -> int:
        """Calculate line total in cents."""
        return self.unit_price_cents * self.quantity

    def to_frozen_item(self) -> FrozenReceiptItem:
        """Convert to frozen receipt item.

        Returns:
            FrozenReceiptItem snapshot.
        """
        return FrozenReceiptItem(
            product_id=self.product_id,
            variant_id=self.variant_id,
            sku=self.sku,
            title=self.title,
            unit_price_cents=self.unit_price_cents,
            quantity=self.quantity,
            currency=self.currency,
        )


# ============================================================================
# Checkout Aggregate Root
# ============================================================================


@dataclass
class AuditEntry:
    """An entry in the checkout audit trail.

    Attributes:
        timestamp: When the action occurred.
        action: Description of the action.
        from_status: Previous status (if applicable).
        to_status: New status (if applicable).
        actor: Who performed the action.
        details: Additional details.
    """

    timestamp: datetime
    action: str
    from_status: str | None = None
    to_status: str | None = None
    actor: str | None = None
    details: dict[str, object] | None = None


@dataclass(kw_only=True)
class Checkout(AggregateRoot[CheckoutId]):
    """Checkout session aggregate root.

    A Checkout represents a purchase session that requires human approval.
    It tracks the state through: created → quoted → awaiting_approval →
    approved → confirmed.

    The frozen receipt captures pricing at approval time to detect changes
    that would require re-approval.

    Attributes:
        id: Unique checkout identifier.
        offer_id: Source offer identifier.
        merchant_id: Merchant fulfilling the order.
        status: Current checkout status (state machine).
        items: Checkout items with current pricing.
        subtotal_cents: Current subtotal.
        tax_cents: Current tax.
        shipping_cents: Current shipping.
        total_cents: Current total.
        currency: Currency code.
        merchant_checkout_id: Merchant's checkout session ID.
        receipt_hash: Hash from merchant for price verification.
        frozen_receipt: Frozen receipt at time of approval request.
        merchant_order_id: Merchant's order ID (after confirmation).
        approved_by: Who approved the checkout.
        approved_at: When it was approved.
        confirmed_at: When it was confirmed.
        expires_at: When the checkout expires.
        failure_reason: Reason if failed.
        idempotency_key: Idempotency key for the operation.
        audit_trail: List of audit entries.
    """

    id: CheckoutId
    offer_id: OfferId
    merchant_id: MerchantId
    status: CheckoutStatus = CheckoutStatus.CREATED
    items: list[CheckoutItem] = field(default_factory=list)
    subtotal_cents: int = 0
    tax_cents: int = 0
    shipping_cents: int = 0
    total_cents: int = 0
    currency: str = "USD"
    merchant_checkout_id: str | None = None
    receipt_hash: str | None = None
    frozen_receipt: FrozenReceipt | None = None
    merchant_order_id: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    confirmed_at: datetime | None = None
    expires_at: datetime | None = None
    failure_reason: str | None = None
    idempotency_key: str | None = None
    audit_trail: list[AuditEntry] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        offer_id: OfferId,
        merchant_id: MerchantId,
        idempotency_key: str | None = None,
        checkout_id: CheckoutId | None = None,
    ) -> "Checkout":
        """Create a new checkout from an offer.

        Factory method that creates a checkout and records the creation event.

        Args:
            offer_id: Source offer identifier.
            merchant_id: Merchant fulfilling the order.
            idempotency_key: Optional idempotency key.
            checkout_id: Optional pre-generated checkout ID.

        Returns:
            New Checkout instance.
        """
        now = datetime.now(timezone.utc)
        checkout = cls(
            id=checkout_id or CheckoutId.generate(),
            offer_id=offer_id,
            merchant_id=merchant_id,
            idempotency_key=idempotency_key,
            expires_at=now + timedelta(hours=24),
        )

        checkout._add_audit_entry(
            action="checkout_created",
            to_status=CheckoutStatus.CREATED.value,
            details={"offer_id": str(offer_id), "merchant_id": str(merchant_id)},
        )

        checkout._record_event(
            CheckoutCreated(
                aggregate_id=str(checkout.id),
                aggregate_type="Checkout",
                checkout_id=str(checkout.id),
                offer_id=str(offer_id),
                merchant_id=str(merchant_id),
            )
        )
        return checkout

    # -------------------------------------------------------------------------
    # Private Helpers
    # -------------------------------------------------------------------------

    def _add_audit_entry(
        self,
        action: str,
        from_status: str | None = None,
        to_status: str | None = None,
        actor: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        """Add an entry to the audit trail."""
        self.audit_trail.append(
            AuditEntry(
                timestamp=datetime.now(timezone.utc),
                action=action,
                from_status=from_status,
                to_status=to_status,
                actor=actor,
                details=details,
            )
        )

    # -------------------------------------------------------------------------
    # Query Methods
    # -------------------------------------------------------------------------

    @property
    def is_expired(self) -> bool:
        """Check if checkout has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def is_confirmable(self) -> bool:
        """Check if checkout can be confirmed."""
        return self.status == CheckoutStatus.APPROVED and not self.is_expired

    @property
    def requires_reapproval(self) -> bool:
        """Check if checkout requires re-approval due to price change."""
        if self.frozen_receipt is None:
            return False
        return not self.frozen_receipt.matches_total(self.total_cents)

    # -------------------------------------------------------------------------
    # State Transitions
    # -------------------------------------------------------------------------

    def set_quote(
        self,
        items: list[CheckoutItem],
        subtotal_cents: int,
        tax_cents: int,
        shipping_cents: int,
        total_cents: int,
        currency: str,
        merchant_checkout_id: str,
        receipt_hash: str,
    ) -> None:
        """Set quote from merchant.

        Args:
            items: Quoted items with prices.
            subtotal_cents: Subtotal amount.
            tax_cents: Tax amount.
            shipping_cents: Shipping amount.
            total_cents: Total amount.
            currency: Currency code.
            merchant_checkout_id: Merchant's checkout ID.
            receipt_hash: Merchant's receipt hash.

        Raises:
            InvalidStateTransitionError: If not in valid state.
            CheckoutExpiredError: If checkout has expired.
        """
        if self.is_expired:
            raise CheckoutExpiredError(str(self.id))

        # If we're in awaiting_approval or approved and price changed,
        # we need to go back to quoted for re-approval
        if self.status.requires_reapproval():
            if self.frozen_receipt and not self.frozen_receipt.matches_total(total_cents):
                # Price changed, reset to quoted
                old_status = self.status
                self.status = CheckoutStatus.QUOTED
                self.frozen_receipt = None  # Clear frozen receipt

                self._add_audit_entry(
                    action="price_changed_reapproval_required",
                    from_status=old_status.value,
                    to_status=self.status.value,
                    details={
                        "original_total_cents": self.total_cents,
                        "new_total_cents": total_cents,
                    },
                )

                self._record_event(
                    CheckoutReapprovalRequired(
                        aggregate_id=str(self.id),
                        aggregate_type="Checkout",
                        checkout_id=str(self.id),
                        original_total_cents=self.total_cents,
                        new_total_cents=total_cents,
                        currency=currency,
                        reason="Price changed since approval was requested",
                    )
                )
        else:
            validate_checkout_transition(str(self.id), self.status, CheckoutStatus.QUOTED)
            old_status = self.status
            self.status = CheckoutStatus.QUOTED

            self._add_audit_entry(
                action="quote_received",
                from_status=old_status.value,
                to_status=self.status.value,
                details={
                    "total_cents": total_cents,
                    "merchant_checkout_id": merchant_checkout_id,
                },
            )

        # Update pricing
        self.items = items
        self.subtotal_cents = subtotal_cents
        self.tax_cents = tax_cents
        self.shipping_cents = shipping_cents
        self.total_cents = total_cents
        self.currency = currency
        self.merchant_checkout_id = merchant_checkout_id
        self.receipt_hash = receipt_hash
        self._touch()

        self._record_event(
            CheckoutQuoted(
                aggregate_id=str(self.id),
                aggregate_type="Checkout",
                checkout_id=str(self.id),
                total_cents=total_cents,
                currency=currency,
                receipt_hash=receipt_hash,
                merchant_checkout_id=merchant_checkout_id,
            )
        )

    def request_approval(self) -> FrozenReceipt:
        """Request approval and freeze the receipt.

        Creates a frozen snapshot of the current pricing for
        comparison when checking for price changes.

        Returns:
            The frozen receipt.

        Raises:
            InvalidStateTransitionError: If not in valid state.
            CheckoutExpiredError: If checkout has expired.
        """
        if self.is_expired:
            raise CheckoutExpiredError(str(self.id))

        validate_checkout_transition(
            str(self.id), self.status, CheckoutStatus.AWAITING_APPROVAL
        )

        old_status = self.status

        # Create frozen receipt
        frozen_items = [item.to_frozen_item() for item in self.items]
        self.frozen_receipt = FrozenReceipt.create(
            items=frozen_items,
            subtotal_cents=self.subtotal_cents,
            tax_cents=self.tax_cents,
            shipping_cents=self.shipping_cents,
            total_cents=self.total_cents,
            currency=self.currency,
        )

        self.status = CheckoutStatus.AWAITING_APPROVAL
        self._touch()

        self._add_audit_entry(
            action="approval_requested",
            from_status=old_status.value,
            to_status=self.status.value,
            details={
                "frozen_receipt_hash": self.frozen_receipt.hash,
                "total_cents": self.total_cents,
            },
        )

        self._record_event(
            CheckoutApprovalRequested(
                aggregate_id=str(self.id),
                aggregate_type="Checkout",
                checkout_id=str(self.id),
                total_cents=self.total_cents,
                currency=self.currency,
                frozen_receipt_hash=self.frozen_receipt.hash,
            )
        )

        return self.frozen_receipt

    def approve(self, approved_by: str) -> None:
        """Approve the checkout.

        Args:
            approved_by: Identifier of who approved.

        Raises:
            InvalidStateTransitionError: If not in valid state.
            CheckoutExpiredError: If checkout has expired.
            ReapprovalRequiredError: If price has changed.
        """
        if self.is_expired:
            raise CheckoutExpiredError(str(self.id))

        # Check if price has changed since approval was requested
        if self.frozen_receipt and not self.frozen_receipt.matches_total(self.total_cents):
            raise ReapprovalRequiredError(
                checkout_id=str(self.id),
                original_total_cents=self.frozen_receipt.total_cents,
                new_total_cents=self.total_cents,
            )

        validate_checkout_transition(
            str(self.id), self.status, CheckoutStatus.APPROVED
        )

        old_status = self.status
        self.status = CheckoutStatus.APPROVED
        self.approved_by = approved_by
        self.approved_at = datetime.now(timezone.utc)
        self._touch()

        self._add_audit_entry(
            action="approved",
            from_status=old_status.value,
            to_status=self.status.value,
            actor=approved_by,
            details={"total_cents": self.total_cents},
        )

        self._record_event(
            CheckoutApproved(
                aggregate_id=str(self.id),
                aggregate_type="Checkout",
                checkout_id=str(self.id),
                approved_by=approved_by,
                approved_at=self.approved_at,
            )
        )

    def confirm(self, merchant_order_id: str) -> None:
        """Confirm the checkout (execute purchase).

        Args:
            merchant_order_id: Merchant's order ID.

        Raises:
            InvalidStateTransitionError: If not in valid state.
            CheckoutExpiredError: If checkout has expired.
            CheckoutAlreadyConfirmedError: If already confirmed.
            ReapprovalRequiredError: If price has changed.
        """
        if self.is_expired:
            raise CheckoutExpiredError(str(self.id))

        if self.status == CheckoutStatus.CONFIRMED:
            raise CheckoutAlreadyConfirmedError(
                str(self.id), self.merchant_order_id or ""
            )

        # Final price check before confirmation
        if self.frozen_receipt and not self.frozen_receipt.matches_total(self.total_cents):
            raise ReapprovalRequiredError(
                checkout_id=str(self.id),
                original_total_cents=self.frozen_receipt.total_cents,
                new_total_cents=self.total_cents,
            )

        if self.status != CheckoutStatus.APPROVED:
            raise CheckoutNotApprovedError(str(self.id), self.status.value)

        validate_checkout_transition(
            str(self.id), self.status, CheckoutStatus.CONFIRMED
        )

        old_status = self.status
        self.status = CheckoutStatus.CONFIRMED
        self.merchant_order_id = merchant_order_id
        self.confirmed_at = datetime.now(timezone.utc)
        self._touch()

        self._add_audit_entry(
            action="confirmed",
            from_status=old_status.value,
            to_status=self.status.value,
            details={
                "merchant_order_id": merchant_order_id,
                "total_cents": self.total_cents,
            },
        )

        self._record_event(
            CheckoutConfirmed(
                aggregate_id=str(self.id),
                aggregate_type="Checkout",
                checkout_id=str(self.id),
                merchant_order_id=merchant_order_id,
                total_cents=self.total_cents,
                currency=self.currency,
                confirmed_at=self.confirmed_at,
            )
        )

    def fail(self, error_code: str, error_message: str) -> None:
        """Mark checkout as failed.

        Args:
            error_code: Error code.
            error_message: Error message.

        Raises:
            InvalidStateTransitionError: If not in valid state.
        """
        validate_checkout_transition(str(self.id), self.status, CheckoutStatus.FAILED)

        old_status = self.status
        self.status = CheckoutStatus.FAILED
        self.failure_reason = f"{error_code}: {error_message}"
        self._touch()

        self._add_audit_entry(
            action="failed",
            from_status=old_status.value,
            to_status=self.status.value,
            details={"error_code": error_code, "error_message": error_message},
        )

        self._record_event(
            CheckoutFailed(
                aggregate_id=str(self.id),
                aggregate_type="Checkout",
                checkout_id=str(self.id),
                error_code=error_code,
                error_message=error_message,
            )
        )

    def cancel(self, reason: str = "", cancelled_by: str = "system") -> None:
        """Cancel the checkout.

        Args:
            reason: Cancellation reason.
            cancelled_by: Who cancelled.

        Raises:
            InvalidStateTransitionError: If not in valid state.
        """
        validate_checkout_transition(
            str(self.id), self.status, CheckoutStatus.CANCELLED
        )

        old_status = self.status
        self.status = CheckoutStatus.CANCELLED
        self.failure_reason = reason
        self._touch()

        self._add_audit_entry(
            action="cancelled",
            from_status=old_status.value,
            to_status=self.status.value,
            actor=cancelled_by,
            details={"reason": reason},
        )

        self._record_event(
            CheckoutCancelled(
                aggregate_id=str(self.id),
                aggregate_type="Checkout",
                checkout_id=str(self.id),
                reason=reason,
                cancelled_by=cancelled_by,
            )
        )
