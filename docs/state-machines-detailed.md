# State Machines - Detailed Component Documentation

> **Complete technical documentation for domain state machines**  
> This document provides comprehensive details for developers working with state machines in CartPilot.

## Table of Contents

1. [Overview](#overview)
2. [Architecture & Design](#architecture--design)
3. [State Machine Details](#state-machine-details)
4. [Transition Rules](#transition-rules)
5. [State Query Methods](#state-query-methods)
6. [Validation Functions](#validation-functions)
7. [Code Examples](#code-examples)

---

## Overview

### Purpose

State machines define deterministic state transitions for domain entities (Cart, Order, Checkout, Approval). They enforce business rules about what operations are valid in each state.

**Location**: `cartpilot-api/app/domain/state_machines.py`  
**Lines of Code**: ~563 lines  
**Dependencies**: Domain exceptions

### Responsibilities

- **State Definition**: Define valid states for entities
- **Transition Validation**: Enforce valid state transitions
- **Business Rules**: Encode business logic in state transitions
- **State Queries**: Provide query methods for state properties

### Key Metrics

- **State Machines**: 4 (Cart, Order, Checkout, Approval)
- **Total States**: 25+ states across all machines
- **Transition Rules**: Defined in transition dictionaries

---

## Architecture & Design

### State Machine Structure

```python
class CartStatus(str, Enum):
    """Cart lifecycle states."""
    
    DRAFT = "draft"
    CHECKOUT = "checkout"
    PENDING_APPROVAL = "pending_approval"
    REJECTED = "rejected"
    SUBMITTED = "submitted"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"
    
    def can_transition_to(self, target: "CartStatus") -> bool
    def allowed_transitions(self) -> list["CartStatus"]
    def is_editable(self) -> bool
    def is_terminal(self) -> bool
    def is_active(self) -> bool
```

### Design Patterns

1. **State Pattern**: Enum-based state representation
2. **State Machine Pattern**: Explicit transition rules
3. **Validation Pattern**: Transition validation functions

---

## State Machine Details

### Cart State Machine

**Location**: Lines 23-120

**States**:
- `DRAFT`: Initial state, cart can be edited
- `CHECKOUT`: Checkout process started
- `PENDING_APPROVAL`: Waiting for approval
- `REJECTED`: Approval rejected
- `SUBMITTED`: Approved and submitted
- `COMPLETED`: Order completed
- `FAILED`: Order failed
- `ABANDONED`: Cart abandoned

**State Diagram**:
```
DRAFT ──────────────────┬──────────────────────► ABANDONED
  │                     │
  │ start_checkout      │ expire
  ▼                     │
CHECKOUT ───────────────┤
  │                     │
  │ submit              │
  ▼                     │
PENDING_APPROVAL ───────┤
  │       │             │
  │       │ reject      │
  │       ▼             │
  │     REJECTED ───────┘
  │
  │ approve
  ▼
SUBMITTED ──────────────┬──────────────────────► FAILED
  │                     │
  │ confirm             │ fail
  ▼                     │
COMPLETED ◄─────────────┘
```

**Query Methods**:
- `is_editable()`: Returns `True` for DRAFT, CHECKOUT
- `is_terminal()`: Returns `True` for COMPLETED, FAILED, ABANDONED, REJECTED
- `is_active()`: Returns `True` for non-terminal states

### Order State Machine

**Location**: Lines 125-205

**States**:
- `PENDING`: Order created, awaiting confirmation
- `CONFIRMED`: Order confirmed by merchant
- `SHIPPED`: Order shipped
- `DELIVERED`: Order delivered
- `CANCELLED`: Order cancelled
- `REFUNDED`: Order refunded
- `RETURNED`: Order returned

**State Diagram**:
```
PENDING ────────────────┬──────────────────────► CANCELLED
  │                      │
  │ confirm              │ cancel
  ▼                      │
CONFIRMED ───────────────┤
  │       │              │
  │       │ cancel       │
  │ ship  │              │
  ▼       ▼              │
SHIPPED ─────────────────┤
  │       │              │
  │       │ cancel       │
  │ deliver              │
  ▼       ▼              │
DELIVERED ───────────────┤
  │       │              │
  │       │ refund       │
  │ return               │
  ▼       ▼              │
RETURNED ────────────────┘
  │
  │ refund
  ▼
REFUNDED
```

**Query Methods**:
- `is_cancellable()`: Returns `True` for PENDING, CONFIRMED, SHIPPED
- `is_terminal()`: Returns `True` for CANCELLED, REFUNDED
- `is_fulfillable()`: Returns `True` for PENDING, CONFIRMED, SHIPPED

### Checkout State Machine

**Location**: Lines 290-380

**States**:
- `CREATED`: Checkout created
- `QUOTED`: Quote received
- `AWAITING_APPROVAL`: Waiting for approval
- `APPROVED`: Approved
- `CONFIRMED`: Confirmed and order created
- `CANCELLED`: Cancelled
- `EXPIRED`: Expired
- `FAILED`: Failed

**State Diagram**:
```
CREATED ────────────────┬──────────────────────► CANCELLED
  │                      │
  │ get_quote            │ cancel
  ▼                      │
QUOTED ──────────────────┤
  │       │              │
  │       │ cancel       │
  │ request_approval     │
  ▼       ▼              │
AWAITING_APPROVAL ────────┤
  │       │              │
  │       │ reject       │
  │ approve              │
  ▼       ▼              │
APPROVED ─────────────────┤
  │       │              │
  │       │ cancel       │
  │ confirm              │
  ▼       ▼              │
CONFIRMED ───────────────┘
```

**Query Methods**:
- `is_expired()`: Returns `True` for EXPIRED
- `is_confirmable()`: Returns `True` for APPROVED
- `requires_reapproval()`: Returns `True` if price changed

### Approval State Machine

**Location**: Lines 213-283

**States**:
- `PENDING`: Approval requested
- `APPROVED`: Approval granted
- `REJECTED`: Approval rejected
- `EXPIRED`: Approval expired

**State Diagram**:
```
PENDING ──────────────────────────────────► EXPIRED
  │           │
  │ approve   │ reject
  ▼           ▼
APPROVED    REJECTED
```

**Query Methods**:
- `is_terminal()`: Returns `True` for APPROVED, REJECTED, EXPIRED
- `is_resolved()`: Returns `True` for APPROVED, REJECTED
- `is_actionable()`: Returns `True` for PENDING

---

## Transition Rules

### Cart Transitions

**Location**: Lines 102-119

```python
_CART_TRANSITIONS = {
    CartStatus.DRAFT: {CartStatus.CHECKOUT, CartStatus.ABANDONED},
    CartStatus.CHECKOUT: {CartStatus.PENDING_APPROVAL, CartStatus.ABANDONED},
    CartStatus.PENDING_APPROVAL: {CartStatus.SUBMITTED, CartStatus.REJECTED, CartStatus.ABANDONED},
    CartStatus.REJECTED: set(),  # Terminal
    CartStatus.SUBMITTED: {CartStatus.COMPLETED, CartStatus.FAILED},
    CartStatus.COMPLETED: set(),  # Terminal
    CartStatus.FAILED: set(),  # Terminal
    CartStatus.ABANDONED: set(),  # Terminal
}
```

### Order Transitions

**Location**: Lines 190-205

```python
_ORDER_TRANSITIONS = {
    OrderStatus.PENDING: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED, OrderStatus.CANCELLED},
    OrderStatus.DELIVERED: {OrderStatus.RETURNED, OrderStatus.REFUNDED},
    OrderStatus.RETURNED: {OrderStatus.REFUNDED},
    OrderStatus.CANCELLED: set(),  # Terminal
    OrderStatus.REFUNDED: set(),  # Terminal
}
```

### Checkout Transitions

**Location**: Lines 360-380

```python
_CHECKOUT_TRANSITIONS = {
    CheckoutStatus.CREATED: {CheckoutStatus.QUOTED, CheckoutStatus.CANCELLED, CheckoutStatus.EXPIRED},
    CheckoutStatus.QUOTED: {CheckoutStatus.AWAITING_APPROVAL, CheckoutStatus.CANCELLED, CheckoutStatus.EXPIRED},
    CheckoutStatus.AWAITING_APPROVAL: {CheckoutStatus.APPROVED, CheckoutStatus.CANCELLED, CheckoutStatus.EXPIRED},
    CheckoutStatus.APPROVED: {CheckoutStatus.CONFIRMED, CheckoutStatus.CANCELLED, CheckoutStatus.EXPIRED},
    CheckoutStatus.CONFIRMED: set(),  # Terminal
    CheckoutStatus.CANCELLED: set(),  # Terminal
    CheckoutStatus.EXPIRED: set(),  # Terminal
    CheckoutStatus.FAILED: set(),  # Terminal
}
```

### Approval Transitions

**Location**: Lines 277-282

```python
_APPROVAL_TRANSITIONS = {
    ApprovalStatus.PENDING: {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED, ApprovalStatus.EXPIRED},
    ApprovalStatus.APPROVED: set(),  # Terminal
    ApprovalStatus.REJECTED: set(),  # Terminal
    ApprovalStatus.EXPIRED: set(),  # Terminal
}
```

---

## State Query Methods

### can_transition_to

**Purpose**: Check if transition to target state is valid.

**Implementation**: Checks if target is in allowed transitions set

**Example**:
```python
if order.status.can_transition_to(OrderStatus.SHIPPED):
    # Transition is valid
    order.status = OrderStatus.SHIPPED
```

### allowed_transitions

**Purpose**: Get list of valid target states.

**Returns**: List of states that can be transitioned to

**Example**:
```python
allowed = checkout.status.allowed_transitions()
# Returns: [CheckoutStatus.CONFIRMED, CheckoutStatus.CANCELLED, CheckoutStatus.EXPIRED]
```

### is_terminal

**Purpose**: Check if state is terminal (no further transitions).

**Returns**: `True` if no further transitions are possible

**Example**:
```python
if order.status.is_terminal():
    # Order is in final state
    return
```

### Entity-Specific Queries

**Cart**:
- `is_editable()`: Can cart be modified?
- `is_active()`: Is cart still active?

**Order**:
- `is_cancellable()`: Can order be cancelled?
- `is_fulfillable()`: Is order in fulfillable state?

**Checkout**:
- `is_expired()`: Is checkout expired?
- `is_confirmable()`: Can checkout be confirmed?
- `requires_reapproval()`: Does checkout require reapproval?

**Approval**:
- `is_resolved()`: Has approval been resolved?
- `is_actionable()`: Can approval be acted upon?

---

## Validation Functions

### validate_cart_transition

**Location**: Lines 122-130

**Purpose**: Validate cart state transition.

**Raises**: `InvalidStateTransitionError` if transition is invalid

**Example**:
```python
validate_cart_transition(CartStatus.DRAFT, CartStatus.CHECKOUT)  # OK
validate_cart_transition(CartStatus.DRAFT, CartStatus.COMPLETED)  # Raises error
```

### validate_order_transition

**Location**: Lines 207-215

**Purpose**: Validate order state transition.

**Raises**: `InvalidStateTransitionError` if transition is invalid

### validate_checkout_transition

**Location**: Lines 382-390

**Purpose**: Validate checkout state transition.

**Raises**: `InvalidStateTransitionError` if transition is invalid

### validate_approval_transition

**Location**: Lines 284-292

**Purpose**: Validate approval state transition.

**Raises**: `InvalidStateTransitionError` if transition is invalid

---

## Code Examples

### Checking Valid Transitions

```python
from app.domain.state_machines import OrderStatus

order_status = OrderStatus.PENDING

# Check if transition is valid
if order_status.can_transition_to(OrderStatus.CONFIRMED):
    print("Can transition to CONFIRMED")
else:
    print("Cannot transition to CONFIRMED")

# Get all allowed transitions
allowed = order_status.allowed_transitions()
print(f"Allowed transitions: {[s.value for s in allowed]}")
```

### Using State Query Methods

```python
# Check if cart can be edited
if cart.status.is_editable():
    cart.add_item(product, quantity=1)

# Check if order can be cancelled
if order.status.is_cancellable():
    await order_service.cancel_order(order_id, reason="Customer request")

# Check if checkout is expired
if checkout.status.is_expired():
    raise CheckoutExpiredError("Checkout has expired")
```

### Validating Transitions

```python
from app.domain.state_machines import validate_order_transition
from app.domain.exceptions import InvalidStateTransitionError

try:
    validate_order_transition(OrderStatus.PENDING, OrderStatus.SHIPPED)
except InvalidStateTransitionError:
    print("Invalid transition: PENDING → SHIPPED")
    print("Must transition through CONFIRMED first")
```

---

## Summary

This detailed documentation covers all state machines, transition rules, query methods, and validation functions for developers working with domain state management in CartPilot.
