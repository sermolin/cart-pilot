# CheckoutService - Detailed Component Documentation

> **Complete technical documentation for the CheckoutService component**  
> This document provides comprehensive details for developers working with or extending the checkout service.

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

The `CheckoutService` is the core orchestration component for the checkout approval workflow in CartPilot. It coordinates the complete flow from checkout creation to purchase confirmation, handling merchant communication, price validation, approval workflows, and state management.

**Location**: `cartpilot-api/app/application/checkout_service.py`  
**Lines of Code**: ~754 lines  
**Dependencies**: 5 external dependencies

### Responsibilities

- **Checkout Lifecycle Management**: Create, update, and transition checkout states
- **Merchant Integration**: Communicate with merchant services for quotes and confirmations
- **Price Change Detection**: Detect and handle price changes between quote and confirmation
- **Approval Workflow**: Manage the approval flow with frozen receipts
- **Idempotency**: Ensure safe retries and prevent duplicate operations
- **State Machine Enforcement**: Enforce valid state transitions

### Key Metrics

- **Public Methods**: 6 main operations
- **State Transitions**: 5 checkout states (CREATED, QUOTED, AWAITING_APPROVAL, APPROVED, CONFIRMED)
- **Error Types**: 8 domain exceptions
- **Result Types**: 5 typed result dataclasses

---

## Architecture & Design

### Class Structure

```python
class CheckoutService:
    """Application service for managing checkout approval flow."""
    
    def __init__(
        self,
        checkout_repo: CheckoutRepository | None = None,
        offer_repo: Any | None = None,
        request_id: str | None = None,
    ) -> None
    
    # Main operations
    async def create_checkout(
        self,
        offer_id: str,
        items: list[dict[str, Any]],
        idempotency_key: str | None = None,
    ) -> CreateCheckoutResult
    
    async def get_quote(
        self,
        checkout_id: str,
        items: list[dict[str, Any]],
        customer_email: str | None = None,
    ) -> QuoteCheckoutResult
    
    async def request_approval(
        self,
        checkout_id: str,
    ) -> RequestApprovalResult
    
    async def approve(
        self,
        checkout_id: str,
        approved_by: str,
    ) -> ApproveCheckoutResult
    
    async def confirm(
        self,
        checkout_id: str,
        payment_method: str = "test_card",
        idempotency_key: str | None = None,
    ) -> ConfirmCheckoutResult
    
    async def get_checkout(self, checkout_id: str) -> Checkout | None
    
    # Private helpers
    async def _create_order_from_checkout(self, checkout: Checkout) -> str | None
```

### Dependency Graph

```
CheckoutService
├── CheckoutRepository (in-memory, singleton)
│   ├── _checkouts: dict[str, Checkout]
│   └── _by_idempotency_key: dict[str, str]
├── OfferRepository (from intent_service, optional)
├── MerchantClientFactory (context manager)
│   └── MerchantClient (per merchant)
└── Domain Entities
    ├── Checkout (AggregateRoot)
    ├── CheckoutItem
    ├── Offer
    └── FrozenReceipt (ValueObject)
```

### Design Patterns

1. **Repository Pattern**: Abstract data access through `CheckoutRepository`
2. **Service Layer Pattern**: Encapsulates business logic and orchestration
3. **Result Pattern**: Returns structured results with success/error states
4. **Factory Pattern**: Uses `MerchantClientFactory` for merchant clients
5. **State Machine Pattern**: Enforces valid state transitions via `CheckoutStatus`
6. **Context Manager Pattern**: MerchantClientFactory used as async context manager

---

## Component Details

### CheckoutRepository

**Location**: Lines 41-86 in `checkout_service.py`

**Purpose**: In-memory storage for checkout sessions (temporary implementation, will be replaced with database).

**Storage Structure**:
```python
class CheckoutRepository:
    def __init__(self) -> None:
        self._checkouts: dict[str, Checkout] = {}
        self._by_idempotency_key: dict[str, str] = {}
```

**Methods**:

- `save(checkout: Checkout) -> None`
  - Persists checkout to `_checkouts` dict
  - Indexes by idempotency key if present
  - Key: `str(checkout.id)`, Value: `Checkout` entity

- `get(checkout_id: str) -> Checkout | None`
  - Retrieves checkout by ID
  - Returns `None` if not found

- `get_by_idempotency_key(key: str) -> Checkout | None`
  - Looks up checkout by idempotency key
  - Returns `None` if key not found

- `list_all(page: int = 1, page_size: int = 20) -> tuple[list[Checkout], int]`
  - Returns paginated list sorted by `created_at` (descending)
  - Returns tuple: `(checkouts, total_count)`

**Singleton Pattern**: Global instance via `get_checkout_repository()`

**Future Migration**: Will be replaced with SQLAlchemy repository using PostgreSQL.

### Result Types

**Location**: Lines 94-146

Each operation returns a typed result object:

```python
@dataclass
class CreateCheckoutResult:
    checkout: Checkout | None = None
    success: bool = True
    error: str | None = None
    error_code: str | None = None

@dataclass
class QuoteCheckoutResult:
    checkout: Checkout | None = None
    success: bool = True
    error: str | None = None
    error_code: str | None = None
    reapproval_required: bool = False  # Price change detected

@dataclass
class RequestApprovalResult:
    checkout: Checkout | None = None
    frozen_receipt: FrozenReceipt | None = None
    success: bool = True
    error: str | None = None
    error_code: str | None = None

@dataclass
class ApproveCheckoutResult:
    checkout: Checkout | None = None
    success: bool = True
    error: str | None = None
    error_code: str | None = None

@dataclass
class ConfirmCheckoutResult:
    checkout: Checkout | None = None
    merchant_order_id: str | None = None
    order_id: str | None = None
    success: bool = True
    error: str | None = None
    error_code: str | None = None
    reapproval_required: bool = False  # Price change detected
```

