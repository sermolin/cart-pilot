# Merchant B Module

## Overview

Merchant B is a chaos-mode merchant simulator designed for resilience testing. It implements the same UCP-compatible contract as Merchant A but includes configurable chaos behaviors to test edge cases and error handling.

## Purpose

- **Resilience Testing**: Test how CartPilot handles edge cases and failures
- **Chaos Engineering**: Simulate real-world merchant failures
- **Error Scenarios**: Test price changes, stock issues, webhook problems
- **UCP Compliance**: Same contract as Merchant A, different behavior

## Architecture

```
merchant-b/
├── app/
│   ├── main.py          # FastAPI application with chaos endpoints
│   ├── products.py       # Product catalog with chaos triggers
│   ├── checkout.py       # Checkout with chaos integration
│   ├── webhooks.py       # Webhook sender with chaos behaviors
│   ├── chaos.py          # Chaos controller and scenarios
│   └── schemas.py        # Pydantic schemas including chaos config
└── tests/                # Test suite including chaos tests
```

## Key Features

### Chaos Scenarios

Merchant B supports 5 configurable chaos scenarios:

#### 1. PRICE_CHANGE
Prices change between quote and confirm, causing checkout failures.

**Behavior:**
- Quote created with original price
- Price changes before confirmation
- Confirmation fails with `PRICE_CHANGED` error
- Webhook sent for failed checkout

**Configuration:**
- `price_change_percent` - Percentage change (default: 20%)

#### 2. OUT_OF_STOCK
Items become unavailable after checkout creation.

**Behavior:**
- Quote created successfully
- Stock depleted before confirmation
- Confirmation fails with `OUT_OF_STOCK` error
- Webhook sent for failed checkout

**Configuration:**
- Can be triggered per product/variant

#### 3. DUPLICATE_WEBHOOK
Same webhook sent multiple times.

**Behavior:**
- Webhook sent normally
- Same webhook sent again (duplicate)
- Tests CartPilot deduplication

**Configuration:**
- `duplicate_count` - Number of duplicates (default: 1)

#### 4. DELAYED_WEBHOOK
Webhooks delivered after a delay.

**Behavior:**
- Webhook queued instead of sent immediately
- Delivered after configured delay
- Tests async webhook handling

**Configuration:**
- `delay_seconds` - Delay in seconds (default: 5)

#### 5. OUT_OF_ORDER_WEBHOOK
Webhooks sent in wrong sequence.

**Behavior:**
- Webhooks queued instead of sent
- Sent in random order when flushed
- Tests out-of-order webhook handling

**Configuration:**
- Webhooks queued until manual flush

## API Endpoints

### Standard UCP Endpoints

Same as Merchant A:
- `GET /health` - Health check (includes chaos status)
- `GET /stats` - Store statistics (includes chaos event count)
- `GET /products` - List products
- `GET /products/{product_id}` - Get product details
- `POST /checkout/quote` - Create quote
- `GET /checkout/{checkout_id}` - Get checkout status
- `POST /checkout/{checkout_id}/confirm` - Confirm checkout

### Chaos Management Endpoints

- `POST /chaos/configure` - Configure chaos scenarios
- `GET /chaos/config` - Get current chaos configuration
- `POST /chaos/enable` - Enable all chaos scenarios
- `POST /chaos/disable` - Disable all chaos scenarios
- `POST /chaos/scenarios/{scenario}/enable` - Enable specific scenario
- `POST /chaos/scenarios/{scenario}/disable` - Disable specific scenario
- `GET /chaos/events` - Get chaos event log
- `DELETE /chaos/events` - Clear chaos event log
- `POST /chaos/reset` - Reset chaos controller
- `POST /chaos/flush-webhooks` - Flush pending webhooks (for out-of-order)

### Admin Endpoints

- `POST /admin/reset` - Reset all state (products, checkouts, chaos)
- `POST /admin/trigger-price-change/{product_id}` - Manually trigger price change
- `POST /admin/trigger-out-of-stock/{product_id}` - Manually mark as out of stock
- `POST /admin/reset-product/{product_id}` - Reset product to original state

## Key Components

### ChaosController (`app/chaos.py`)

Central controller for chaos scenarios:
- Scenario enable/disable
- Configuration management
- Event logging
- State tracking

