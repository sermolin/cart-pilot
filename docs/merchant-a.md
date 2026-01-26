# Merchant A Module

## Overview

Merchant A is a stable, happy-path merchant simulator that implements a UCP-compatible contract. It provides reliable, predictable behavior for testing normal purchase flows without edge cases or failures.

## Purpose

- **Happy Path Testing**: Demonstrates successful purchase flows
- **UCP Compliance**: Implements Universal Commerce Protocol contract
- **Stable Behavior**: High inventory, stable pricing, reliable checkout
- **Reference Implementation**: Shows how merchants should integrate with CartPilot

## Architecture

```
merchant-a/
├── app/
│   ├── main.py          # FastAPI application
│   ├── products.py       # Product catalog management
│   ├── checkout.py       # Checkout session handling
│   ├── webhooks.py       # Webhook sending to CartPilot
│   └── schemas.py        # Pydantic schemas
└── tests/                # Test suite
```

## Key Features

### Stable Behavior

- **High Inventory**: Products always in stock
- **Stable Pricing**: Prices don't change between quote and confirm
- **Reliable Checkout**: No failures or edge cases
- **Consistent Webhooks**: Webhooks always delivered correctly

### Product Catalog

- Synthetic product catalog with multiple categories
- Configurable products per category (default: 5)
- Random seed for reproducible generation (default: 42)
- Products include:
  - Product ID, title, description
  - Variants with SKUs
  - Pricing in cents
  - Stock levels
  - Ratings and reviews

### Checkout Flow

Implements standard UCP checkout workflow:

1. **Quote** (`POST /checkout/quote`): Create checkout session with pricing
2. **Get Checkout** (`GET /checkout/{id}`): Retrieve checkout status
3. **Confirm** (`POST /checkout/{id}/confirm`): Finalize purchase and create order

### Webhook Integration

Sends webhooks to CartPilot API:
- `checkout.quoted` - When quote is created
- `checkout.confirmed` - When checkout is confirmed
- `order.created` - When order is created

## API Endpoints

### Health & Stats

- `GET /health` - Health check with merchant info
- `GET /stats` - Store statistics (product count, checkout count)

### Products

- `GET /products` - List products with filtering and pagination
  - Query parameters: `page`, `page_size`, `category_id`, `brand`, `min_price`, `max_price`, `in_stock`, `search`, `sort_by`, `sort_order`
- `GET /products/{product_id}` - Get product details

### Checkout

- `POST /checkout/quote` - Create quote for items
  - Request body: `items`, `customer_email`, `idempotency_key`
  - Returns: Checkout session with pricing
- `GET /checkout/{checkout_id}` - Get checkout status
- `POST /checkout/{checkout_id}/confirm` - Confirm checkout and create order
  - Request body: `payment_method`, `idempotency_key`
  - Returns: Confirmation with merchant order ID

## Key Components

### ProductStore (`app/products.py`)

In-memory product catalog:
- Product generation with taxonomy
- Filtering and search
- Pagination support
- Stock management (always in stock)

### CheckoutStore (`app/checkout.py`)

Checkout session management:
- Session creation and storage
- Quote generation with pricing
- Confirmation with order creation
- Idempotency support
- Expiration handling

### WebhookSender (`app/webhooks.py`)

Webhook delivery to CartPilot:
- HMAC signature generation
- Background task execution
- Retry logic
- Event logging

## Configuration

Key environment variables:
- `MERCHANT_ID` - Merchant identifier (default: `merchant-a`)
- `WEBHOOK_URL` - CartPilot webhook endpoint (default: `http://cartpilot-api:8000/webhooks/merchant`)
- `WEBHOOK_SECRET` - HMAC secret for webhooks
- `PRODUCTS_PER_CATEGORY` - Products per category (default: 5)
- `RANDOM_SEED` - Random seed for product generation (default: 42)
- `LOG_LEVEL` - Logging level (default: `INFO`)

## UCP Contract Compliance

Merchant A implements the Universal Commerce Protocol contract:

### Required Endpoints

- ✅ `GET /health` - Health check
- ✅ `GET /products` - List products
- ✅ `GET /products/{id}` - Get product
- ✅ `POST /checkout/quote` - Create quote
- ✅ `GET /checkout/{id}` - Get checkout
- ✅ `POST /checkout/{id}/confirm` - Confirm checkout

### Webhook Events

- ✅ `checkout.quoted` - Quote created
- ✅ `checkout.confirmed` - Checkout confirmed
- ✅ `order.created` - Order created

### Error Handling

Consistent error format:
```json
{
  "error_code": "ERROR_CODE",
  "message": "Human-readable message",
  "details": []
}
```

## Testing

Test suite includes:
- `test_api.py` - API endpoint tests
- `test_products.py` - Product catalog tests
- `test_checkout.py` - Checkout flow tests

## Use Cases

### Happy Path Testing

Use Merchant A for:
- Testing complete purchase flows
- Validating CartPilot integration
- Demonstrating normal operations
- Performance testing

### Reference Implementation

Merchant A serves as a reference for:
- How to implement UCP contract
- Webhook integration patterns
- Error handling conventions
- Product catalog structure

## Differences from Merchant B

| Feature | Merchant A | Merchant B |
|---------|-----------|-----------|
| **Behavior** | Stable, predictable | Chaos mode enabled |
| **Inventory** | Always in stock | Can go out of stock |
| **Pricing** | Stable | Can change |
| **Webhooks** | Reliable | Can be delayed/duplicated |
| **Use Case** | Happy path testing | Resilience testing |

## Dependencies

- FastAPI - Web framework
- Pydantic - Data validation
- Structlog - Structured logging
- httpx - HTTP client for webhooks