**Usage Pattern**:
```python
result = await service.create_checkout(...)
if result.success:
    checkout = result.checkout
else:
    # Handle error
    error_code = result.error_code
    error_message = result.error
```

---

## Workflow Diagrams

### Complete Checkout Flow

```
┌─────────┐      ┌──────────────┐      ┌──────────┐      ┌──────────┐
│  Agent  │      │ CheckoutSvc  │      │ Merchant │      │   Order  │
└────┬────┘      └──────┬───────┘      └────┬─────┘      └────┬─────┘
     │                  │                    │                 │
     │ 1. create_checkout                    │                 │
     ├─────────────────>│                    │                 │
     │                  │                    │                 │
     │                  │ 2. Check idempotency│                 │
     │                  │    (if key exists) │                 │
     │                  │                    │                 │
     │                  │ 3. Get offer       │                 │
     │                  │    (determine merchant)               │
     │                  │                    │                 │
     │                  │ 4. Create Checkout │                 │
     │                  │    (status: CREATED)                 │
     │                  │                    │                 │
     │                  │ 5. Save to repo    │                 │
     │                  │                    │                 │
     │ 6. Return checkout                    │                 │
     │<──────────────────┤                    │                 │
     │                  │                    │                 │
     │ 7. get_quote                          │                 │
     │─────────────────>│                    │                 │
     │                  │                    │                 │
     │                  │ 8. Validate state  │                 │
     │                  │    (must be CREATED or QUOTED)        │
     │                  │                    │                 │
     │                  │ 9. POST /checkout/quote              │
     │                  ├───────────────────>│                 │
     │                  │                    │                 │
     │                  │ 10. Quote Response │                 │
     │                  │     (items, prices)│                 │
     │                  │<───────────────────┤                 │
     │                  │                    │                 │
     │                  │ 11. Convert to CheckoutItems          │
     │                  │                    │                 │
     │                  │ 12. Check price change               │
     │                  │     (if reapproval state)            │
     │                  │                    │                 │
     │                  │ 13. checkout.set_quote()             │
     │                  │     (status: QUOTED)                │
     │                  │                    │                 │
     │                  │ 14. Save checkout  │                 │
     │                  │                    │                 │
     │ 15. Return quoted checkout            │                 │
     │<──────────────────┤                    │                 │
     │                  │                    │                 │
     │ 16. request_approval                   │                 │
     │─────────────────>│                    │                 │
     │                  │                    │                 │
     │                  │ 17. checkout.request_approval()      │
     │                  │     (freeze receipt)                 │
     │                  │     (status: AWAITING_APPROVAL)       │
     │                  │                    │                 │
     │                  │ 18. Save checkout  │                 │
     │                  │                    │                 │
     │ 19. Return frozen receipt              │                 │
     │<──────────────────┤                    │                 │
     │                  │                    │                 │
     │ 20. approve                            │                 │
     │─────────────────>│                    │                 │
     │                  │                    │                 │
     │                  │ 21. checkout.approve(approved_by)     │
     │                  │     (status: APPROVED)                │
     │                  │                    │                 │
     │                  │ 22. Save checkout  │                 │
     │                  │                    │                 │
     │ 23. Return approved checkout           │                 │
     │<──────────────────┤                    │                 │
     │                  │                    │                 │
     │ 24. confirm                            │                 │
     │─────────────────>│                    │                 │
     │                  │                    │                 │
     │                  │ 25. Check if already confirmed       │
     │                  │     (idempotency)   │                 │
     │                  │                    │                 │
     │                  │ 26. Check if approved                │
     │                  │                    │                 │
     │                  │ 27. Check price change               │
     │                  │     (requires_reapproval)            │
     │                  │                    │                 │
     │                  │ 28. POST /checkout/{id}/confirm      │
     │                  ├───────────────────>│                 │
     │                  │                    │                 │
     │                  │ 29. Order created  │                 │
     │                  │     (merchant_order_id)               │
     │                  │<───────────────────┤                 │
     │                  │                    │                 │
     │                  │ 30. checkout.confirm()               │
     │                  │     (status: CONFIRMED)              │
     │                  │                    │                 │
     │                  │ 31. Save checkout  │                 │
     │                  │                    │                 │
     │                  │ 32. Create Order  │                 │
     │                  ├─────────────────────────────────────>│
     │                  │                    │                 │
     │                  │ 33. Order ID       │                 │
     │                  │<─────────────────────────────────────┤
     │                  │                    │                 │
     │ 34. Return order ID                   │                 │
     │<──────────────────┤                    │                 │
```

### Price Change Detection Flow

```
┌─────────┐      ┌──────────────┐      ┌──────────┐
│  Agent  │      │ CheckoutSvc  │      │ Merchant │
└────┬────┘      └──────┬───────┘      └────┬─────┘
     │                  │                    │
     │ 1. get_quote (on APPROVED checkout)   │
     │─────────────────>│                    │
     │                  │                    │
     │                  │ 2. Check state     │
     │                  │    (requires_reapproval() = True)    │
     │                  │                    │
     │                  │ 3. Get fresh quote │
     │                  ├───────────────────>│
     │                  │                    │
     │                  │ 4. Quote: $120    │
     │                  │    (was $100)     │
     │                  │<───────────────────┤
     │                  │                    │
     │                  │ 5. Compare prices │
     │                  │    frozen_receipt.total_cents         │
     │                  │    vs quote.total_cents              │
     │                  │    $100 != $120    │
     │                  │                    │
     │                  │ 6. checkout.set_quote()              │
     │                  │    (detects mismatch)                │
     │                  │    (status: QUOTED)                  │
     │                  │    (clears frozen_receipt)           │
     │                  │                    │
     │                  │ 7. Save checkout  │                 │
     │                  │                    │
     │ 8. Return with reapproval_required=True                │
     │<──────────────────┤                    │
     │                  │                    │
     │ 9. request_approval (again)           │
     │─────────────────>│                    │
     │                  │                    │
     │                  │ 10. Freeze new receipt              │
     │                  │     (status: AWAITING_APPROVAL)      │
     │                  │                    │
     │ 11. Return new frozen receipt          │
     │<──────────────────┤                    │
```

