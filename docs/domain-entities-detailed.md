# Domain Entities - Detailed Component Documentation

> **Complete technical documentation for domain entities**  
> This document provides comprehensive details for developers working with domain entities in CartPilot.

## Table of Contents

1. [Overview](#overview)
2. [Architecture & Design](#architecture--design)
3. [Entity Details](#entity-details)
4. [Value Objects](#value-objects)
5. [Domain Events](#domain-events)
6. [Business Rules](#business-rules)
7. [Code Examples](#code-examples)

---

## Overview

### Purpose

Domain entities are core aggregates with identity that persist across state changes. This module contains the main aggregates: Cart, Order, Checkout, Intent, Offer, and Approval.

**Location**: `cartpilot-api/app/domain/entities.py`  
**Lines of Code**: ~1951 lines  
**Dependencies**: Base classes, state machines, value objects, domain events, exceptions

### Responsibilities

- **Identity Management**: Maintain unique identity for aggregates
- **State Management**: Manage entity state and transitions
- **Business Logic**: Enforce business rules and invariants
- **Event Generation**: Emit domain events for state changes
- **Validation**: Validate entity state and operations

### Key Metrics

- **Aggregate Roots**: 6 (Cart, Order, Checkout, Intent, Offer, Approval)
- **Entities**: 3 (CartItem, CheckoutItem, OfferItem)
- **Value Objects**: Multiple (Money, Address, ProductRef, etc.)
- **Domain Events**: 30+ event types

---

## Architecture & Design

### Entity Hierarchy

```
AggregateRoot (base)
├── Cart (AggregateRoot[CartId])
├── Order (AggregateRoot[OrderId])
├── Checkout (AggregateRoot[CheckoutId])
├── Intent (AggregateRoot[IntentId])
├── Offer (AggregateRoot[OfferId])
└── Approval (AggregateRoot[ApprovalId])

Entity (base)
├── CartItem (Entity[CartItemId])
├── CheckoutItem (Entity[CheckoutItemId])
└── OfferItem (Entity[OfferItemId])
```

### Design Patterns

1. **Aggregate Pattern**: Entities grouped into aggregates
2. **Domain Events**: Events emitted for state changes
3. **Value Objects**: Immutable value objects for attributes
4. **Factory Pattern**: Factory methods for entity creation
5. **State Machine Pattern**: State transitions via state machines

---

## Entity Details

### Cart Aggregate

**Location**: Lines 155-500+

**Purpose**: Shopping cart aggregate root.

**Identity**: `CartId` (typed ID)

**States**: `CartStatus` enum (DRAFT, CHECKOUT, PENDING_APPROVAL, etc.)

**Properties**:
- `id: CartId` - Unique identifier
- `merchant_id: MerchantId` - Merchant this cart belongs to
- `status: CartStatus` - Current status
- `items: list[CartItem]` - Cart items
- `session_id: str | None` - Session identifier
- `customer: CustomerInfo | None` - Customer information
- `shipping_address: Address | None` - Shipping address
- `billing_address: Address | None` - Billing address
- `order_id: OrderId | None` - Associated order ID

**Key Methods**:
- `create(merchant_id, session_id, cart_id) -> Cart`: Factory method
- `add_item(product, quantity) -> CartItem`: Add item to cart
- `remove_item(item_id) -> None`: Remove item from cart
- `update_item_quantity(item_id, quantity) -> None`: Update item quantity
- `start_checkout() -> None`: Start checkout process
- `submit() -> None`: Submit cart for approval
- `approve(approved_by) -> None`: Approve cart
- `reject(reason) -> None`: Reject cart
- `confirm() -> None`: Confirm cart completion

**Business Rules**:
- Cart can only be edited in DRAFT or CHECKOUT states
- Cart must have items before submission
- Cart total calculated from item line totals

**Domain Events**:
- `CartCreated`, `CartItemAdded`, `CartItemRemoved`, `CartItemQuantityUpdated`
- `CartCheckoutStarted`, `CartSubmitted`, `CartCompleted`, `CartFailed`, `CartAbandoned`

### Checkout Aggregate

**Location**: Lines 600-1000+

**Purpose**: Checkout session aggregate root.

**Identity**: `CheckoutId` (typed ID)

**States**: `CheckoutStatus` enum (CREATED, QUOTED, AWAITING_APPROVAL, etc.)

**Properties**:
- `id: CheckoutId` - Unique identifier
- `offer_id: OfferId` - Associated offer
- `merchant_id: MerchantId` - Merchant
- `status: CheckoutStatus` - Current status
- `items: list[CheckoutItem]` - Checkout items
- `frozen_receipt: FrozenReceipt | None` - Frozen receipt for approval
- `approved_by: str | None` - Who approved
- `merchant_order_id: str | None` - Merchant's order ID
- `expires_at: datetime | None` - Expiration time

**Key Methods**:
- `create(offer_id, items, merchant_id) -> Checkout`: Factory method
- `set_quote(quote_response) -> None`: Set quote from merchant
- `request_approval() -> FrozenReceipt`: Request approval with frozen receipt
- `approve(approved_by) -> None`: Approve checkout
- `confirm(payment_method) -> None`: Confirm checkout

**Business Rules**:
- Checkout expires after timeout
- Price changes require reapproval
- Checkout must be approved before confirmation

**Domain Events**:
- `CheckoutCreated`, `CheckoutQuoted`, `CheckoutApprovalRequested`
- `CheckoutApproved`, `CheckoutConfirmed`, `CheckoutCancelled`, `CheckoutFailed`

### Order Aggregate

**Location**: Lines 1000-1300+

**Purpose**: Order aggregate root.

**Identity**: `OrderId` (typed ID)

**States**: `OrderStatus` enum (PENDING, CONFIRMED, SHIPPED, etc.)

**Properties**:
- `id: OrderId` - Unique identifier
- `checkout_id: CheckoutId` - Source checkout
- `merchant_id: MerchantId` - Merchant
- `status: OrderStatus` - Current status
- `customer: CustomerInfo` - Customer information
- `shipping_address: Address` - Shipping address
- `billing_address: Address | None` - Billing address
- `items: list[OrderItem]` - Order items
- `total: Money` - Total amount
- `merchant_order_id: str | None` - Merchant's order ID
- `tracking_number: str | None` - Tracking number
- `cancelled_reason: str | None` - Cancellation reason

**Key Methods**:
- `create(checkout_id, merchant_id, ...) -> Order`: Factory method
- `confirm(merchant_order_id) -> None`: Confirm order
- `ship(tracking_number, carrier) -> None`: Ship order
- `deliver() -> None`: Mark as delivered
- `cancel(reason, cancelled_by) -> None`: Cancel order
- `refund(amount, reason) -> None`: Refund order

**Business Rules**:
- Order can only be cancelled in cancellable states
- Order must be confirmed before shipping
- Order must be shipped before delivery

**Domain Events**:
- `OrderCreated`, `OrderConfirmed`, `OrderShipped`, `OrderDelivered`
- `OrderCancelled`, `OrderRefunded`

### Intent Aggregate

**Location**: Lines 1300-1500+

**Purpose**: Purchase intent aggregate root.

**Identity**: `IntentId` (typed ID)

**Properties**:
- `id: IntentId` - Unique identifier
- `query: str` - Search query
- `session_id: str | None` - Session identifier
- `metadata: dict[str, Any]` - Metadata
- `created_at: datetime` - Creation timestamp
- `updated_at: datetime` - Update timestamp

**Key Methods**:
- `create(query, session_id, metadata) -> Intent`: Factory method

**Domain Events**:
- `IntentCreated`

### Offer Aggregate

**Location**: Lines 1500-1700+

**Purpose**: Offer aggregate root.

**Identity**: `OfferId` (typed ID)

**Properties**:
- `id: OfferId` - Unique identifier
- `intent_id: IntentId` - Associated intent
- `merchant_id: MerchantId` - Merchant
- `items: list[OfferItem]` - Offer items
- `total: Money` - Total price
- `created_at: datetime` - Creation timestamp

**Key Methods**:
- `create(intent_id, merchant_id, items) -> Offer`: Factory method

**Domain Events**:
- `OffersCollected`

### Approval Aggregate

**Location**: Lines 1700-1951

**Purpose**: Approval request aggregate root.

**Identity**: `ApprovalId` (typed ID)

**States**: `ApprovalStatus` enum (PENDING, APPROVED, REJECTED, EXPIRED)

**Properties**:
- `id: ApprovalId` - Unique identifier
- `checkout_id: CheckoutId` - Associated checkout
- `status: ApprovalStatus` - Current status
- `requested_at: datetime` - Request timestamp
- `expires_at: datetime` - Expiration time
- `approved_by: str | None` - Who approved
- `rejected_by: str | None` - Who rejected
- `reason: str | None` - Rejection reason

**Key Methods**:
- `create(checkout_id, expires_at) -> Approval`: Factory method
- `approve(approved_by) -> None`: Approve request
- `reject(rejected_by, reason) -> None`: Reject request
- `expire() -> None`: Mark as expired

**Business Rules**:
- Approval expires after timeout
- Approval can only be acted upon if pending
- Approval cannot be changed after resolution

**Domain Events**:
- `ApprovalRequested`, `ApprovalGranted`, `ApprovalRejected`, `ApprovalExpired`

---

## Value Objects

### Money

**Location**: `app/domain/value_objects.py`

**Purpose**: Represents monetary amounts.

**Properties**:
- `amount_cents: int` - Amount in cents
- `currency: str` - Currency code

**Methods**:
- `zero(currency) -> Money`: Create zero amount
- `__add__`, `__sub__`, `__mul__`: Arithmetic operations

### Address

**Location**: `app/domain/value_objects.py`

**Purpose**: Represents shipping/billing address.

**Properties**:
- `line1: str` - Address line 1
- `line2: str | None` - Address line 2
- `city: str` - City
- `state: str | None` - State/province
- `postal_code: str` - Postal code
- `country: str` - Country code

### ProductRef

**Location**: `app/domain/value_objects.py`

**Purpose**: Reference to a product.

**Properties**:
- `product_id: ProductId` - Product identifier
- `name: str` - Product name
- `variant_id: str | None` - Variant identifier

### FrozenReceipt

**Location**: `app/domain/value_objects.py`

**Purpose**: Frozen receipt for approval.

**Properties**:
- `items: list[FrozenReceiptItem]` - Receipt items
- `subtotal_cents: int` - Subtotal
- `tax_cents: int` - Tax
- `shipping_cents: int` - Shipping
- `total_cents: int` - Total
- `currency: str` - Currency
- `receipt_hash: str` - Hash for validation

---

## Domain Events

### Event Types

**Location**: `app/domain/events.py`

**Cart Events**:
- `CartCreated`, `CartItemAdded`, `CartItemRemoved`, `CartItemQuantityUpdated`
- `CartCheckoutStarted`, `CartSubmitted`, `CartCompleted`, `CartFailed`, `CartAbandoned`

**Checkout Events**:
- `CheckoutCreated`, `CheckoutQuoted`, `CheckoutApprovalRequested`
- `CheckoutApproved`, `CheckoutConfirmed`, `CheckoutCancelled`, `CheckoutFailed`
- `CheckoutReapprovalRequired`

**Order Events**:
- `OrderCreated`, `OrderConfirmed`, `OrderShipped`, `OrderDelivered`
- `OrderCancelled`, `OrderRefunded`

**Approval Events**:
- `ApprovalRequested`, `ApprovalGranted`, `ApprovalRejected`, `ApprovalExpired`

### Event Structure

```python
@dataclass
class DomainEvent:
    aggregate_id: str
    aggregate_type: str
    event_type: str
    occurred_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)
```

---

## Business Rules

### Cart Rules

- Cart can only be edited in DRAFT or CHECKOUT states
- Cart must have items before submission
- Cart total calculated from item line totals
- Cart expires after inactivity timeout

### Checkout Rules

- Checkout expires after timeout
- Price changes require reapproval
- Checkout must be approved before confirmation
- Checkout can be cancelled in any non-terminal state

### Order Rules

- Order can only be cancelled in cancellable states
- Order must be confirmed before shipping
- Order must be shipped before delivery
- Order refunds only from DELIVERED or RETURNED states

### Approval Rules

- Approval expires after timeout
- Approval can only be acted upon if pending
- Approval cannot be changed after resolution

---

## Code Examples

### Creating a Cart

```python
from app.domain.entities import Cart
from app.domain.value_objects import MerchantId, ProductRef

cart = Cart.create(
    merchant_id=MerchantId("merchant-a"),
    session_id="session-123"
)

# Add items
product = ProductRef(
    product_id=ProductId("prod-123"),
    name="Product Name"
)
cart.add_item(product, quantity=2)

# Start checkout
cart.start_checkout()
```

### Creating a Checkout

```python
from app.domain.entities import Checkout
from app.domain.value_objects import OfferId, MerchantId

checkout = Checkout.create(
    offer_id=OfferId("offer-123"),
    items=[{"product_id": "prod-123", "quantity": 1}],
    merchant_id=MerchantId("merchant-a")
)

# Get quote
checkout.set_quote(quote_response)

# Request approval
frozen_receipt = checkout.request_approval()

# Approve
checkout.approve(approved_by="user-john")

# Confirm
checkout.confirm(payment_method="test_card")
```

### Creating an Order

```python
from app.domain.entities import Order
from app.domain.value_objects import CheckoutId, MerchantId, Money, Address, CustomerInfo

order = Order.create(
    checkout_id=CheckoutId("checkout-123"),
    merchant_id=MerchantId("merchant-a"),
    customer=CustomerInfo(email="user@example.com", name="John Doe"),
    shipping_address=Address(
        line1="123 Main St",
        city="New York",
        postal_code="10001",
        country="US"
    ),
    items=[...],
    total=Money(amount_cents=10000, currency="USD")
)

# Confirm order
order.confirm(merchant_order_id="merchant-order-456")

# Ship order
order.ship(tracking_number="1Z999AA10123456784", carrier="UPS")

# Deliver order
order.deliver()
```

---

## Summary

This detailed documentation covers all domain entities, their properties, methods, business rules, and domain events for developers working with the domain layer in CartPilot.
