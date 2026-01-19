"""Domain events for the CartPilot system.

Domain events represent significant occurrences in the domain.
They are used for:
- Event sourcing (reconstructing aggregate state)
- Integration between bounded contexts
- Triggering side effects (notifications, webhooks)
- Audit logging
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar
from uuid import UUID, uuid4

from app.domain.base import DomainEvent


# ============================================================================
# Cart Events
# ============================================================================


@dataclass(frozen=True)
class CartCreated(DomainEvent):
    """Event raised when a new cart is created."""

    event_type: ClassVar[str] = "cart.created"

    cart_id: str = ""
    merchant_id: str = ""
    session_id: str | None = None

    def _payload(self) -> dict[str, Any]:
        """Get event-specific payload."""
        return {
            "cart_id": self.cart_id,
            "merchant_id": self.merchant_id,
            "session_id": self.session_id,
        }


@dataclass(frozen=True)
class CartItemAdded(DomainEvent):
    """Event raised when an item is added to a cart."""

    event_type: ClassVar[str] = "cart.item_added"

    cart_id: str = ""
    item_id: str = ""
    product_id: str = ""
    product_name: str = ""
    quantity: int = 0
    unit_price_cents: int = 0
    currency: str = "USD"

    def _payload(self) -> dict[str, Any]:
        """Get event-specific payload."""
        return {
            "cart_id": self.cart_id,
            "item_id": self.item_id,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "quantity": self.quantity,
            "unit_price_cents": self.unit_price_cents,
            "currency": self.currency,
        }


@dataclass(frozen=True)
class CartItemRemoved(DomainEvent):
    """Event raised when an item is removed from a cart."""

    event_type: ClassVar[str] = "cart.item_removed"

    cart_id: str = ""
    item_id: str = ""
    product_id: str = ""

    def _payload(self) -> dict[str, Any]:
        """Get event-specific payload."""
        return {
            "cart_id": self.cart_id,
            "item_id": self.item_id,
            "product_id": self.product_id,
        }


@dataclass(frozen=True)
class CartItemQuantityUpdated(DomainEvent):
    """Event raised when cart item quantity is changed."""

    event_type: ClassVar[str] = "cart.item_quantity_updated"

    cart_id: str = ""
    item_id: str = ""
    old_quantity: int = 0
    new_quantity: int = 0

    def _payload(self) -> dict[str, Any]:
        """Get event-specific payload."""
        return {
            "cart_id": self.cart_id,
            "item_id": self.item_id,
            "old_quantity": self.old_quantity,
            "new_quantity": self.new_quantity,
        }


@dataclass(frozen=True)
class CartCheckoutStarted(DomainEvent):
    """Event raised when checkout process begins."""

    event_type: ClassVar[str] = "cart.checkout_started"

    cart_id: str = ""
    total_cents: int = 0
    currency: str = "USD"
    item_count: int = 0

    def _payload(self) -> dict[str, Any]:
        """Get event-specific payload."""
        return {
            "cart_id": self.cart_id,
            "total_cents": self.total_cents,
            "currency": self.currency,
            "item_count": self.item_count,
        }


@dataclass(frozen=True)
class CartSubmitted(DomainEvent):
    """Event raised when cart is submitted for processing."""

    event_type: ClassVar[str] = "cart.submitted"

    cart_id: str = ""
    order_id: str = ""
    total_cents: int = 0
    currency: str = "USD"

    def _payload(self) -> dict[str, Any]:
        """Get event-specific payload."""
        return {
            "cart_id": self.cart_id,
            "order_id": self.order_id,
            "total_cents": self.total_cents,
            "currency": self.currency,
        }


@dataclass(frozen=True)
class CartCompleted(DomainEvent):
    """Event raised when cart processing is complete."""

    event_type: ClassVar[str] = "cart.completed"

    cart_id: str = ""
    order_id: str = ""

    def _payload(self) -> dict[str, Any]:
        """Get event-specific payload."""
        return {
            "cart_id": self.cart_id,
            "order_id": self.order_id,
        }


@dataclass(frozen=True)
class CartAbandoned(DomainEvent):
    """Event raised when cart is abandoned (expired or manually)."""

    event_type: ClassVar[str] = "cart.abandoned"

    cart_id: str = ""
    reason: str = ""

    def _payload(self) -> dict[str, Any]:
        """Get event-specific payload."""
        return {
            "cart_id": self.cart_id,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CartFailed(DomainEvent):
    """Event raised when cart processing fails."""

    event_type: ClassVar[str] = "cart.failed"

    cart_id: str = ""
    error_code: str = ""
    error_message: str = ""

    def _payload(self) -> dict[str, Any]:
        """Get event-specific payload."""
        return {
            "cart_id": self.cart_id,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


# ============================================================================
# Order Events
# ============================================================================


@dataclass(frozen=True)
class OrderCreated(DomainEvent):
    """Event raised when an order is created from a cart."""

    event_type: ClassVar[str] = "order.created"

    order_id: str = ""
    cart_id: str = ""
    merchant_id: str = ""
    total_cents: int = 0
    currency: str = "USD"
    customer_email: str = ""

    def _payload(self) -> dict[str, Any]:
        """Get event-specific payload."""
        return {
            "order_id": self.order_id,
            "cart_id": self.cart_id,
            "merchant_id": self.merchant_id,
            "total_cents": self.total_cents,
            "currency": self.currency,
            "customer_email": self.customer_email,
        }


@dataclass(frozen=True)
class OrderConfirmed(DomainEvent):
    """Event raised when merchant confirms the order."""

    event_type: ClassVar[str] = "order.confirmed"

    order_id: str = ""
    merchant_order_id: str = ""
    confirmed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def _payload(self) -> dict[str, Any]:
        """Get event-specific payload."""
        return {
            "order_id": self.order_id,
            "merchant_order_id": self.merchant_order_id,
            "confirmed_at": self.confirmed_at.isoformat(),
        }


@dataclass(frozen=True)
class OrderShipped(DomainEvent):
    """Event raised when order is shipped."""

    event_type: ClassVar[str] = "order.shipped"

    order_id: str = ""
    tracking_number: str | None = None
    carrier: str | None = None
    shipped_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def _payload(self) -> dict[str, Any]:
        """Get event-specific payload."""
        return {
            "order_id": self.order_id,
            "tracking_number": self.tracking_number,
            "carrier": self.carrier,
            "shipped_at": self.shipped_at.isoformat(),
        }


@dataclass(frozen=True)
class OrderDelivered(DomainEvent):
    """Event raised when order is delivered."""

    event_type: ClassVar[str] = "order.delivered"

    order_id: str = ""
    delivered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def _payload(self) -> dict[str, Any]:
        """Get event-specific payload."""
        return {
            "order_id": self.order_id,
            "delivered_at": self.delivered_at.isoformat(),
        }


@dataclass(frozen=True)
class OrderCancelled(DomainEvent):
    """Event raised when order is cancelled."""

    event_type: ClassVar[str] = "order.cancelled"

    order_id: str = ""
    reason: str = ""
    cancelled_by: str = ""  # 'customer', 'merchant', 'system'

    def _payload(self) -> dict[str, Any]:
        """Get event-specific payload."""
        return {
            "order_id": self.order_id,
            "reason": self.reason,
            "cancelled_by": self.cancelled_by,
        }


@dataclass(frozen=True)
class OrderRefunded(DomainEvent):
    """Event raised when order is refunded."""

    event_type: ClassVar[str] = "order.refunded"

    order_id: str = ""
    refund_amount_cents: int = 0
    currency: str = "USD"
    reason: str = ""

    def _payload(self) -> dict[str, Any]:
        """Get event-specific payload."""
        return {
            "order_id": self.order_id,
            "refund_amount_cents": self.refund_amount_cents,
            "currency": self.currency,
            "reason": self.reason,
        }


# ============================================================================
# Approval Events
# ============================================================================


@dataclass(frozen=True)
class ApprovalRequested(DomainEvent):
    """Event raised when approval is requested for an operation."""

    event_type: ClassVar[str] = "approval.requested"

    approval_id: str = ""
    cart_id: str = ""
    amount_cents: int = 0
    currency: str = "USD"
    reason: str = ""
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def _payload(self) -> dict[str, Any]:
        """Get event-specific payload."""
        return {
            "approval_id": self.approval_id,
            "cart_id": self.cart_id,
            "amount_cents": self.amount_cents,
            "currency": self.currency,
            "reason": self.reason,
            "expires_at": self.expires_at.isoformat(),
        }


@dataclass(frozen=True)
class ApprovalGranted(DomainEvent):
    """Event raised when approval is granted."""

    event_type: ClassVar[str] = "approval.granted"

    approval_id: str = ""
    cart_id: str = ""
    approved_by: str = ""
    approved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def _payload(self) -> dict[str, Any]:
        """Get event-specific payload."""
        return {
            "approval_id": self.approval_id,
            "cart_id": self.cart_id,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat(),
        }


@dataclass(frozen=True)
class ApprovalRejected(DomainEvent):
    """Event raised when approval is rejected."""

    event_type: ClassVar[str] = "approval.rejected"

    approval_id: str = ""
    cart_id: str = ""
    rejected_by: str = ""
    reason: str = ""

    def _payload(self) -> dict[str, Any]:
        """Get event-specific payload."""
        return {
            "approval_id": self.approval_id,
            "cart_id": self.cart_id,
            "rejected_by": self.rejected_by,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ApprovalExpired(DomainEvent):
    """Event raised when approval request expires."""

    event_type: ClassVar[str] = "approval.expired"

    approval_id: str = ""
    cart_id: str = ""
    expired_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def _payload(self) -> dict[str, Any]:
        """Get event-specific payload."""
        return {
            "approval_id": self.approval_id,
            "cart_id": self.cart_id,
            "expired_at": self.expired_at.isoformat(),
        }


# ============================================================================
# Webhook Events
# ============================================================================


@dataclass(frozen=True)
class WebhookReceived(DomainEvent):
    """Event raised when a webhook is received from a merchant."""

    event_type: ClassVar[str] = "webhook.received"

    webhook_id: str = field(default_factory=lambda: str(uuid4()))
    merchant_id: str = ""
    event_name: str = ""
    idempotency_key: str = ""

    def _payload(self) -> dict[str, Any]:
        """Get event-specific payload."""
        return {
            "webhook_id": self.webhook_id,
            "merchant_id": self.merchant_id,
            "event_name": self.event_name,
            "idempotency_key": self.idempotency_key,
        }


@dataclass(frozen=True)
class WebhookProcessed(DomainEvent):
    """Event raised when a webhook is successfully processed."""

    event_type: ClassVar[str] = "webhook.processed"

    webhook_id: str = ""
    merchant_id: str = ""
    event_name: str = ""
    processing_time_ms: int = 0

    def _payload(self) -> dict[str, Any]:
        """Get event-specific payload."""
        return {
            "webhook_id": self.webhook_id,
            "merchant_id": self.merchant_id,
            "event_name": self.event_name,
            "processing_time_ms": self.processing_time_ms,
        }


@dataclass(frozen=True)
class WebhookFailed(DomainEvent):
    """Event raised when webhook processing fails."""

    event_type: ClassVar[str] = "webhook.failed"

    webhook_id: str = ""
    merchant_id: str = ""
    event_name: str = ""
    error_message: str = ""
    retry_count: int = 0

    def _payload(self) -> dict[str, Any]:
        """Get event-specific payload."""
        return {
            "webhook_id": self.webhook_id,
            "merchant_id": self.merchant_id,
            "event_name": self.event_name,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
        }


# ============================================================================
# Event Registry
# ============================================================================


# Registry of all event types for deserialization
EVENT_REGISTRY: dict[str, type[DomainEvent]] = {
    # Cart events
    CartCreated.event_type: CartCreated,
    CartItemAdded.event_type: CartItemAdded,
    CartItemRemoved.event_type: CartItemRemoved,
    CartItemQuantityUpdated.event_type: CartItemQuantityUpdated,
    CartCheckoutStarted.event_type: CartCheckoutStarted,
    CartSubmitted.event_type: CartSubmitted,
    CartCompleted.event_type: CartCompleted,
    CartAbandoned.event_type: CartAbandoned,
    CartFailed.event_type: CartFailed,
    # Order events
    OrderCreated.event_type: OrderCreated,
    OrderConfirmed.event_type: OrderConfirmed,
    OrderShipped.event_type: OrderShipped,
    OrderDelivered.event_type: OrderDelivered,
    OrderCancelled.event_type: OrderCancelled,
    OrderRefunded.event_type: OrderRefunded,
    # Approval events
    ApprovalRequested.event_type: ApprovalRequested,
    ApprovalGranted.event_type: ApprovalGranted,
    ApprovalRejected.event_type: ApprovalRejected,
    ApprovalExpired.event_type: ApprovalExpired,
    # Webhook events
    WebhookReceived.event_type: WebhookReceived,
    WebhookProcessed.event_type: WebhookProcessed,
    WebhookFailed.event_type: WebhookFailed,
}


def get_event_class(event_type: str) -> type[DomainEvent] | None:
    """Get event class by event type string.

    Args:
        event_type: Event type identifier (e.g., 'cart.created').

    Returns:
        Event class if found, None otherwise.
    """
    return EVENT_REGISTRY.get(event_type)