---

## API Reference

### create_checkout

**Method**: `async def create_checkout(...)`

**Purpose**: Create a new checkout session from an offer.

**Parameters**:
- `offer_id: str` - The offer ID to create checkout from
- `items: list[dict[str, Any]]` - List of items with:
  - `product_id` (required): Product identifier
  - `variant_id` (optional): Variant identifier
  - `quantity` (required): Quantity to purchase
- `idempotency_key: str | None` - Optional idempotency key

**Returns**: `CreateCheckoutResult`

**Implementation Flow**:
1. Check idempotency: If key exists, return existing checkout
2. Get offer from repository to determine merchant
3. Create `Checkout` entity via `Checkout.create()`
4. Save to repository
5. Log creation event

**Example**:
```python
result = await service.create_checkout(
    offer_id="offer-123",
    items=[
        {
            "product_id": "prod-456",
            "variant_id": "var-789",
            "quantity": 2
        }
    ],
    idempotency_key="unique-key-123"
)

if result.success:
    checkout = result.checkout
    print(f"Created checkout: {checkout.id}")
    print(f"Status: {checkout.status}")  # CREATED
    print(f"Expires at: {checkout.expires_at}")
else:
    print(f"Error: {result.error_code} - {result.error}")
```

**Idempotency Behavior**:
- If `idempotency_key` provided and checkout exists → returns existing checkout
- If `idempotency_key` provided and no checkout → creates new checkout
- If no `idempotency_key` → always creates new checkout

**Error Codes**:
- `OFFER_NOT_FOUND`: Offer doesn't exist (line 217)
- `CREATE_FAILED`: Unexpected error during creation (line 253)

**State After**: `CheckoutStatus.CREATED`

**Expiration**: 24 hours from creation (line 1541 in entities.py)

### get_quote

**Method**: `async def get_quote(...)`

**Purpose**: Get pricing quote from merchant for checkout items.

**Parameters**:
- `checkout_id: str` - Checkout identifier
- `items: list[dict[str, Any]]` - Items to quote (same format as create_checkout)
- `customer_email: str | None` - Optional customer email

**Returns**: `QuoteCheckoutResult` with `reapproval_required` flag

**Implementation Flow**:
1. Get checkout from repository
2. Validate state: Must be `CREATED` or `QUOTED` (or `requires_reapproval()`)
3. Get merchant client via factory
4. Call `merchant_client.create_quote()`
5. Convert quote items to `CheckoutItem` entities
6. Check if price changed (if in reapproval state)
7. Call `checkout.set_quote()` to update checkout
8. Save checkout

**Merchant Communication**:
```python
async with MerchantClientFactory(request_id=self.request_id) as factory:
    client = factory.get_client(str(checkout.merchant_id))
    quote = await client.create_quote(
        items=items,
        customer_email=customer_email,
    )
```

**Price Change Detection** (lines 319-323):
```python
reapproval_triggered = (
    checkout.status.requires_reapproval()
    and checkout.frozen_receipt
    and not checkout.frozen_receipt.matches_total(quote.total_cents)
)
```

**Example**:
```python
result = await service.get_quote(
    checkout_id="checkout-123",
    items=[{"product_id": "prod-456", "quantity": 1}],
    customer_email="user@example.com"
)

if result.success:
    checkout = result.checkout
    print(f"Quote total: ${checkout.total_cents / 100}")
    print(f"Status: {checkout.status}")  # QUOTED
    print(f"Merchant checkout ID: {checkout.merchant_checkout_id}")
    
    if result.reapproval_required:
        print("Price changed! Re-approval required.")
else:
    print(f"Error: {result.error}")
```

**Error Codes**:
- `CHECKOUT_NOT_FOUND`: Checkout doesn't exist (line 278)
- `INVALID_STATE`: Checkout in invalid state for quoting (line 286)
- `MERCHANT_NOT_FOUND`: Merchant not found (line 296)
- `MERCHANT_ERROR`: Merchant API error (line 363)
- `QUOTE_FAILED`: Unexpected error (line 375)

**State After**: `CheckoutStatus.QUOTED` (or stays `QUOTED` if already quoted)

**Price Storage**: Stored in `checkout.items[]`, `subtotal_cents`, `tax_cents`, `shipping_cents`, `total_cents`

### request_approval

**Method**: `async def request_approval(...)`

**Purpose**: Freeze receipt and request human approval.

**Parameters**:
- `checkout_id: str` - Checkout identifier

**Returns**: `RequestApprovalResult` with `frozen_receipt`

**Implementation Flow**:
1. Get checkout from repository
2. Call `checkout.request_approval()` (domain method)
3. Domain method creates `FrozenReceipt` from current prices
4. Domain method transitions state to `AWAITING_APPROVAL`
5. Save checkout

