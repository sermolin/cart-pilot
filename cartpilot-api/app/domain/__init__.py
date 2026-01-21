"""Domain layer - Entities, value objects, state machines, domain events.

This module exports the core domain building blocks following DDD patterns:

- **Entities**: Objects with identity (Cart, Order, Approval)
- **Value Objects**: Immutable objects compared by value (Money, Address, typed IDs)
- **State Machines**: Deterministic state transitions (CartStatus, OrderStatus, ApprovalStatus)
- **Domain Events**: Represent significant domain occurrences
- **Exceptions**: Domain-specific errors and invariant violations

Example usage:
    from app.domain import Cart, Money, MerchantId, CartStatus

    # Create a cart
    cart = Cart.create(merchant_id=MerchantId("merchant-a"))

    # Add an item
    product = ProductRef(
        product_id=ProductId("SKU-001"),
        merchant_id=MerchantId("merchant-a"),
        name="Widget",
        unit_price=Money.from_float(29.99),
    )
    cart.add_item(product, quantity=2)

    # Check cart total
    print(cart.total)  # $59.98 USD
"""

# Base classes
from app.domain.base import AggregateRoot, DomainEvent, Entity, ValueObject

# Entities
from app.domain.entities import (
    Approval,
    AuditEntry,
    Cart,
    CartItem,
    Checkout,
    CheckoutItem,
    Intent,
    Offer,
    OfferItem,
    Order,
    OrderItem,
)

# Domain Events
from app.domain.events import (
    EVENT_REGISTRY,
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
    WebhookFailed,
    WebhookProcessed,
    WebhookReceived,
    get_event_class,
)

# Exceptions
from app.domain.exceptions import (
    ApprovalAlreadyResolvedError,
    ApprovalError,
    ApprovalExpiredError,
    CartEmptyError,
    CartError,
    CartItemNotFoundError,
    CartNotEditableError,
    CheckoutAlreadyConfirmedError,
    CheckoutError,
    CheckoutExpiredError,
    CheckoutNotApprovedError,
    CheckoutNotFoundError,
    CheckoutNotQuotedError,
    CurrencyMismatchError,
    DomainError,
    InvalidQuantityError,
    InvalidStateTransitionError,
    MoneyError,
    NegativeMoneyError,
    OrderError,
    OrderNotCancellableError,
    ReapprovalRequiredError,
)

# State Machines
from app.domain.state_machines import (
    ApprovalStatus,
    CartStatus,
    CheckoutStatus,
    OrderStatus,
    StateTransition,
    validate_approval_transition,
    validate_cart_transition,
    validate_checkout_transition,
    validate_order_transition,
)

# Value Objects
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
    WebhookPayload,
)

__all__ = [
    # Base classes
    "AggregateRoot",
    "DomainEvent",
    "Entity",
    "ValueObject",
    # Entities
    "Approval",
    "AuditEntry",
    "Cart",
    "CartItem",
    "Checkout",
    "CheckoutItem",
    "Intent",
    "Offer",
    "OfferItem",
    "Order",
    "OrderItem",
    # Value Objects
    "Address",
    "ApprovalId",
    "CartId",
    "CartItemId",
    "CheckoutId",
    "CustomerInfo",
    "FrozenReceipt",
    "FrozenReceiptItem",
    "IntentId",
    "MerchantId",
    "Money",
    "OfferId",
    "OrderId",
    "ProductId",
    "ProductRef",
    "WebhookPayload",
    # State Machines
    "ApprovalStatus",
    "CartStatus",
    "CheckoutStatus",
    "OrderStatus",
    "StateTransition",
    "validate_approval_transition",
    "validate_cart_transition",
    "validate_checkout_transition",
    "validate_order_transition",
    # Domain Events - Cart
    "CartCreated",
    "CartItemAdded",
    "CartItemRemoved",
    "CartItemQuantityUpdated",
    "CartCheckoutStarted",
    "CartSubmitted",
    "CartCompleted",
    "CartAbandoned",
    "CartFailed",
    # Domain Events - Order
    "OrderCreated",
    "OrderConfirmed",
    "OrderShipped",
    "OrderDelivered",
    "OrderCancelled",
    "OrderRefunded",
    # Domain Events - Approval
    "ApprovalRequested",
    "ApprovalGranted",
    "ApprovalRejected",
    "ApprovalExpired",
    # Domain Events - Checkout
    "CheckoutCreated",
    "CheckoutQuoted",
    "CheckoutApprovalRequested",
    "CheckoutApproved",
    "CheckoutConfirmed",
    "CheckoutReapprovalRequired",
    "CheckoutFailed",
    "CheckoutCancelled",
    # Domain Events - Intent
    "IntentCreated",
    "OffersCollected",
    # Domain Events - Webhook
    "WebhookReceived",
    "WebhookProcessed",
    "WebhookFailed",
    # Event utilities
    "EVENT_REGISTRY",
    "get_event_class",
    # Exceptions
    "DomainError",
    "InvalidStateTransitionError",
    "CartError",
    "CartNotEditableError",
    "CartItemNotFoundError",
    "CartEmptyError",
    "InvalidQuantityError",
    "OrderError",
    "OrderNotCancellableError",
    "ApprovalError",
    "ApprovalExpiredError",
    "ApprovalAlreadyResolvedError",
    "CheckoutError",
    "CheckoutNotFoundError",
    "ReapprovalRequiredError",
    "CheckoutExpiredError",
    "CheckoutAlreadyConfirmedError",
    "CheckoutNotQuotedError",
    "CheckoutNotApprovedError",
    "MoneyError",
    "CurrencyMismatchError",
    "NegativeMoneyError",
]
