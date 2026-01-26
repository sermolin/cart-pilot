# WebhookService - Detailed Component Documentation

> **Complete technical documentation for the WebhookService component**  
> This document provides comprehensive details for developers working with or extending the webhook service.

## Table of Contents

1. [Overview](#overview)
2. [Architecture & Design](#architecture--design)
3. [Component Details](#component-details)
4. [API Reference](#api-reference)
5. [Business Logic & Rules](#business-logic--rules)
6. [Implementation Details](#implementation-details)
7. [Security Considerations](#security-considerations)
8. [Code Examples](#code-examples)

---

## Overview

### Purpose

The `WebhookService` processes incoming webhooks from merchants with HMAC signature verification, event deduplication, out-of-order event tolerance, and event processing.

**Location**: `cartpilot-api/app/application/webhook_service.py`  
**Lines of Code**: ~618 lines  
**Dependencies**: HMAC signature verification, event log

### Responsibilities

- **Signature Verification**: Verify HMAC-SHA256 signatures on webhook payloads
- **Event Deduplication**: Prevent duplicate event processing
- **Event Logging**: Store events for audit and replay
- **Event Processing**: Route events to appropriate handlers
- **State Updates**: Update domain entities based on events

### Key Metrics

- **Event Types**: 12 webhook event types
- **Event Statuses**: 5 status types (RECEIVED, PROCESSING, PROCESSED, FAILED, DUPLICATE)
- **Components**: WebhookService, WebhookSignatureVerifier, InMemoryEventLog

---

## Architecture & Design

### Class Structure

```python
class WebhookService:
    """Service for processing incoming webhooks."""
    
    def __init__(
        self,
        event_log: InMemoryEventLog | None = None,
        signature_verifier: WebhookSignatureVerifier | None = None,
    ) -> None
    
    def verify_signature(payload: str, signature: str, merchant_id: str) -> bool
    async def process_event(event: WebhookEvent, correlation_id: str | None = None) -> WebhookResult

class WebhookSignatureVerifier:
    """Verifies HMAC signatures on webhook payloads."""
    
    def __init__(self, secret: str | None = None) -> None
    def verify(payload: str, signature: str, merchant_id: str) -> bool

class InMemoryEventLog:
    """In-memory event log for deduplication."""
    
    async def exists(event_id: str, merchant_id: str) -> bool
    async def store(event: WebhookEvent, status: EventStatus, ...) -> None
    async def get(event_id: str, merchant_id: str) -> dict[str, Any] | None
    async def update_status(event_id: str, merchant_id: str, status: EventStatus, ...) -> None
```

### Design Patterns

1. **Service Layer Pattern**: Encapsulates webhook processing logic
2. **Strategy Pattern**: Signature verification strategy
3. **Repository Pattern**: Event log abstraction
4. **Observer Pattern**: Event processing handlers

---

## Component Details

### WebhookEvent

**Location**: Lines 52-89

```python
@dataclass
class WebhookEvent:
    """Represents a webhook event from a merchant."""
    
    event_id: str
    event_type: WebhookEventType
    merchant_id: str
    timestamp: datetime
    data: dict[str, Any]
    signature: str | None = None
    
    def compute_payload_hash(self) -> str
```

**Event Types** (Lines 24-39):
- `CHECKOUT_CREATED`, `CHECKOUT_QUOTED`, `CHECKOUT_CONFIRMED`, `CHECKOUT_FAILED`, `CHECKOUT_EXPIRED`
- `ORDER_CREATED`, `ORDER_CONFIRMED`, `ORDER_SHIPPED`, `ORDER_DELIVERED`, `ORDER_CANCELLED`, `ORDER_REFUNDED`
- `PRICE_CHANGED`, `STOCK_CHANGED`

**Payload Hash**: SHA-256 hash of normalized JSON payload for deduplication (line 89)

### WebhookSignatureVerifier

**Location**: Lines 111-174

**Purpose**: Verifies HMAC-SHA256 signatures on webhook payloads.

**Signature Format**: `sha256=<hex_digest>`

**Verification Process**:
1. Parse signature header format (line 144)
2. Compute HMAC-SHA256 of payload using secret (lines 156-160)
3. Constant-time comparison with provided signature (line 163)

**Security**: Uses `hmac.compare_digest()` for constant-time comparison to prevent timing attacks

**Secret Source**: `settings.webhook_secret` (line 123)

### InMemoryEventLog

**Location**: Lines 177-264

**Purpose**: In-memory event log for deduplication (temporary, will be replaced with database).

**Storage Structure**:
```python
self._events: dict[str, dict[str, Any]] = {}
# Key format: f"{merchant_id}:{event_id}"
```

**Event Storage**:
- `event_id`, `merchant_id`, `event_type`
- `payload_hash` (SHA-256 of payload)
- `payload` (event data)
- `received_at`, `processed_at`
- `status`, `error_message`, `correlation_id`

**Future Migration**: Will use PostgreSQL `event_log` table

### WebhookResult

**Location**: Lines 92-108

```python
@dataclass
class WebhookResult:
    """Result of webhook processing."""
    
    success: bool
    event_id: str
    status: EventStatus
    message: str
    duplicate: bool = False
```

**Status Values**:
- `RECEIVED`: Event received but not yet processed
- `PROCESSING`: Event is being processed
- `PROCESSED`: Event successfully processed
- `FAILED`: Event processing failed
- `DUPLICATE`: Event was already processed

---

## API Reference

### process_event

**Method**: `async def process_event(event: WebhookEvent, correlation_id: str | None = None) -> WebhookResult`

**Purpose**: Process a webhook event with deduplication and routing.

**Flow**:
1. Check for duplicate (by event_id + merchant_id) - line 332
2. Store event as PROCESSING - line 347
3. Process event based on type - lines 350-400
4. Update status to PROCESSED or FAILED - lines 380-400

**Returns**: `WebhookResult` with success status and event status

**Example**:
```python
event = WebhookEvent(
    event_id="evt_123",
    event_type=WebhookEventType.ORDER_CONFIRMED,
    merchant_id="merchant-a",
    timestamp=datetime.now(timezone.utc),
    data={"order_id": "order-456", "merchant_order_id": "merchant-order-789"}
)

result = await service.process_event(event, correlation_id="req-123")
if result.success:
    print(f"Event processed: {result.status}")
```

**Error Handling**: Returns `WebhookResult` with `success=False` and `status=FAILED` on processing errors

### verify_signature

**Method**: `def verify_signature(payload: str, signature: str, merchant_id: str) -> bool`

**Purpose**: Verify HMAC signature on webhook payload.

**Parameters**:
- `payload: str` - JSON payload string
- `signature: str` - Signature header (format: `sha256=<hex>`)
- `merchant_id: str` - Merchant identifier

**Returns**: `True` if signature is valid

**Example**:
```python
is_valid = service.verify_signature(
    payload='{"event_id":"evt_123","type":"order.confirmed"}',
    signature="sha256=abc123...",
    merchant_id="merchant-a"
)
```

**Error Cases**:
- Missing signature → returns `False` (line 136)
- Invalid format → returns `False` (line 145)
- Signature mismatch → returns `False` (line 163)

---

## Business Logic & Rules

### Deduplication Rules

**Duplicate Detection**: Checks if event exists by `merchant_id:event_id` key (line 332)

**Duplicate Handling**: Returns `WebhookResult` with `status=DUPLICATE` and `duplicate=True` (lines 338-344)

**Payload Hash**: Uses SHA-256 hash of normalized payload for deduplication (line 89)

**Normalization**: JSON payload sorted by keys for consistent hashing (line 87)

### Event Processing Rules

**Event Routing**: Routes events to appropriate handlers based on `event_type`:
- Order events → OrderService (lines 360-370)
- Checkout events → CheckoutService (lines 350-359)
- Price/Stock events → CatalogService (future)

**Status Transitions**:
- RECEIVED → PROCESSING → PROCESSED/FAILED
- Duplicate events → DUPLICATE (immediate)

**Error Handling**: Failed events stored with error message and status=FAILED

### Out-of-Order Tolerance

**Current Implementation**: Events processed in order received

**Future Enhancement**: Will support out-of-order processing with sequence numbers

---

## Implementation Details

### Signature Verification

**Algorithm**: HMAC-SHA256

**Secret Source**: `settings.webhook_secret` (line 123)

**Constant-Time Comparison**: Uses `hmac.compare_digest()` to prevent timing attacks (line 163)

**Error Handling**: Returns `False` on invalid format or mismatch (lines 136-168)

**Logging**: Logs warnings for invalid signatures (lines 137-150, 164-167)

### Event Storage

**Storage Format**: Dictionary with composite key `merchant_id:event_id`

**Metadata Stored**:
- Event identification (event_id, merchant_id, event_type)
- Payload (data, payload_hash)
- Timestamps (received_at, processed_at)
- Status tracking (status, error_message, correlation_id)

**Future Migration**: Will use PostgreSQL `event_log` table with indexes on:
- `(merchant_id, event_id)` for deduplication
- `event_type` for filtering
- `received_at` for time-based queries

### Event Processing

**Order Events** (Lines 360-370):
- `ORDER_CONFIRMED` → calls `order_service.confirm_order()`
- `ORDER_SHIPPED` → calls `order_service.ship_order()`
- `ORDER_DELIVERED` → calls `order_service.deliver_order()`
- `ORDER_CANCELLED` → calls `order_service.cancel_order()`
- `ORDER_REFUNDED` → calls `order_service.refund_order()`

**Checkout Events** (Lines 350-359):
- `CHECKOUT_CONFIRMED` → calls `checkout_service.confirm()`
- `CHECKOUT_FAILED` → updates checkout status
- `CHECKOUT_EXPIRED` → updates checkout status

---

## Security Considerations

### Signature Verification

**HMAC-SHA256**: Industry-standard algorithm for webhook signatures

**Secret Management**: Secret stored in environment variable (`WEBHOOK_SECRET`)

**Constant-Time Comparison**: Prevents timing attacks

**Signature Format Validation**: Validates `sha256=<hex>` format before verification

### Payload Validation

**JSON Parsing**: Validates JSON structure

**Event Type Validation**: Ensures event_type is valid enum value

**Merchant Validation**: Verifies merchant_id exists in registry

### Event Replay Protection

**Deduplication**: Prevents processing same event twice

**Payload Hash**: Uses hash for reliable duplicate detection

**Idempotency**: Event processing is idempotent (safe to retry)

---

## Code Examples

### Processing Webhook Event

```python
from app.application.webhook_service import WebhookService, WebhookEvent, WebhookEventType
import json

service = WebhookService()

# Create event from webhook payload
event = WebhookEvent(
    event_id=payload["event_id"],
    event_type=WebhookEventType(payload["event_type"]),
    merchant_id=payload["merchant_id"],
    timestamp=datetime.fromisoformat(payload["timestamp"]),
    data=payload["data"],
    signature=headers.get("X-Webhook-Signature")
)

# Verify signature
if not service.verify_signature(json.dumps(payload), event.signature, event.merchant_id):
    return {"error": "Invalid signature"}, 401

# Process event
result = await service.process_event(event, correlation_id=request_id)
return {"status": result.status.value, "event_id": result.event_id}
```

### Handling Duplicate Events

```python
result = await service.process_event(event)

if result.duplicate:
    logger.info("Duplicate event ignored", event_id=result.event_id)
    return {"status": "duplicate"}, 200

if not result.success:
    logger.error("Event processing failed", error=result.message)
    return {"error": result.message}, 500
```

### Event Processing with Error Handling

```python
try:
    result = await service.process_event(event, correlation_id=request_id)
    
    if result.success:
        logger.info("Event processed successfully", event_id=result.event_id)
    else:
        logger.error("Event processing failed", 
                    event_id=result.event_id, 
                    error=result.message)
except Exception as e:
    logger.exception("Unexpected error processing event", event_id=event.event_id)
    raise
```

---

## Summary

This detailed documentation covers webhook processing, signature verification, event deduplication, and security considerations for developers working with the WebhookService component.