**Frozen Receipt Creation** (in domain entity):
```python
frozen_receipt = FrozenReceipt.create(
    items=[FrozenReceiptItem(...) for item in self.items],
    subtotal_cents=self.subtotal_cents,
    tax_cents=self.tax_cents,
    shipping_cents=self.shipping_cents,
    total_cents=self.total_cents,
    currency=self.currency
)
```

**State Transition**: `QUOTED` → `AWAITING_APPROVAL`

**Receipt Hash**: SHA-256 hash computed in `FrozenReceipt.create()` for integrity verification.

**Example**:
```python
result = await service.request_approval(checkout_id="checkout-123")

if result.success:
    frozen_receipt = result.frozen_receipt
    checkout = result.checkout
    print(f"Receipt hash: {frozen_receipt.hash}")
    print(f"Total: ${frozen_receipt.total_cents / 100}")
    print(f"Status: {checkout.status}")  # AWAITING_APPROVAL
    # Display to user for approval
else:
    print(f"Error: {result.error}")
```

**Error Codes**:
- `CHECKOUT_NOT_FOUND`: Checkout doesn't exist (line 398)
- `CHECKOUT_EXPIRED`: Checkout expired (line 421)
- `APPROVAL_REQUEST_FAILED`: Unexpected error (line 433)

**Prerequisites**: Checkout must be in `QUOTED` state

### approve

**Method**: `async def approve(...)`

**Purpose**: Approve a pending checkout.

**Parameters**:
- `checkout_id: str` - Checkout identifier
- `approved_by: str` - Who is approving (e.g., "user", "agent")

**Returns**: `ApproveCheckoutResult`

**Implementation Flow**:
1. Get checkout from repository
2. Call `checkout.approve(approved_by=approved_by)` (domain method)
3. Domain method validates state and transitions to `APPROVED`
4. Domain method records approval in audit trail
5. Save checkout

**State Transition**: `AWAITING_APPROVAL` → `APPROVED`

**Audit Trail**: Records approval in `checkout.audit_trail` with:
- `action`: "checkout_approved"
- `actor`: `approved_by`
- `timestamp`: Current UTC time

**Example**:
```python
result = await service.approve(
    checkout_id="checkout-123",
    approved_by="user-john-doe"
)

if result.success:
    checkout = result.checkout
    print(f"Approved by: {checkout.approved_by}")
    print(f"Approved at: {checkout.approved_at}")
    print(f"Status: {checkout.status}")  # APPROVED
```

**Error Codes**:
- `CHECKOUT_NOT_FOUND`: Checkout doesn't exist (line 456)
- `CHECKOUT_EXPIRED`: Checkout expired (line 475)
- `REAPPROVAL_REQUIRED`: Price changed, needs re-approval (line 481)
- `APPROVAL_FAILED`: Unexpected error (line 493)

**Prerequisites**: Checkout must be in `AWAITING_APPROVAL` state

### confirm

**Method**: `async def confirm(...)`

**Purpose**: Execute the purchase with merchant.

**Parameters**:
- `checkout_id: str` - Checkout identifier
- `payment_method: str` - Payment method (default: "test_card")
- `idempotency_key: str | None` - Optional idempotency key

**Returns**: `ConfirmCheckoutResult` with `merchant_order_id` and `order_id`

**Implementation Flow**:
1. Get checkout from repository
2. Check if already confirmed (idempotency) - return existing if so
3. Validate state: Must be `APPROVED`
4. Check for price changes: `checkout.requires_reapproval`
5. Get merchant client via factory
6. Call `merchant_client.confirm_checkout()`
7. Call `checkout.confirm()` to update state
8. Save checkout
9. Create order via `_create_order_from_checkout()`

**Price Change Detection** (lines 537-543):
```python
if checkout.requires_reapproval:
    return ConfirmCheckoutResult(
        success=False,
        error="Price has changed, re-approval required",
        error_code="REAPPROVAL_REQUIRED",
        reapproval_required=True,
    )
```

**Merchant Confirmation**:
```python
confirm_response = await client.confirm_checkout(
    checkout_id=checkout.merchant_checkout_id,
    payment_method=payment_method,
    idempotency_key=idempotency_key,
)
```

**Order Creation** (lines 646-732):
- Converts checkout items to `OrderItemDTO`
- Creates default customer and address (in production, would come from checkout)
- Calls `order_service.create_order_from_checkout()`
- Returns order ID

**State Transition**: `APPROVED` → `CONFIRMED`

**Example**:
```python
result = await service.confirm(
    checkout_id="checkout-123",
    payment_method="test_card",
    idempotency_key="confirm-key-123"
)

if result.success:
    print(f"Order ID: {result.order_id}")
    print(f"Merchant Order ID: {result.merchant_order_id}")
    print(f"Status: {result.checkout.status}")  # CONFIRMED
elif result.reapproval_required:
    print("Price changed! Re-approval required.")
    # Trigger re-approval flow
else:
    print(f"Error: {result.error}")
```

**Error Codes**:
- `CHECKOUT_NOT_FOUND`: Checkout doesn't exist (line 518)
- `NOT_APPROVED`: Must be approved first (line 533)
- `REAPPROVAL_REQUIRED`: Price changed, needs re-approval (line 541, 620)
- `MERCHANT_NOT_FOUND`: Merchant not found (line 552)
- `QUOTE_REQUIRED`: No merchant checkout ID (line 559)
- `MERCHANT_ERROR`: Merchant API error (line 607)
- `CHECKOUT_EXPIRED`: Checkout expired (line 613)
- `CONFIRM_FAILED`: Unexpected error (line 632)

**Idempotency**: If checkout already `CONFIRMED`, returns existing result (line 522-526)

**Prerequisites**: Checkout must be in `APPROVED` state

