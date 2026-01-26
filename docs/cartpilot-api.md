# CartPilot API Module

## Overview

CartPilot API is the core orchestration backend for agent-first commerce. It provides a RESTful API that coordinates purchase workflows between AI agents and merchant services, implementing a UCP-compatible contract.

## Purpose

- **Orchestration**: Coordinates the complete purchase flow from intent creation to order fulfillment
- **State Management**: Manages checkout and order state machines with deterministic transitions
- **Merchant Integration**: Discovers and communicates with multiple merchant services
- **Webhook Processing**: Handles merchant webhooks with deduplication and idempotency
- **Approval Workflows**: Implements agent-safe approval mechanisms for purchases

## Architecture

The module follows a clean architecture pattern with clear separation of concerns:

```
app/
├── api/              # FastAPI routes, request/response schemas
├── application/      # Use cases and business workflows
├── domain/           # Core entities, state machines, value objects
├── infrastructure/   # Database, HTTP clients, configuration
└── catalog/          # Product catalog generation and management
```

## Key Components

### API Layer (`app/api/`)

- **intents.py**: Purchase intent creation and management
- **offers.py**: Offer retrieval and details
- **checkouts.py**: Checkout lifecycle management
- **orders.py**: Order status and lifecycle operations
- **webhooks.py**: Merchant webhook reception and processing
- **merchants.py**: Merchant discovery and configuration
- **middleware.py**: Request ID, authentication, error handling
- **idempotency.py**: Idempotency key handling middleware

### Application Layer (`app/application/`)

- **intent_service.py**: Intent creation and query processing
- **checkout_service.py**: Checkout workflow orchestration (754 lines)
- **order_service.py**: Order state management and lifecycle
- **webhook_service.py**: Webhook deduplication and event processing
- **idempotency_service.py**: Idempotency key validation

### Domain Layer (`app/domain/`)

- **entities.py**: Core domain entities (Intent, Checkout, Order)
- **state_machines.py**: State machine definitions for checkouts and orders
- **value_objects.py**: Domain value objects (Price, Address, etc.)
- **events.py**: Domain events
- **exceptions.py**: Domain-specific exceptions

### Infrastructure Layer (`app/infrastructure/`)

- **database.py**: SQLAlchemy database setup and session management
- **merchant_client.py**: HTTP client for merchant communication
- **models.py**: SQLAlchemy ORM models
- **config.py**: Application configuration and settings

### Catalog Layer (`app/catalog/`)

- **service.py**: Catalog service for product search
- **generator.py**: Synthetic product catalog generation
- **taxonomy.py**: Product taxonomy and categorization
- **repository.py**: Catalog data access
- **models.py**: Catalog data models

## Key Features

### State Machines

**Checkout State Machine:**
```
created → quoted → awaiting_approval → approved → confirmed
                                              ↓
                                           failed
```

**Order State Machine:**
```
pending → confirmed → shipped → delivered
    ↓          ↓          ↓
cancelled ← cancelled ← cancelled → refunded
```

### Idempotency

All state-changing operations support idempotency keys to ensure safe retries and prevent duplicate operations.

### Webhook Handling

- Deduplication using webhook event IDs
- Idempotent processing
- Support for out-of-order webhook delivery
- Event logging and status tracking

### Merchant Discovery

Dynamic merchant discovery with enable/disable configuration. Supports multiple merchants with different behaviors (happy path vs chaos mode).

## API Endpoints

### Intents
- `POST /intents` - Create purchase intent from natural language
- `GET /intents/{id}` - Get intent details
- `GET /intents/{id}/offers` - Get offers from merchants

### Checkouts
- `POST /checkouts` - Create checkout from offer
- `GET /checkouts/{id}` - Get checkout status
- `POST /checkouts/{id}/quote` - Get quote from merchant
- `POST /checkouts/{id}/request-approval` - Request human approval
- `POST /checkouts/{id}/approve` - Approve purchase
- `POST /checkouts/{id}/confirm` - Execute purchase

### Orders
- `GET /orders` - List orders (paginated)
- `GET /orders/{id}` - Get order details
- `POST /orders/{id}/cancel` - Cancel order
- `POST /orders/{id}/refund` - Refund order
- `POST /orders/{id}/simulate-advance` - Advance order state (testing)

### Webhooks
- `POST /webhooks/merchant` - Receive merchant webhooks
- `GET /webhooks/events/{id}` - Get webhook event status

## Database

Uses PostgreSQL with Alembic for migrations. Key tables:
- `products` - Product catalog
- `intents` - Purchase intents
- `checkouts` - Checkout sessions
- `orders` - Orders
- `webhook_events` - Webhook event log

## Configuration

Key environment variables:
- `DATABASE_URL` - PostgreSQL connection string
- `CARTPILOT_API_KEY` - API authentication key
- `WEBHOOK_SECRET` - HMAC secret for webhook verification
- `MERCHANT_A_ENABLED` - Enable Merchant A
- `MERCHANT_B_ENABLED` - Enable Merchant B
- `CATALOG_SEED_MODE` - Catalog size (small/full)

## Testing

Comprehensive test suite:
- **API tests** (`tests/api/`) - Endpoint testing
- **Domain tests** (`tests/domain/`) - Business logic testing
- **E2E tests** (`tests/e2e/`) - Full workflow scenarios
- **Catalog tests** (`tests/catalog/`) - Catalog functionality

## Dependencies

- FastAPI - Web framework
- SQLAlchemy - ORM
- Alembic - Database migrations
- Pydantic - Data validation
- Structlog - Structured logging
- httpx - HTTP client
