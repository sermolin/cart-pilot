# MerchantClient - Detailed Component Documentation

> **Complete technical documentation for the MerchantClient component**  
> This document provides comprehensive details for developers working with or extending the merchant client.

## Table of Contents

1. [Overview](#overview)
2. [Architecture & Design](#architecture--design)
3. [Component Details](#component-details)
4. [API Reference](#api-reference)
5. [Business Logic & Rules](#business-logic--rules)
6. [Implementation Details](#implementation-details)
7. [Error Handling](#error-handling)
8. [Code Examples](#code-examples)

---

## Overview

### Purpose

The `MerchantClient` provides HTTP client functionality for communicating with merchant services. It handles product search, checkout operations, quote requests, and order confirmations with error handling and response normalization.

**Location**: `cartpilot-api/app/infrastructure/merchant_client.py`  
**Lines of Code**: ~788 lines  
**Dependencies**: httpx, MerchantRegistry

### Responsibilities

- **Product Search**: Search products across merchants
- **Checkout Operations**: Create and manage checkouts
- **Quote Requests**: Get pricing quotes for checkout items
- **Order Confirmation**: Confirm checkouts and create orders
- **Error Handling**: Normalize merchant API errors
- **Response Normalization**: Convert merchant responses to domain objects

### Key Metrics

- **Public Methods**: 6 main operations
- **Response Types**: MerchantProduct, MerchantProductList, MerchantQuoteResponse, MerchantConfirmResponse
- **Error Types**: MerchantClientError

---

## Architecture & Design

### Class Structure

```python
class MerchantClient:
    """HTTP client for communicating with a single merchant."""
    
    def __init__(
        self,
        merchant: MerchantConfig,
        timeout: float = 10.0,
        request_id: str | None = None,
    ) -> None
    
    async def health_check() -> bool
    async def search_products(query: str, page: int = 1, page_size: int = 20) -> MerchantProductList
    async def get_product(product_id: str) -> MerchantProduct
    async def create_checkout(items: list[dict[str, Any]], customer_email: str | None = None) -> dict[str, Any]
    async def get_checkout_quote(checkout_id: str, items: list[dict[str, Any]], customer_email: str | None = None) -> MerchantQuoteResponse
    async def confirm_checkout(checkout_id: str, payment_method: str = "test_card") -> MerchantConfirmResponse
    async def close() -> None

class MerchantClientFactory:
    """Factory for creating merchant clients."""
    
    async def __aenter__() -> "MerchantClientFactory"
    async def __aexit__(...) -> None
    def get_client(merchant_id: str) -> MerchantClient
    def get_enabled_merchant_ids() -> list[str]

class MerchantRegistry:
    """Registry for merchant configurations."""
    
    def register(merchant: MerchantConfig) -> None
    def get(merchant_id: str) -> MerchantConfig | None
    def get_enabled_merchant_ids() -> list[str]
```

### Design Patterns

1. **Factory Pattern**: MerchantClientFactory for creating clients
2. **Registry Pattern**: MerchantRegistry for merchant configuration
3. **Client Pattern**: HTTP client abstraction
4. **Context Manager Pattern**: Factory used as async context manager
5. **Adapter Pattern**: Normalizes merchant API responses

---

## Component Details

### MerchantConfig

**Location**: Lines 20-50

```python
@dataclass
class MerchantConfig:
    """Configuration for a merchant."""
    
    id: str
    name: str
    url: str
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
```

**Fields**:
- `id`: Unique merchant identifier
- `name`: Display name
- `url`: Base URL for merchant API
- `enabled`: Whether merchant is active
- `metadata`: Additional configuration

### MerchantProduct

**Location**: Lines 132-178

```python
@dataclass
class MerchantProduct:
    """Product data from a merchant."""
    
    id: str
    sku: str | None
    title: str
    description: str | None
    brand: str | None
    category_id: int | None
    category_path: str | None
    price_cents: int
    currency: str
    rating: float | None
    review_count: int | None
    image_url: str | None
    in_stock: bool
    stock_quantity: int
    variants: list[dict[str, Any]]
    
    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "MerchantProduct"
```

**Normalization**: Converts merchant API response to standardized format

### MerchantQuoteResponse

**Location**: Lines 235-268

```python
@dataclass
class MerchantQuoteResponse:
    """Quote response from a merchant."""
    
    checkout_id: str
    status: str
    items: list[MerchantQuoteItem]
    subtotal_cents: int
    tax_cents: int
    shipping_cents: int
    total_cents: int
    currency: str
    receipt_hash: str | None
    expires_at: str | None
```

**Quote Items**: List of `MerchantQuoteItem` with pricing details

### MerchantConfirmResponse

**Location**: Lines 272-293

```python
@dataclass
class MerchantConfirmResponse:
    """Confirmation response from a merchant."""
    
    checkout_id: str
    merchant_order_id: str
    status: str
    total_cents: int
    currency: str
    confirmed_at: str
```

---

## API Reference

### health_check

**Method**: `async def health_check() -> bool`

**Purpose**: Check merchant health status.

**Endpoint**: `GET /health`

**Returns**: `True` if merchant is healthy (status 200)

**Example**:
```python
client = factory.get_client("merchant-a")
is_healthy = await client.health_check()
if not is_healthy:
    logger.warning("Merchant is unhealthy", merchant_id="merchant-a")
```

### search_products

**Method**: `async def search_products(query: str, page: int = 1, page_size: int = 20) -> MerchantProductList`

**Purpose**: Search products across merchant catalog.

**Endpoint**: `GET /products/search`

**Parameters**:
- `query: str` - Search query string
- `page: int` - Page number (default: 1)
- `page_size: int` - Items per page (default: 20)

**Returns**: `MerchantProductList` with products and pagination info

**Example**:
```python
result = await client.search_products("laptop", page=1, page_size=20)
print(f"Found {result.total} products")
for product in result.items:
    print(f"{product.title}: ${product.price_cents / 100}")
```

**Error Handling**: Raises `MerchantClientError` on API errors

### get_product

**Method**: `async def get_product(product_id: str) -> MerchantProduct`

**Purpose**: Get product details by ID.

**Endpoint**: `GET /products/{product_id}`

**Parameters**:
- `product_id: str` - Product identifier

**Returns**: `MerchantProduct` with full details

**Example**:
```python
product = await client.get_product("prod-123")
print(f"Title: {product.title}")
print(f"Price: ${product.price_cents / 100}")
print(f"In Stock: {product.in_stock}")
```

### create_checkout

**Method**: `async def create_checkout(items: list[dict[str, Any]], customer_email: str | None = None) -> dict[str, Any]`

**Purpose**: Create a checkout session.

**Endpoint**: `POST /checkouts`

**Parameters**:
- `items: list[dict[str, Any]]` - List of items with product_id, quantity, variant_id
- `customer_email: str | None` - Optional customer email

**Returns**: Checkout creation response dict

**Example**:
```python
checkout = await client.create_checkout(
    items=[
        {"product_id": "prod-123", "quantity": 2},
        {"product_id": "prod-456", "quantity": 1, "variant_id": "var-789"}
    ],
    customer_email="user@example.com"
)
checkout_id = checkout["id"]
```

### get_checkout_quote

**Method**: `async def get_checkout_quote(checkout_id: str, items: list[dict[str, Any]], customer_email: str | None = None) -> MerchantQuoteResponse`

**Purpose**: Get pricing quote for checkout items.

**Endpoint**: `POST /checkouts/{checkout_id}/quote`

**Parameters**:
- `checkout_id: str` - Checkout identifier
- `items: list[dict[str, Any]]` - List of items
- `customer_email: str | None` - Optional customer email

**Returns**: `MerchantQuoteResponse` with pricing breakdown

**Example**:
```python
quote = await client.get_checkout_quote(
    checkout_id="checkout-123",
    items=[{"product_id": "prod-123", "quantity": 2}],
    customer_email="user@example.com"
)
print(f"Subtotal: ${quote.subtotal_cents / 100}")
print(f"Tax: ${quote.tax_cents / 100}")
print(f"Shipping: ${quote.shipping_cents / 100}")
print(f"Total: ${quote.total_cents / 100}")
```

### confirm_checkout

**Method**: `async def confirm_checkout(checkout_id: str, payment_method: str = "test_card") -> MerchantConfirmResponse`

**Purpose**: Confirm checkout and create order.

**Endpoint**: `POST /checkouts/{checkout_id}/confirm`

**Parameters**:
- `checkout_id: str` - Checkout identifier
- `payment_method: str` - Payment method (default: "test_card")

**Returns**: `MerchantConfirmResponse` with order details

**Example**:
```python
confirmation = await client.confirm_checkout(
    checkout_id="checkout-123",
    payment_method="test_card"
)
print(f"Order ID: {confirmation.merchant_order_id}")
print(f"Confirmed at: {confirmation.confirmed_at}")
```

---

## Business Logic & Rules

### Merchant Registry

**Registration**: Merchants registered via `MerchantRegistry.register()`

**Discovery**: Enabled merchants retrieved via `get_enabled_merchant_ids()`

**Configuration**: Each merchant has base URL, enabled status, metadata

### HTTP Client Management

**Lazy Initialization**: HTTP client created on first use (line 321)

**Request Headers**: Includes `X-Request-ID` if provided (line 326)

**Timeout**: Configurable timeout (default: 10.0 seconds)

**Connection Pooling**: httpx.AsyncClient manages connection pool

### Response Normalization

**Product Normalization**: Converts merchant-specific format to `MerchantProduct`

**Quote Normalization**: Converts quote response to `MerchantQuoteResponse`

**Error Normalization**: Converts HTTP errors to `MerchantClientError`

---

## Implementation Details

### HTTP Client Creation

**Lazy Initialization** (Lines 321-332):
```python
async def _get_client(self) -> httpx.AsyncClient:
    if self._client is None:
        headers = {}
        if self.request_id:
            headers["X-Request-ID"] = self.request_id
        self._client = httpx.AsyncClient(
            base_url=self.merchant.url,
            timeout=self.timeout,
            headers=headers,
        )
    return self._client
```

**Connection Management**: Client reused across requests, closed via `close()`

### Error Handling

**HTTP Errors** (Lines 350-400):
- Status 4xx/5xx → raises `MerchantClientError`
- Includes merchant_id, message, status_code

**Network Errors**: httpx exceptions wrapped in `MerchantClientError`

**Error Format**: `[{merchant_id}] {message}`

### Factory Pattern

**Context Manager** (Lines 50-80):
```python
async with MerchantClientFactory() as factory:
    client = factory.get_client("merchant-a")
    products = await client.search_products("laptop")
```

**Client Lifecycle**: Factory manages client creation and cleanup

**Registry Access**: Factory accesses MerchantRegistry for configurations

---

## Error Handling

### MerchantClientError

**Location**: Lines 192-201

```python
class MerchantClientError(Exception):
    """Error from merchant API call."""
    
    def __init__(
        self, merchant_id: str, message: str, status_code: int | None = None
    ):
        self.merchant_id = merchant_id
        self.message = message
        self.status_code = status_code
```

**Error Cases**:
- HTTP 4xx/5xx responses
- Network timeouts
- Invalid responses
- Connection errors

### Error Propagation

**Flow**:
```
HTTP Error → MerchantClientError → Service Layer → API Handler
```

**Error Information**: Includes merchant_id, message, status_code for debugging

---

## Code Examples

### Using MerchantClientFactory

```python
from app.infrastructure.merchant_client import MerchantClientFactory

async with MerchantClientFactory() as factory:
    # Get client for merchant
    client = factory.get_client("merchant-a")
    
    # Search products
    products = await client.search_products("laptop", page=1, page_size=20)
    
    # Get product details
    product = await client.get_product("prod-123")
    
    # Create checkout
    checkout = await client.create_checkout(
        items=[{"product_id": "prod-123", "quantity": 1}],
        customer_email="user@example.com"
    )
    
    # Get quote
    quote = await client.get_checkout_quote(
        checkout_id=checkout["id"],
        items=[{"product_id": "prod-123", "quantity": 1}]
    )
    
    # Confirm checkout
    confirmation = await client.confirm_checkout(checkout["id"])
```

### Error Handling

```python
try:
    products = await client.search_products("laptop")
except MerchantClientError as e:
    logger.error(
        "Merchant API error",
        merchant_id=e.merchant_id,
        status_code=e.status_code,
        message=e.message
    )
    # Handle error
```

### Querying Multiple Merchants

```python
async with MerchantClientFactory() as factory:
    merchant_ids = factory.get_enabled_merchant_ids()
    
    tasks = [
        factory.get_client(mid).search_products("laptop")
        for mid in merchant_ids
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for merchant_id, result in zip(merchant_ids, results):
        if isinstance(result, Exception):
            logger.error("Merchant query failed", merchant_id=merchant_id)
        else:
            print(f"{merchant_id}: {len(result.items)} products")
```

---

## Summary

This detailed documentation covers merchant client operations, HTTP communication, error handling, and factory pattern usage for developers working with merchant integrations.