---

## Business Logic & Rules

### State Machine Rules

**Valid State Transitions** (from `state_machines.py`):
```python
_CHECKOUT_TRANSITIONS = {
    CheckoutStatus.CREATED: {CheckoutStatus.QUOTED, CheckoutStatus.CANCELLED},
    CheckoutStatus.QUOTED: {
        CheckoutStatus.AWAITING_APPROVAL,
        CheckoutStatus.QUOTED,  # Can re-quote
        CheckoutStatus.CANCELLED
    },
    CheckoutStatus.AWAITING_APPROVAL: {
        CheckoutStatus.APPROVED,
        CheckoutStatus.QUOTED,  # Price change -> re-quote
        CheckoutStatus.CANCELLED
    },
    CheckoutStatus.APPROVED: {
        CheckoutStatus.CONFIRMED,
        CheckoutStatus.QUOTED,  # Price change -> re-quote
        CheckoutStatus.FAILED,
        CheckoutStatus.CANCELLED
    },
    CheckoutStatus.CONFIRMED: set(),  # Terminal
    CheckoutStatus.FAILED: set(),  # Terminal
    CheckoutStatus.CANCELLED: set(),  # Terminal
}
```

**State Validation Methods**:
- `is_quotable()`: Returns `True` for `CREATED` or `QUOTED`
- `requires_reapproval()`: Returns `True` for `AWAITING_APPROVAL` or `APPROVED`
- `is_cancellable()`: Returns `True` for all non-terminal states

**State Transition Enforcement**:
- Domain entity methods (`set_quote()`, `request_approval()`, `approve()`, `confirm()`) validate transitions
- Raises `InvalidStateTransitionError` if invalid

### Price Change Detection

**Detection Logic** (in `Checkout` entity):
```python
@property
def requires_reapproval(self) -> bool:
    """Check if checkout requires re-approval due to price change."""
    if self.frozen_receipt is None:
        return False
    return not self.frozen_receipt.matches_total(self.total_cents)
```

**Price Comparison** (in `FrozenReceipt`):
```python
def matches_total(self, current_total_cents: int) -> bool:
    """Check if current total matches frozen receipt."""
    return self.total_cents == current_total_cents
```

**Re-approval Flow**:
1. When `get_quote()` called on `APPROVED` checkout with price change:
   - `set_quote()` detects mismatch
   - State transitions back to `QUOTED`
   - `frozen_receipt` cleared
   - `reapproval_required` flag set to `True`
2. Agent must call `request_approval()` again
3. New frozen receipt created with new price
4. User approves again
5. `confirm()` can proceed

**Tolerance**: Currently exact match required. No percentage tolerance.

### Expiration Rules

**Checkout Expiration**:
- Default expiration: **24 hours** from creation (line 1541 in entities.py)
- Expired checkouts cannot be modified
- Expiration checked before all operations

**Expiration Check** (in `Checkout` entity):
```python
@property
def is_expired(self) -> bool:
    """Check if checkout has expired."""
    if self.expires_at is None:
        return False
    return datetime.now(timezone.utc) > self.expires_at
```

**Expiration Handling**:
- `CheckoutExpiredError` raised if expired
- Caught in service methods and returned as error result

### Idempotency Rules

**Idempotency Key Usage**:
- `create_checkout`: Returns existing checkout if key exists (line 201-208)
- `confirm`: Returns existing result if already confirmed (line 522-526)
- Keys are scoped per operation type

**Key Format**: Free-form string, recommended: UUID or deterministic hash.

**Idempotency Window**: No expiration (stored indefinitely in repository).

**Lookup**: `CheckoutRepository.get_by_idempotency_key(key)`

### Frozen Receipt Rules

**Receipt Freezing**:
- Frozen when `request_approval()` is called
- Contains snapshot of prices at that moment
- Hash computed for integrity verification

**Receipt Hash Calculation** (in `FrozenReceipt.create()`):
```python
# Hash includes all receipt data
hash_input = json.dumps({
    "items": [item.to_dict() for item in items],
    "subtotal": subtotal_cents,
    "tax": tax_cents,
    "shipping": shipping_cents,
    "total": total_cents,
    "currency": currency
}, sort_keys=True)

hash = hashlib.sha256(hash_input.encode()).hexdigest()
```

**Receipt Validation**: On confirmation, `requires_reapproval` property checks if current total matches frozen receipt.

---

## Implementation Details

### Merchant Client Integration

**Client Factory**:
```python
async with MerchantClientFactory(request_id=self.request_id) as factory:
    client = factory.get_client(str(checkout.merchant_id))
    quote = await client.create_quote(...)
```

**Factory Pattern**: Uses context manager for resource management.

**Client Interface**:
```python
class MerchantClient:
    async def create_quote(
        self,
        items: list[dict],
        customer_email: str | None = None,
    ) -> MerchantQuoteResponse
    
    async def confirm_checkout(
        self,
        checkout_id: str,
        payment_method: str,
        idempotency_key: str | None = None
    ) -> MerchantConfirmResponse
```

**Error Handling**:
- `MerchantClientError`: Wrapped and returned as service error
- Network errors: Propagated as `MERCHANT_ERROR`
- HTTP 409 with "PRICE_CHANGED": Converted to `REAPPROVAL_REQUIRED` (line 591-597)

### Repository Pattern

**Current Implementation**: In-memory dictionary (lines 41-86).

**Storage**:
- `_checkouts`: `dict[str, Checkout]` - Key: checkout ID string
- `_by_idempotency_key`: `dict[str, str]` - Key: idempotency key, Value: checkout ID

