# IntentService - Detailed Component Documentation

> **Complete technical documentation for the IntentService component**  
> This document provides comprehensive details for developers working with or extending the intent service.

## Table of Contents

1. [Overview](#overview)
2. [Architecture & Design](#architecture--design)
3. [Component Details](#component-details)
4. [API Reference](#api-reference)
5. [Business Logic & Rules](#business-logic--rules)
6. [Implementation Details](#implementation-details)
7. [Code Examples](#code-examples)

---

## Overview

### Purpose

The `IntentService` orchestrates the creation of purchase intents from user queries and collection of offers from multiple merchants. It handles merchant discovery, product search, offer normalization, and storage.

**Location**: `cartpilot-api/app/application/intent_service.py`  
**Lines of Code**: ~504 lines  
**Dependencies**: MerchantClientFactory, domain entities (Intent, Offer)

### Responsibilities

- **Intent Creation**: Create purchase intents from natural language queries
- **Merchant Discovery**: Find enabled merchants
- **Offer Collection**: Collect offers from multiple merchants concurrently
- **Offer Normalization**: Normalize merchant products into domain offers
- **Storage**: Persist intents and offers

### Key Metrics

- **Public Methods**: 3 main operations
- **Repositories**: IntentRepository, OfferRepository
- **Concurrent Operations**: Parallel merchant API calls using asyncio.gather

---

## Architecture & Design

### Class Structure

```python
class IntentService:
    """Application service for managing purchase intents and offers."""
    
    def __init__(
        self,
        intent_repo: IntentRepository | None = None,
        offer_repo: OfferRepository | None = None,
        request_id: str | None = None,
    ) -> None
    
    async def create_intent(query: str, session_id: str | None = None, metadata: dict[str, Any] | None = None) -> CreateIntentResult
    async def collect_offers(intent_id: str, merchant_ids: list[str] | None = None) -> CollectOffersResult
    async def get_intent(intent_id: str) -> Intent | None
```

### Dependency Graph

```
IntentService
├── IntentRepository (in-memory)
│   └── _intents: dict[str, Intent]
├── OfferRepository (in-memory)
│   ├── _offers: dict[str, Offer]
│   └── _by_intent: dict[str, list[str]]
├── MerchantClientFactory
│   └── MerchantClient (per merchant)
└── Domain Entities
    ├── Intent (AggregateRoot)
    └── Offer (Entity)
```

### Design Patterns

1. **Repository Pattern**: IntentRepository, OfferRepository
2. **Service Layer Pattern**: Encapsulates business logic
3. **Factory Pattern**: MerchantClientFactory for merchant clients
4. **Concurrent Processing**: asyncio.gather for parallel API calls

---

## Component Details

### IntentRepository

**Location**: Lines 31-54

**Purpose**: In-memory storage for intents (temporary implementation).

**Storage Structure**:
```python
class IntentRepository:
    def __init__(self) -> None:
        self._intents: dict[str, Intent] = {}
```

**Methods**:
- `save(intent: Intent) -> None`: Persist intent
- `get(intent_id: str) -> Intent | None`: Retrieve by ID
- `list_all(page, page_size) -> tuple[list[Intent], int]`: Paginated listing sorted by created_at

**Singleton Pattern**: Global instance via `get_intent_repository()`

### OfferRepository

**Location**: Lines 57-91

**Purpose**: In-memory storage for offers (temporary implementation).

**Storage Structure**:
```python
class OfferRepository:
    def __init__(self) -> None:
        self._offers: dict[str, Offer] = {}
        self._by_intent: dict[str, list[str]] = {}
```

**Methods**:
- `save(offer: Offer) -> None`: Persist offer and index by intent
- `get(offer_id: str) -> Offer | None`: Retrieve by ID
- `get_by_intent(intent_id: str, page, page_size) -> tuple[list[Offer], int]`: Get offers for intent

**Indexing**: Maintains `_by_intent` mapping for efficient lookup

### Result Types

**Location**: Lines 108-157

```python
@dataclass
class CreateIntentResult:
    intent: Intent | None = None
    success: bool = True
    error: str | None = None
    error_code: str | None = None

@dataclass
class CollectOffersResult:
    offers: list[Offer] = field(default_factory=list)
    success: bool = True
    error: str | None = None
    error_code: str | None = None
    merchant_errors: dict[str, str] = field(default_factory=dict)
```

---

## API Reference

### create_intent

**Method**: `async def create_intent(query: str, session_id: str | None = None, metadata: dict[str, Any] | None = None) -> CreateIntentResult`

**Purpose**: Create a new purchase intent from a natural language query.

**Parameters**:
- `query: str` - Natural language search query
- `session_id: str | None` - Optional session identifier
- `metadata: dict[str, Any] | None` - Optional metadata

**Returns**: `CreateIntentResult` with created intent

**Example**:
```python
result = await service.create_intent(
    query="I need a laptop under $1000",
    session_id="session-123",
    metadata={"user_id": "user-456"}
)

if result.success:
    intent = result.intent
    print(f"Intent created: {intent.id}")
    print(f"Query: {intent.query}")
```

**Error Codes**:
- `CREATE_FAILED`: Unexpected error during creation

**State After**: Intent created with status and timestamps

### collect_offers

**Method**: `async def collect_offers(intent_id: str, merchant_ids: list[str] | None = None) -> CollectOffersResult`

**Purpose**: Collect offers from multiple merchants for an intent.

**Parameters**:
- `intent_id: str` - Intent identifier
- `merchant_ids: list[str] | None` - Specific merchants to query (None = all enabled)

**Returns**: `CollectOffersResult` with collected offers and merchant errors

**Flow**:
1. Get intent from repository
2. Get enabled merchant IDs (or use provided list)
3. Query each merchant concurrently using asyncio.gather
4. Normalize merchant products into domain offers
5. Save offers to repository
6. Return collected offers

**Example**:
```python
result = await service.collect_offers(
    intent_id="intent-123",
    merchant_ids=["merchant-a", "merchant-b"]
)

if result.success:
    print(f"Collected {len(result.offers)} offers")
    for offer in result.offers:
        print(f"Merchant: {offer.merchant_id}, Price: ${offer.total.amount_cents / 100}")
    
    if result.merchant_errors:
        print("Merchant errors:", result.merchant_errors)
```

**Concurrent Processing**: Uses `asyncio.gather()` for parallel merchant API calls (line 250)

**Error Handling**: Individual merchant errors stored in `merchant_errors` dict, don't fail entire operation

### get_intent

**Method**: `async def get_intent(intent_id: str) -> Intent | None`

**Purpose**: Get intent by ID.

**Parameters**:
- `intent_id: str` - Intent identifier

**Returns**: `Intent | None`

**Example**:
```python
intent = await service.get_intent("intent-123")
if intent:
    print(f"Query: {intent.query}")
    print(f"Created: {intent.created_at}")
```

---

## Business Logic & Rules

### Intent Creation Rules

**Query Validation**: Query must be non-empty string

**ID Generation**: Uses `IntentId.generate()` for unique IDs

**Timestamps**: Sets `created_at` to current UTC time

**Status**: Intent created with initial status

### Offer Collection Rules

**Merchant Discovery**: 
- If `merchant_ids` provided → use those merchants
- Otherwise → use all enabled merchants from registry

**Concurrent Queries**: All merchant queries executed in parallel

**Error Tolerance**: Individual merchant failures don't stop collection

**Offer Normalization**: Merchant products converted to domain Offer entities

**Offer Storage**: All offers saved to repository and indexed by intent_id

### Offer Normalization

**Product Mapping**:
- Merchant product → OfferItem
- Price conversion (Money value object)
- Product reference creation
- Variant handling

**Offer Creation**:
- Creates Offer entity with normalized items
- Sets merchant_id, intent_id
- Calculates total price
- Sets timestamps

---

## Implementation Details

### Concurrent Merchant Queries

**Implementation** (Lines 250-260):
```python
tasks = [
    self._collect_from_merchant(intent, merchant_id)
    for merchant_id in merchant_ids
]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

**Error Handling**: Uses `return_exceptions=True` to capture individual failures

**Result Processing**: Filters out exceptions and processes successful results

### Merchant Client Usage

**Factory Pattern**: Uses `MerchantClientFactory` as async context manager

**Client Lifecycle**:
```python
async with MerchantClientFactory() as factory:
    client = factory.get_client(merchant_id)
    products = await client.search_products(intent.query)
```

**Error Handling**: Catches `MerchantClientError` and stores in `merchant_errors`

### Offer Normalization

**Process** (Lines 270-320):
1. Extract products from merchant response
2. Create OfferItem for each product
3. Convert prices to Money value objects
4. Create ProductRef for each product
5. Calculate total price
6. Create Offer entity

**Price Handling**: Converts merchant price format to Money value object

**Variant Support**: Handles product variants if present

---

## Code Examples

### Complete Intent and Offer Flow

```python
from app.application.intent_service import IntentService, get_intent_service

service = get_intent_service()

# 1. Create intent
create_result = await service.create_intent(
    query="wireless keyboard under $50",
    session_id="session-123"
)

if not create_result.success:
    raise Exception(f"Failed to create intent: {create_result.error}")

intent_id = create_result.intent.id
print(f"Intent created: {intent_id}")

# 2. Collect offers from all merchants
collect_result = await service.collect_offers(intent_id)

if collect_result.success:
    print(f"Collected {len(collect_result.offers)} offers")
    
    # Sort by price
    sorted_offers = sorted(
        collect_result.offers,
        key=lambda o: o.total.amount_cents
    )
    
    for offer in sorted_offers:
        print(f"Merchant: {offer.merchant_id}")
        print(f"  Price: ${offer.total.amount_cents / 100}")
        print(f"  Items: {len(offer.items)}")
    
    # Handle merchant errors
    if collect_result.merchant_errors:
        print("\nMerchant errors:")
        for merchant_id, error in collect_result.merchant_errors.items():
            print(f"  {merchant_id}: {error}")
```

### Collecting from Specific Merchants

```python
# Collect offers only from specific merchants
result = await service.collect_offers(
    intent_id="intent-123",
    merchant_ids=["merchant-a", "merchant-b"]
)

if result.success:
    print(f"Found {len(result.offers)} offers from specified merchants")
```

### Error Handling

```python
result = await service.collect_offers(intent_id)

if not result.success:
    print(f"Collection failed: {result.error}")
    return

# Check for merchant-specific errors
if result.merchant_errors:
    for merchant_id, error in result.merchant_errors.items():
        logger.warning(
            "Merchant query failed",
            merchant_id=merchant_id,
            error=error
        )

# Process successful offers
for offer in result.offers:
    process_offer(offer)
```

---

## Summary

This detailed documentation covers intent creation, offer collection, concurrent merchant queries, and error handling for developers working with the IntentService component.