**Configuration Structure:**
```python
{
    "enabled": bool,
    "scenarios": {
        "price_change": bool,
        "out_of_stock": bool,
        "duplicate_webhook": bool,
        "delayed_webhook": bool,
        "out_of_order_webhook": bool
    },
    "price_change_percent": int,
    "duplicate_count": int,
    "delay_seconds": int
}
```

### ProductStore (`app/products.py`)

Extended product catalog with chaos support:
- Price change triggers
- Stock manipulation
- Product reset functionality
- Chaos-aware operations

### CheckoutStore (`app/checkout.py`)

Checkout with chaos integration:
- Checks chaos scenarios before confirmation
- Triggers price change failures
- Triggers out-of-stock failures
- Integrates with ChaosController

### WebhookSender (`app/webhooks.py`)

Webhook delivery with chaos behaviors:
- Duplicate webhook sending
- Delayed webhook delivery
- Out-of-order webhook queuing
- Chaos event logging

## Configuration

Key environment variables:
- `MERCHANT_ID` - Merchant identifier (default: `merchant-b`)
- `WEBHOOK_URL` - CartPilot webhook endpoint
- `WEBHOOK_SECRET` - HMAC secret for webhooks
- `CHAOS_ENABLED` - Auto-enable chaos on startup (default: `false`)
- `PRODUCTS_PER_CATEGORY` - Products per category (default: 5)
- `RANDOM_SEED` - Random seed (default: 43, different from Merchant A)
- `LOG_LEVEL` - Logging level (default: `INFO`)

## Usage Examples

### Enable Price Change Chaos

```bash
curl -X POST http://localhost:8002/chaos/configure \
  -H "Content-Type: application/json" \
  -d '{
    "scenarios": {"price_change": true},
    "price_change_percent": 20
  }'
```

### Enable All Chaos Scenarios

```bash
curl -X POST http://localhost:8002/chaos/enable
```

### Check Chaos Status

```bash
curl http://localhost:8002/chaos/config
```

### View Chaos Events

```bash
curl http://localhost:8002/chaos/events?limit=50
```

### Test Out-of-Order Webhooks

```bash
# Enable out-of-order webhook chaos
curl -X POST http://localhost:8002/chaos/scenarios/out_of_order_webhook/enable

# Perform checkout (webhooks will be queued)
# ... checkout operations ...

# Flush webhooks in random order
curl -X POST http://localhost:8002/chaos/flush-webhooks
```

## Testing Scenarios

Merchant B enables testing of:

1. **Price Change Handling**: CartPilot detects price changes and requires re-approval
2. **Stock Management**: Out-of-stock scenarios handled gracefully
3. **Webhook Deduplication**: Duplicate webhooks processed idempotently
4. **Async Webhooks**: Delayed webhooks handled correctly
5. **Out-of-Order Events**: Late-arriving webhooks processed in correct order

## Chaos Event Log

All chaos events are logged with:
- Timestamp
- Scenario name
- Checkout ID (if applicable)
- Event details
- Success/failure status

Query events:
```bash
# Get all events
GET /chaos/events

# Filter by scenario
GET /chaos/events?scenario=price_change

# Filter by checkout
GET /chaos/events?checkout_id=checkout-123
```

## Differences from Merchant A

| Feature | Merchant A | Merchant B |
|---------|-----------|-----------|
| **Purpose** | Happy path | Resilience testing |
| **Chaos Mode** | None | Configurable |
| **Price Stability** | Always stable | Can change |
| **Stock** | Always available | Can go out of stock |
| **Webhooks** | Immediate, reliable | Can be delayed/duplicated |
| **Random Seed** | 42 | 43 (different products) |
| **Chaos Endpoints** | None | Full chaos API |

## Testing

Test suite includes:
- `test_api.py` - Standard API tests
- `test_products.py` - Product catalog tests
- `test_chaos.py` - Chaos scenario tests
- `test_webhooks.py` - Webhook chaos tests

## Use Cases

### Resilience Testing

Use Merchant B to test:
- Error handling in CartPilot
- Webhook deduplication
- Price change detection
- Stock management
- Out-of-order event processing

### Chaos Engineering

Demonstrates:
- How to build chaos testing into merchant simulators
- Configurable failure modes
- Event logging and observability
- Recovery mechanisms

## Dependencies

- FastAPI - Web framework
- Pydantic - Data validation
- Structlog - Structured logging
- httpx - HTTP client for webhooks