**Future Migration**:
```python
class SQLCheckoutRepository:
    def __init__(self, session: Session):
        self.session = session
    
    def save(self, checkout: Checkout):
        # Convert domain entity to ORM model
        model = CheckoutModel.from_entity(checkout)
        self.session.merge(model)
        self.session.commit()
    
    def get(self, checkout_id: str) -> Checkout | None:
        model = self.session.query(CheckoutModel).filter_by(id=checkout_id).first()
        return model.to_entity() if model else None
```

### Logging

**Structured Logging** (using structlog):
```python
logger.info(
    "Checkout created",
    checkout_id=str(checkout.id),
    offer_id=offer_id,
    merchant_id=str(merchant_id),
    request_id=self.request_id,
)
```

**Log Levels**:
- `INFO`: Normal operations (create, quote, approve, confirm)
- `WARNING`: Recoverable errors (price changes, expired checkouts)
- `ERROR`: Unexpected errors (merchant failures, validation errors)

**Log Fields**:
- `checkout_id`: Always included
- `request_id`: For request correlation (from service initialization)
- `merchant_id`: Merchant identifier
- `operation`: Implicit from log message

---

## Error Handling

### Error Types

**Domain Exceptions** (from `domain/exceptions.py`):
```python
class CheckoutNotFoundError(CheckoutError):
    """Checkout not found."""
    pass

class CheckoutExpiredError(CheckoutError):
    """Checkout expired."""
    pass

class CheckoutNotApprovedError(CheckoutError):
    """Checkout not approved."""
    pass

class ReapprovalRequiredError(CheckoutError):
    """Price changed, re-approval required."""
    old_price: int
    new_price: int
```

**Service Errors**:
- Wrapped in `Result` objects
- Error codes standardized (e.g., `CHECKOUT_NOT_FOUND`, `REAPPROVAL_REQUIRED`)
- Error messages user-friendly

### Error Propagation

```
Merchant API Error
    ↓
MerchantClientError
    ↓
CheckoutService (catches, wraps)
    ↓
Result.error / Result.error_code
    ↓
API Handler (converts to HTTP)
    ↓
HTTPException with error_code
```

**Example** (from `confirm()` method):
```python
except MerchantClientError as e:
    # Handle price changed from merchant
    if e.status_code == 409 and "PRICE_CHANGED" in str(e):
        return ConfirmCheckoutResult(
            success=False,
            error=str(e),
            error_code="REAPPROVAL_REQUIRED",
            reapproval_required=True,
        )
    # Other merchant errors
    return ConfirmCheckoutResult(
        success=False,
        error=str(e),
        error_code="MERCHANT_ERROR",
    )
```

### Retry Logic

**Current**: No automatic retries.

**Future Enhancement**:
```python
@retry(
    max_attempts=3,
    backoff=exponential_backoff(base=1, max=10),
    exceptions=(MerchantClientError,)
)
async def get_quote(...):
    # Implementation
```

---

## Performance Considerations

### Current Limitations

1. **In-Memory Storage**: Not scalable, lost on restart
2. **No Caching**: Every operation hits merchant API
3. **Synchronous Merchant Calls**: Blocks until response
4. **No Connection Pooling**: New connection per request (handled by httpx)

### Optimization Opportunities

**Caching**:
```python
@lru_cache(maxsize=1000)
async def get_merchant_client(merchant_id: str):
    return MerchantClientFactory.create(merchant_id)
```

**Async Batching** (future):
```python
# Batch multiple quote requests
quotes = await asyncio.gather(
    merchant_client.create_quote(...),
    merchant_client.create_quote(...),
    merchant_client.create_quote(...),
)
```

**Database Indexing** (future):
```sql
CREATE INDEX idx_checkout_idempotency ON checkouts(idempotency_key);
CREATE INDEX idx_checkout_status ON checkouts(status);
CREATE INDEX idx_checkout_expires_at ON checkouts(expires_at);
CREATE INDEX idx_checkout_merchant_id ON checkouts(merchant_id);
```

### Performance Metrics

**Target Latencies**:
- `create_checkout`: < 10ms (in-memory)
- `get_quote`: < 500ms (depends on merchant API)
- `request_approval`: < 10ms (in-memory)
- `approve`: < 10ms (in-memory)
- `confirm`: < 1000ms (depends on merchant API + order creation)

**Bottlenecks**:
1. Merchant API calls (network latency)
2. Order creation (calls order_service)
3. No database yet (will add latency when migrated)

---

## Security Considerations

### Input Validation

**Item Validation** (should be added):
```python
def validate_items(items: list[dict]) -> None:
    for item in items:
        if "product_id" not in item:
            raise ValueError("product_id required")
        if "quantity" not in item or item["quantity"] <= 0:
            raise ValueError("quantity must be positive")
        if item["quantity"] > 1000:  # Reasonable limit
            raise ValueError("quantity too large")
```

**Current**: Validation happens in domain entity (`CheckoutItem`).

### Idempotency Key Security

**Recommendations**:
- Use cryptographically random keys (UUID v4)
- Don't expose internal IDs as idempotency keys
- Rate limit by idempotency key (future)
- Validate key format (future)

### Merchant Communication

**Authentication**:
- API keys per merchant (configured in settings)
- HMAC signatures for webhooks (handled by merchant)
- TLS for all merchant communication (httpx default)

### Audit Trail

**Audit Log** (in `Checkout` entity):
```python
audit_trail: list[AuditEntry] = field(default_factory=list)

# Each operation adds entry
self._add_audit_entry(
    action="checkout_approved",
    from_status="awaiting_approval",
    to_status="approved",
    actor=approved_by,
    details={"ip_address": request.client.host}  # If available
)
```

