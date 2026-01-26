# OrderService - Detailed Component Documentation

> **Complete technical documentation for the OrderService component**  
> This document provides comprehensive details for developers working with or extending the order service.

## Table of Contents

1. [Overview](#overview)
2. [Architecture & Design](#architecture--design)
3. [Component Details](#component-details)
4. [Workflow Diagrams](#workflow-diagrams)
5. [API Reference](#api-reference)
6. [Business Logic & Rules](#business-logic--rules)
7. [Implementation Details](#implementation-details)
8. [Error Handling](#error-handling)
9. [Performance Considerations](#performance-considerations)
10. [Security Considerations](#security-considerations)
11. [Testing Strategy](#testing-strategy)
12. [Extension Points](#extension-points)
13. [Troubleshooting](#troubleshooting)
14. [Code Examples](#code-examples)

---

## Overview

### Purpose

The `OrderService` orchestrates order lifecycle management in CartPilot. It handles order creation from confirmed checkouts, tracks status transitions, processes merchant webhook events, and supports simulate_time functionality for testing.

**Location**: `cartpilot-api/app/application/order_service.py`  
**Lines of Code**: ~755 lines  
**Dependencies**: Repository pattern, domain state machines

### Responsibilities

- **Order Lifecycle Management**: Create orders from confirmed checkouts
- **Status Tracking**: Track order status transitions (pending → confirmed → shipped → delivered)
- **Webhook Integration**: Handle order events from merchants
- **Testing Support**: Simulate order advancement for testing
- **Cancellation & Refunds**: Handle order cancellation and refund flows

### Key Metrics

- **Public Methods**: 9 main operations
- **State Transitions**: 7 order states (PENDING, CONFIRMED, SHIPPED, DELIVERED, CANCELLED, REFUNDED, RETURNED)
- **Result Types**: 4 typed result dataclasses
- **DTOs**: OrderDTO, OrderItemDTO, AddressDTO, CustomerDTO

---

## Architecture & Design

### Class Structure

```python
class OrderService:
    """Application service for managing orders."""
    
    def __init__(
        self,
        order_repo: OrderRepository | None = None,
        request_id: str | None = None,
    ) -> None
    
    # Main operations
    async def create_order_from_checkout(...) -> CreateOrderResult
    async def get_order(order_id: str) -> GetOrderResult
    async def get_order_by_merchant_order_id(...) -> GetOrderResult
    async def list_orders(...) -> ListOrdersResult
    async def confirm_order(...) -> UpdateOrderResult
    async def ship_order(...) -> UpdateOrderResult
    async def deliver_order(...) -> UpdateOrderResult
    async def cancel_order(...) -> UpdateOrderResult
    async def refund_order(...) -> UpdateOrderResult
    async def simulate_advance_order(...) -> UpdateOrderResult
    
    # Private helpers
    async def _transition_order(...) -> UpdateOrderResult
    async def _ship_simulated(...) -> UpdateOrderResult
```

### Dependency Graph

```
OrderService
├── OrderRepository (in-memory, singleton)
│   ├── _orders: dict[str, OrderDTO]
│   ├── _by_checkout_id: dict[str, str]
│   └── _by_merchant_order_id: dict[str, str]
└── Domain State Machines
    └── OrderStatus (enum with transition rules)
```

### Design Patterns

1. **Repository Pattern**: Abstract data access through `OrderRepository`
2. **Service Layer Pattern**: Encapsulates business logic and orchestration
3. **Result Pattern**: Returns structured results with success/error states
4. **DTO Pattern**: Uses Data Transfer Objects (OrderDTO, OrderItemDTO)
5. **State Machine Pattern**: Enforces valid state transitions via `OrderStatus`
6. **Template Method Pattern**: `_transition_order` implements common transition logic

---

## Component Details

### OrderRepository

**Location**: Lines 164-226 in `order_service.py`

**Purpose**: In-memory storage for orders (temporary implementation, will be replaced with database).

**Storage Structure**:
```python
class OrderRepository:
    def __init__(self) -> None:
        self._orders: dict[str, OrderDTO] = {}
        self._by_checkout_id: dict[str, str] = {}
        self._by_merchant_order_id: dict[str, str] = {}
```

**Methods**:

- `save(order: OrderDTO) -> None`
  - Persists order to `_orders` dict
  - Indexes by checkout_id and merchant_order_id
  - Key: `order.id`, Value: `OrderDTO`

- `get(order_id: str) -> OrderDTO | None`
  - Retrieves order by ID
  - Returns `None` if not found

- `get_by_checkout_id(checkout_id: str) -> OrderDTO | None`
  - Looks up order by checkout ID (for idempotency)

- `get_by_merchant_order_id(merchant_id: str, merchant_order_id: str) -> OrderDTO | None`
  - Looks up order by merchant's order ID
  - Key format: `f"{merchant_id}:{merchant_order_id}"`

- `list_all(page, page_size, status, merchant_id) -> tuple[list[OrderDTO], int]`
  - Returns paginated list with filtering
  - Sorted by `created_at` (descending)

**Singleton Pattern**: Global instance via `get_order_repository()`

**Future Migration**: Will be replaced with SQLAlchemy repository using PostgreSQL.

### Result Types

**Location**: Lines 117-157

```python
@dataclass
class CreateOrderResult:
    order: OrderDTO | None = None
    success: bool = True
    error: str | None = None
    error_code: str | None = None

@dataclass
class GetOrderResult:
    order: OrderDTO | None = None
    success: bool = True
    error: str | None = None
    error_code: str | None = None

@dataclass
class UpdateOrderResult:
    order: OrderDTO | None = None
    success: bool = True
    error: str | None = None
    error_code: str | None = None

@dataclass
class ListOrdersResult:
    orders: list[OrderDTO] = field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    success: bool = True
    error: str | None = None
```

### Data Transfer Objects

**OrderDTO** (Lines 67-97):
- Complete order representation
- Includes customer, addresses, items, pricing
- Status history tracking
- Timestamps for all lifecycle events

**OrderItemDTO** (Lines 27-42):
- Product information
- Quantity and pricing
- Line total calculation

**AddressDTO** (Lines 45-54):
- Shipping/billing address
- Validation in domain layer

**CustomerDTO** (Lines 57-63):
- Customer information
- Email, name, phone

---

## Workflow Diagrams

### Order Creation Flow

```
┌─────────┐      ┌──────────────┐      ┌──────────┐
│ Checkout│      │ OrderService │      │   Order  │
└────┬────┘      └──────┬───────┘      └────┬─────┘
     │                  │                    │
     │ 1. confirm()     │                    │
     │    (status: CONFIRMED)                │
     │                  │                    │
     │ 2. create_order_from_checkout()       │
     ├─────────────────>│                    │
     │                  │                    │
     │                  │ 3. Check idempotency│
     │                  │    (by checkout_id) │
     │                  │                    │
     │                  │ 4. Create OrderDTO │
     │                  │    (status: PENDING)│
     │                  │                    │
     │                  │ 5. Initialize status history│
     │                  │                    │
     │                  │ 6. Save to repo    │
     │                  │                    │
     │                  │ 7. Return order ID │
     │                  ├───────────────────>│
     │                  │                    │
     │ 8. Return order ID                    │
     │<──────────────────┤                    │
```

### Order Status Transition Flow

```
┌─────────┐      ┌──────────────┐      ┌──────────┐
│  Agent  │      │ OrderService │      │   Order  │
└────┬────┘      └──────┬───────┘      └────┬─────┘
     │                  │                    │
     │ 1. confirm_order()                    │
     │─────────────────>│                    │
     │                  │                    │
     │                  │ 2. Get order       │
     │                  ├───────────────────>│
     │                  │                    │
     │                  │ 3. Validate transition│
     │                  │    (status.can_transition_to)│
     │                  │                    │
     │                  │ 4. Apply updates   │
     │                  │    (set confirmed_at)│
     │                  │                    │
     │                  │ 5. Update status   │
     │                  │    (PENDING → CONFIRMED)│
     │                  │                    │
     │                  │ 6. Add to history  │
     │                  │                    │
     │                  │ 7. Save order      │
     │                  ├───────────────────>│
     │                  │                    │
     │ 8. Return updated order               │
     │<──────────────────┤                    │
```

---

## API Reference

### create_order_from_checkout

**Method**: `async def create_order_from_checkout(...)`

**Purpose**: Create an order from a confirmed checkout (called by checkout_service).

**Parameters**:
- `checkout_id: str` - Source checkout ID
- `merchant_id: str` - Merchant fulfilling the order
- `merchant_order_id: str` - Merchant's order reference
- `customer: CustomerDTO` - Customer information
- `shipping_address: AddressDTO` - Shipping address
- `billing_address: AddressDTO | None` - Billing address
- `items: list[OrderItemDTO]` - Order items
- `subtotal_cents: int` - Subtotal in cents
- `tax_cents: int` - Tax in cents
- `shipping_cents: int` - Shipping in cents
- `total_cents: int` - Total in cents
- `currency: str` - Currency code (default: "USD")

**Returns**: `CreateOrderResult`

**Idempotency**: Checks if order already exists for checkout_id (line 312-319)

**Example**:
```python
result = await service.create_order_from_checkout(
    checkout_id="checkout-123",
    merchant_id="merchant-a",
    merchant_order_id="merchant-order-456",
    customer=CustomerDTO(email="user@example.com", name="John Doe"),
    shipping_address=AddressDTO(
        line1="123 Main St",
        city="New York",
        postal_code="10001",
        country="US",
        state="NY"
    ),
    items=[
        OrderItemDTO(
            product_id="prod-789",
            title="Product Name",
            quantity=2,
            unit_price_cents=5000
        )
    ],
    subtotal_cents=10000,
    tax_cents=800,
    shipping_cents=500,
    total_cents=11300
)

if result.success:
    order = result.order
    print(f"Order created: {order.id}")
    print(f"Status: {order.status}")  # PENDING
```

**Error Codes**:
- `CREATE_FAILED`: Unexpected error during creation (line 375)

**State After**: `OrderStatus.PENDING`

### confirm_order

**Method**: `async def confirm_order(...) -> UpdateOrderResult`

**Purpose**: Transition order from PENDING to CONFIRMED.

**Parameters**:
- `order_id: str` - Order identifier
- `merchant_order_id: str | None` - Updated merchant order ID (optional)
- `actor: str` - Who initiated (default: "merchant")

**Returns**: `UpdateOrderResult`

**State Transition**: `PENDING` → `CONFIRMED`

**Example**:
```python
result = await service.confirm_order(
    order_id="order-123",
    merchant_order_id="merchant-order-456",
    actor="merchant_webhook"
)

if result.success:
    order = result.order
    print(f"Confirmed at: {order.confirmed_at}")
    print(f"Status: {order.status}")  # CONFIRMED
```

**Error Codes**:
- `ORDER_NOT_FOUND`: Order doesn't exist
- `INVALID_TRANSITION`: Invalid state transition

### ship_order

**Method**: `async def ship_order(...) -> UpdateOrderResult`

**Purpose**: Mark order as shipped with tracking information.

**Parameters**:
- `order_id: str` - Order identifier
- `tracking_number: str | None` - Tracking number (optional)
- `carrier: str | None` - Carrier name (optional)
- `actor: str` - Who initiated (default: "merchant")

**Returns**: `UpdateOrderResult`

**State Transition**: `CONFIRMED` → `SHIPPED`

**Example**:
```python
result = await service.ship_order(
    order_id="order-123",
    tracking_number="1Z999AA10123456784",
    carrier="UPS",
    actor="merchant_webhook"
)

if result.success:
    order = result.order
    print(f"Shipped at: {order.shipped_at}")
    print(f"Tracking: {order.tracking_number}")
```

### deliver_order

**Method**: `async def deliver_order(...) -> UpdateOrderResult`

**Purpose**: Mark order as delivered.

**Parameters**:
- `order_id: str` - Order identifier
- `actor: str` - Who initiated (default: "merchant")

**Returns**: `UpdateOrderResult`

**State Transition**: `SHIPPED` → `DELIVERED`

### cancel_order

**Method**: `async def cancel_order(...) -> UpdateOrderResult`

**Purpose**: Cancel an order.

**Parameters**:
- `order_id: str` - Order identifier
- `reason: str` - Cancellation reason
- `cancelled_by: str` - Who cancelled (default: "customer")

**Returns**: `UpdateOrderResult`

**State Transition**: `PENDING/CONFIRMED/SHIPPED` → `CANCELLED`

**Cancellable States**: Only if `status.is_cancellable()` returns True

### refund_order

**Method**: `async def refund_order(...) -> UpdateOrderResult`

**Purpose**: Refund an order (full or partial).

**Parameters**:
- `order_id: str` - Order identifier
- `refund_amount_cents: int | None` - Refund amount (None for full refund)
- `reason: str` - Refund reason (default: "")
- `actor: str` - Who initiated (default: "system")

**Returns**: `UpdateOrderResult`

**State Transition**: `DELIVERED` → `REFUNDED`

**Refund Logic**: If `refund_amount_cents` is None → full refund (order.total_cents)

### simulate_advance_order

**Method**: `async def simulate_advance_order(...) -> UpdateOrderResult`

**Purpose**: Advance order through lifecycle for testing.

**Parameters**:
- `order_id: str` - Order identifier
- `steps: int` - Number of steps to advance (default: 1)

**Returns**: `UpdateOrderResult`

**Progression Sequence**:
1. `PENDING` → `CONFIRMED`
2. `CONFIRMED` → `SHIPPED` (with simulated tracking)
3. `SHIPPED` → `DELIVERED`

**Simulated Tracking**: Automatically generates tracking number format `SIM{hex8}`

---

## Business Logic & Rules

### State Machine Rules

**Valid State Transitions**:
- PENDING → CONFIRMED, CANCELLED
- CONFIRMED → SHIPPED, CANCELLED
- SHIPPED → DELIVERED, CANCELLED
- DELIVERED → RETURNED, REFUNDED
- RETURNED → REFUNDED
- CANCELLED: Terminal
- REFUNDED: Terminal

**State Query Methods**:
- `is_cancellable()`: Returns `True` for PENDING, CONFIRMED, SHIPPED
- `is_terminal()`: Returns `True` for CANCELLED, REFUNDED
- `is_fulfillable()`: Returns `True` for PENDING, CONFIRMED, SHIPPED

**Transition Validation**: All transitions validated via `order.status.can_transition_to(target_status)`

### Status History

Every status transition adds entry to `order.status_history`:
```python
{
    "from_status": "pending",
    "to_status": "confirmed",
    "reason": "Order confirmed by merchant",
    "actor": "merchant_webhook",
    "metadata": {"merchant_order_id": "..."},
    "created_at": "2024-01-01T12:00:00Z"
}
```

### Idempotency Rules

**Order Creation**: Checked by `checkout_id`. If order exists for checkout → returns existing order.

---

## Implementation Details

### Transition Helper Method

**`_transition_order`** (Lines 667-738): Central method for all status transitions.

**Flow**:
1. Get order from repository
2. Validate transition (`order.status.can_transition_to(target_status)`)
3. Apply custom updates via `update_fn`
4. Update status
5. Add to status history
6. Save order
7. Log transition

### Simulate Advance Implementation

**Progression Array** (Lines 629-633):
```python
progression = [
    (OrderStatus.PENDING, OrderStatus.CONFIRMED, self.confirm_order),
    (OrderStatus.CONFIRMED, OrderStatus.SHIPPED, self._ship_simulated),
    (OrderStatus.SHIPPED, OrderStatus.DELIVERED, self.deliver_order),
]
```

**Algorithm**: Loop `steps` times, find current status in progression, call handler, stop if no more transitions.

---

## Code Examples

### Complete Order Lifecycle

```python
service = get_order_service()

# Create order
create_result = await service.create_order_from_checkout(...)
order_id = create_result.order.id

# Confirm
confirm_result = await service.confirm_order(order_id, actor="merchant_webhook")

# Ship
ship_result = await service.ship_order(
    order_id,
    tracking_number="1Z999AA10123456784",
    carrier="UPS"
)

# Deliver
deliver_result = await service.deliver_order(order_id)
```

### Simulate Order Advancement

```python
# Advance order through complete lifecycle
result = await service.simulate_advance_order(order_id, steps=3)
# PENDING → CONFIRMED → SHIPPED → DELIVERED
```

---

## Summary

This detailed documentation covers order lifecycle management, status transitions, error handling, and extension points for developers working with the OrderService component.