**Audit Entry Structure**:
```python
@dataclass
class AuditEntry:
    timestamp: datetime
    action: str
    from_status: str | None
    to_status: str | None
    actor: str | None
    details: dict[str, object] | None
```

---

## Testing Strategy

### Unit Tests

**Test Structure**:
```python
class TestCheckoutService:
    @pytest.fixture
    def service(self):
        repo = CheckoutRepository()
        return CheckoutService(checkout_repo=repo)
    
    async def test_create_checkout_success(self, service):
        # Arrange
        offer_repo = MockOfferRepository()
        service.offer_repo = offer_repo
        
        # Act
        result = await service.create_checkout(
            offer_id="offer-123",
            items=[{"product_id": "prod-1", "quantity": 1}]
        )
        
        # Assert
        assert result.success
        assert result.checkout is not None
        assert result.checkout.status == CheckoutStatus.CREATED
    
    async def test_create_checkout_idempotency(self, service):
        # Test idempotency behavior
        key = "idemp-key-123"
        result1 = await service.create_checkout(..., idempotency_key=key)
        result2 = await service.create_checkout(..., idempotency_key=key)
        
        assert result1.checkout.id == result2.checkout.id
    
    async def test_get_quote_price_change(self, service):
        # Test price change detection
        # Create checkout, quote, approve
        # Quote again with different price
        # Verify reapproval_required flag
        pass
```

### Integration Tests

**Merchant Mocking**:
```python
@pytest.fixture
def mock_merchant_client():
    client = MockMerchantClient()
    client.set_quote_response(MerchantQuoteResponse(
        items=[...],
        total_cents=10000,
        ...
    ))
    return client

async def test_get_quote_integration(service, mock_merchant_client):
    # Test full integration with mocked merchant
    pass
```

### E2E Tests

**Full Flow**:
```python
async def test_complete_checkout_flow():
    # 1. Create checkout
    create_result = await service.create_checkout(...)
    checkout_id = str(create_result.checkout.id)
    
    # 2. Get quote
    quote_result = await service.get_quote(checkout_id, ...)
    assert quote_result.checkout.status == CheckoutStatus.QUOTED
    
    # 3. Request approval
    approval_result = await service.request_approval(checkout_id)
    assert approval_result.frozen_receipt is not None
    
    # 4. Approve
    approve_result = await service.approve(checkout_id, "user")
    assert approve_result.checkout.status == CheckoutStatus.APPROVED
    
    # 5. Confirm
    confirm_result = await service.confirm(checkout_id)
    assert confirm_result.order_id is not None
    assert confirm_result.checkout.status == CheckoutStatus.CONFIRMED
```

---

## Extension Points

### Adding New Merchant Types

**Interface**:
```python
class CustomMerchantClient(MerchantClient):
    async def create_quote(self, ...):
        # Custom implementation
        pass
    
    async def confirm_checkout(self, ...):
        # Custom implementation
        pass
```

**Registration** (in `MerchantClientFactory`):
```python
MerchantClientFactory.register("custom-merchant", CustomMerchantClient)
```

### Adding New Approval Methods

**Extension**:
```python
class TwoFactorApprovalService:
    async def request_approval(self, checkout_id: str):
        # Send 2FA code
        # Wait for verification
        # Then approve
        pass
```

**Integration**: Could be called before `approve()` method.

### Adding Price Change Tolerance

**Configuration**:
```python
class CheckoutService:
    def __init__(
        self,
        price_tolerance_percent: float = 0.0,
        ...
    ):
        self.price_tolerance_percent = price_tolerance_percent
    
    def _prices_match(self, old: int, new: int) -> bool:
        if self.price_tolerance_percent == 0:
            return old == new
        
        diff_percent = abs(new - old) / old * 100
        return diff_percent <= self.price_tolerance_percent
```

**Usage**: Modify `FrozenReceipt.matches_total()` to use tolerance.

### Adding Checkout Expiration Extension

**Extension**:
```python
async def extend_checkout_expiration(
    self,
    checkout_id: str,
    additional_hours: int = 24
) -> Result:
    checkout = self.checkout_repo.get(checkout_id)
    if not checkout:
        return Result(success=False, error="Not found")
    
    checkout.extends_expiration(timedelta(hours=additional_hours))
    self.checkout_repo.save(checkout)
    return Result(success=True)
```

---

## Troubleshooting

### Common Issues

**Issue**: "Checkout not found"
- **Cause**: Checkout ID incorrect or checkout expired/deleted
- **Solution**: Verify checkout ID, check expiration time, check repository state

**Issue**: "Price changed, re-approval required"
- **Cause**: Merchant price changed between quote and confirm
- **Solution**: Call `get_quote()` again, then `request_approval()` with new price

**Issue**: "Invalid state transition"
- **Cause**: Trying to perform operation in wrong state
- **Solution**: Check current state with `get_checkout()`, follow state machine flow

**Issue**: "Merchant API error"
- **Cause**: Merchant service unavailable or error
- **Solution**: Check merchant health endpoint, verify merchant configuration, check network connectivity

**Issue**: "Checkout expired"
- **Cause**: Checkout older than 24 hours
- **Solution**: Create new checkout, or extend expiration (if extension method added)

### Debugging

**Enable Debug Logging**:
```python
import logging
logging.getLogger("app.application.checkout_service").setLevel(logging.DEBUG)
```

**Check Checkout State**:
```python
checkout = await service.get_checkout(checkout_id)
if checkout:
    print(f"Status: {checkout.status}")
    print(f"Expires at: {checkout.expires_at}")
    print(f"Is expired: {checkout.is_expired}")
    print(f"Frozen receipt: {checkout.frozen_receipt is not None}")
    print(f"Requires reapproval: {checkout.requires_reapproval}")
    print(f"Audit trail: {len(checkout.audit_trail)} entries")
else:
    print("Checkout not found")
```

**Inspect Repository State**:
```python
repo = get_checkout_repository()
print(f"Total checkouts: {len(repo._checkouts)}")
print(f"Idempotency keys: {len(repo._by_idempotency_key)}")
```

---

## Code Examples

### Complete Purchase Flow

```python
from app.application.checkout_service import CheckoutService, get_checkout_service
from app.application.intent_service import get_offer_repository

# Initialize service
offer_repo = get_offer_repository()
service = get_checkout_service(offer_repo=offer_repo)

# 1. Create checkout
create_result = await service.create_checkout(
    offer_id="offer-123",
    items=[{"product_id": "prod-456", "quantity": 1}],
    idempotency_key="flow-123"
)

if not create_result.success:
    raise Exception(f"Failed to create checkout: {create_result.error}")

checkout_id = str(create_result.checkout.id)
print(f"Created checkout: {checkout_id}")

# 2. Get quote
quote_result = await service.get_quote(
    checkout_id=checkout_id,
    items=[{"product_id": "prod-456", "quantity": 1}],
    customer_email="user@example.com"
)

if not quote_result.success:
    raise Exception(f"Failed to get quote: {quote_result.error}")

print(f"Quote total: ${quote_result.checkout.total_cents / 100}")

# 3. Request approval
approval_result = await service.request_approval(checkout_id)

if not approval_result.success:
    raise Exception(f"Failed to request approval: {approval_result.error}")

frozen_receipt = approval_result.frozen_receipt
print(f"Receipt hash: {frozen_receipt.hash}")
print(f"Total: ${frozen_receipt.total_cents / 100}")

# Display to user for approval
user_approved = input("Approve purchase? (y/n): ")

if user_approved.lower() != 'y':
    print("Purchase cancelled")
    exit()

# 4. Approve
approve_result = await service.approve(
    checkout_id=checkout_id,
    approved_by="user-john"
)

if not approve_result.success:
    raise Exception(f"Failed to approve: {approve_result.error}")

print(f"Approved by: {approve_result.checkout.approved_by}")

# 5. Confirm purchase
confirm_result = await service.confirm(
    checkout_id=checkout_id,
    payment_method="test_card",
    idempotency_key="confirm-123"
)

if confirm_result.success:
    print(f"Order created: {confirm_result.order_id}")
    print(f"Merchant Order ID: {confirm_result.merchant_order_id}")
elif confirm_result.reapproval_required:
    print("Price changed! Re-approval needed.")
    # Handle re-approval flow
else:
    raise Exception(f"Failed to confirm: {confirm_result.error}")
```

### Handling Price Changes

```python
# Attempt confirmation
confirm_result = await service.confirm(
    checkout_id=checkout_id,
    payment_method="test_card"
)

if confirm_result.reapproval_required:
    print("Price changed! Getting new quote...")
    
    # Get new quote
    new_quote_result = await service.get_quote(
        checkout_id=checkout_id,
        items=[{"product_id": "prod-456", "quantity": 1}]
    )
    
    if new_quote_result.reapproval_required:
        # Request approval again with new price
        new_approval_result = await service.request_approval(checkout_id)
        
        # Show new price to user
        new_total = new_approval_result.frozen_receipt.total_cents
        old_total = confirm_result.checkout.frozen_receipt.total_cents
        print(f"Price changed from ${old_total/100} to ${new_total/100}")
        
        # User approves again
        user_approved = input("Approve new price? (y/n): ")
        if user_approved.lower() == 'y':
            await service.approve(checkout_id, approved_by="user")
            
            # Confirm again
            confirm_result = await service.confirm(
                checkout_id=checkout_id,
                payment_method="test_card"
            )
            
            if confirm_result.success:
                print(f"Order created: {confirm_result.order_id}")
```

### Error Handling Pattern

```python
async def safe_confirm(checkout_id: str) -> str:
    """Safely confirm checkout with error handling."""
    result = await service.confirm(checkout_id)
    
    if result.success:
        return result.order_id
    
    if result.error_code == "REAPPROVAL_REQUIRED":
        # Handle re-approval
        raise ReapprovalNeededError("Price changed")
    
    if result.error_code == "CHECKOUT_EXPIRED":
        raise CheckoutExpiredError("Checkout expired")
    
    if result.error_code == "MERCHANT_ERROR":
        # Retry logic could go here
        raise MerchantError(result.error)
    
    raise Exception(f"Unexpected error: {result.error}")
```

---

## Summary

This detailed documentation covers:

1. **Architecture**: Class structure, dependencies, design patterns
2. **Component Details**: Repository, result types, service methods
3. **Workflow Diagrams**: Complete flow and price change detection
4. **API Reference**: All 6 methods with parameters, returns, examples, error codes
5. **Business Logic**: State machine rules, price change detection, expiration, idempotency
6. **Implementation**: Merchant integration, repository pattern, logging
7. **Error Handling**: Error types, propagation, retry logic
8. **Performance**: Limitations, optimizations, metrics
9. **Security**: Validation, idempotency, audit trail
10. **Testing**: Unit, integration, E2E test strategies
11. **Extension Points**: How to extend functionality
12. **Troubleshooting**: Common issues and debugging tips
13. **Code Examples**: Real-world usage patterns

This level of detail helps developers:
- Understand component internals deeply
- Debug issues quickly
- Extend functionality safely
- Optimize performance
- Write comprehensive tests
- Integrate with the service correctly
