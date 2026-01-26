# CartPilot Architecture Overview

## Executive Summary

CartPilot is an **agent-first commerce orchestration backend** designed to provide a stable, deterministic platform for AI assistants to perform test purchases. The system is built around a UCP-compatible contract and demonstrates protocol-first design, agent-safe approval workflows, deterministic state machines, and robust webhook handling.

## System Architecture

### High-Level Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client Layer                             │
├─────────────────────────────────────────────────────────────────┤
│  AI Agents (Claude, ChatGPT, Gemini)  │  REST Clients (Postman) │
└──────────────┬────────────────────────┴──────────────┬───────────┘
               │                                       │
               │ MCP Protocol                          │ REST API
               │ (SSE/stdio)                           │ (HTTP)
               ▼                                       ▼
┌──────────────────────────┐              ┌──────────────────────────┐
│   CartPilot MCP Server   │              │    CartPilot API          │
│   (cartpilot-mcp)        │              │    (cartpilot-api)        │
│                          │              │                           │
│  - MCP Tools Adapter     │──────────────│  - FastAPI Application   │
│  - SSE/stdio Transport   │  HTTP       │  - Domain Logic           │
│  - Tool Orchestration    │              │  - State Machines        │
└──────────────────────────┘              │  - Business Rules         │
                                          └───────────┬───────────────┘
                                                      │
                                                      │ SQLAlchemy
                                                      │ AsyncPG
                                                      ▼
                                          ┌──────────────────────────┐
                                          │    PostgreSQL Database    │
                                          │    (cartpilot-db)         │
                                          │                           │
                                          │  - Intents                │
                                          │  - Offers                 │
                                          │  - Checkouts              │
                                          │  - Orders                 │
                                          │  - Webhooks               │
                                          └──────────────────────────┘
                                                      │
                                                      │
                          ┌──────────────────────────┴───────────────┐
                          │                                          │
                          │ HTTP                                     │ HTTP
                          ▼                                          ▼
              ┌──────────────────────┐              ┌──────────────────────┐
              │    Merchant A         │              │    Merchant B         │
              │    (merchant-a)       │              │    (merchant-b)        │
              │                       │              │                       │
              │  - Happy Path         │              │  - Chaos Mode         │
              │  - Product Catalog    │              │  - Edge Cases         │
              │  - Checkout API       │              │  - Testing Scenarios  │
              │  - Webhook Sender     │              │  - Webhook Sender     │
              └───────────────────────┘              └───────────────────────┘
```

## Core Components

### 1. CartPilot API (`cartpilot-api`)

The core orchestration backend built with FastAPI, implementing a clean architecture pattern with clear separation of concerns.

#### Architecture Layers

**API Layer** (`app/api/`)
- FastAPI route handlers
- Request/response schemas (Pydantic)
- Authentication middleware (Bearer token)
- Idempotency middleware
- Error handling and validation

**Application Layer** (`app/application/`)
- Use case orchestration
- Business workflow coordination
- Service composition
- Transaction boundaries

**Domain Layer** (`app/domain/`)
- **Entities**: Core business objects (Cart, Order, Checkout, Intent, Offer, Approval)
- **Value Objects**: Immutable domain concepts (Money, Address, typed IDs)
- **State Machines**: Deterministic state transitions (CartStatus, OrderStatus, ApprovalStatus)
- **Domain Events**: Significant domain occurrences
- **Exceptions**: Domain-specific errors

**Infrastructure Layer** (`app/infrastructure/`)
- Database access (SQLAlchemy + AsyncPG)
- HTTP clients for merchant communication
- Configuration management
- External service adapters

#### Key Features

- **State Machines**: Enforce deterministic state transitions for carts, orders, and approvals
- **Idempotency**: Request-level idempotency using idempotency keys
- **Webhook Handling**: Deduplication and out-of-order processing
- **Merchant Abstraction**: Unified interface for multiple merchant integrations
- **Approval Workflows**: Agent-safe approval mechanisms with frozen receipts

### 2. CartPilot MCP Server (`cartpilot-mcp`)

A thin adapter layer that exposes CartPilot capabilities as MCP (Model Context Protocol) tools for AI agent integration.

#### Architecture

- **Transport Modes**:
  - `stdio`: For local use with AI agents (Claude Desktop, Cursor)
  - `sse`: For Docker/HTTP use via Server-Sent Events

- **Tool Set** (8 tools):
  1. `create_intent` - Create purchase intent from natural language
  2. `list_offers` - Get offers from merchants for an intent
  3. `get_offer_details` - Get detailed offer information
  4. `request_approval` - Initiate approval flow for a purchase
  5. `approve_purchase` - Approve and optionally confirm purchase
  6. `get_order_status` - Check order status and tracking
  7. `simulate_time` - Advance order state for testing
  8. `trigger_chaos_case` - Enable chaos scenarios for resilience testing

- **Implementation**: Thin wrapper over CartPilot REST API using HTTP client

### 3. Merchant Simulators

Two merchant simulators that implement a common merchant API contract:

#### Merchant A (`merchant-a`)
- **Purpose**: Happy path testing
- **Behavior**: Reliable, predictable responses
- **Features**:
  - Product catalog with search
  - Checkout quote generation
  - Order confirmation
  - Webhook delivery

#### Merchant B (`merchant-b`)
- **Purpose**: Chaos engineering and resilience testing
- **Behavior**: Configurable edge cases and failures
- **Chaos Scenarios**:
  - Price changes during checkout
  - Out-of-stock conditions
  - Duplicate webhooks
  - Delayed webhooks
  - Out-of-order webhooks

### 4. PostgreSQL Database (`cartpilot-db`)

Persistent storage for all domain entities and system state.

#### Schema Components

- **Products**: Catalog data (seeded from taxonomy)
- **Intents**: Purchase intentions from users
- **Offers**: Merchant product offerings
- **Checkouts**: Checkout sessions and quotes
- **Orders**: Completed purchases
- **Webhooks**: Incoming webhook events with deduplication

#### Migration Management

- Alembic for schema versioning
- Automatic migrations on startup (via docker-entrypoint.sh)

## Data Flow

### Purchase Flow

```
1. Intent Creation
   AI Agent → MCP Server → CartPilot API → Intent Entity → Database

2. Offer Collection
   CartPilot API → Merchant Clients (parallel) → Merchant APIs
   Merchant APIs → CartPilot API → Offer Entities → Database

3. Checkout Initiation
   AI Agent → MCP Server → CartPilot API → Checkout Entity
   CartPilot API → Merchant API (quote) → Checkout Entity → Database

4. Approval Flow
   CartPilot API → Frozen Receipt Generation
   AI Agent → Approval Request → Approval Entity
   Approval → Checkout State Transition

5. Order Confirmation
   CartPilot API → Merchant API (confirm) → Order Entity → Database
   Merchant API → Webhook → CartPilot API → Order State Update

6. Order Lifecycle
   Webhooks → Order State Machine → State Transitions
   (pending → confirmed → shipped → delivered)
```

### Webhook Flow

```
Merchant → HTTP POST → CartPilot API Webhook Endpoint
         ↓
    Idempotency Check (event_id)
         ↓
    Deduplication Logic
         ↓
    Order State Update
         ↓
    Database Persistence
```

## Design Patterns

### 1. Clean Architecture / Hexagonal Architecture

- **Domain Layer**: Core business logic, independent of infrastructure
- **Application Layer**: Use cases and orchestration
- **Infrastructure Layer**: External concerns (database, HTTP, config)
- **API Layer**: Entry points and adapters

### 2. Domain-Driven Design (DDD)

- **Aggregate Roots**: Cart, Order, Checkout, Intent
- **Value Objects**: Money, Address, typed IDs
- **Domain Events**: CartCreated, OrderConfirmed, ApprovalRequested
- **State Machines**: Enforce business rules through state transitions

### 3. Repository Pattern

- Abstract data access behind repository interfaces
- In-memory repositories for intents/offers (can be replaced with DB)
- Database repositories for persistent entities

### 4. Factory Pattern

- `MerchantClientFactory`: Creates and manages merchant HTTP clients
- `MerchantRegistry`: Discovers and manages merchant configurations

### 5. Adapter Pattern

- MCP Server adapts REST API to MCP protocol
- Merchant clients adapt merchant APIs to unified interface

## Technology Stack

### Backend
- **Language**: Python 3.11+
- **Framework**: FastAPI
- **Database**: PostgreSQL 16
- **ORM**: SQLAlchemy (async)
- **Migrations**: Alembic
- **HTTP Client**: httpx (async)
- **Logging**: structlog

### Protocol & Integration
- **MCP**: Model Context Protocol (MCP SDK)
- **Transport**: stdio (local) / SSE (HTTP)
- **API**: REST with OpenAPI specification

### Infrastructure
- **Containerization**: Docker
- **Orchestration**: Docker Compose
- **Deployment**: Google Cloud Run (optional)
- **Database**: Cloud SQL (optional)

## Key Architectural Decisions

### 1. Protocol-First Design
- UCP-compatible contract ensures interoperability
- Clear API boundaries and contracts
- OpenAPI specification for API documentation

### 2. Deterministic State Machines
- All state transitions are explicit and validated
- Prevents invalid state transitions
- Makes system behavior predictable for AI agents

### 3. Idempotency
- Request-level idempotency using idempotency keys
- Prevents duplicate operations
- Critical for agent retry scenarios

### 4. Webhook Deduplication
- Event-level deduplication using event IDs
- Handles out-of-order webhook delivery
- Ensures idempotent webhook processing

### 5. Agent-Safe Approval Workflows
- Frozen receipts prevent price changes after approval
- Explicit approval states
- Clear separation between approval and confirmation

### 6. Merchant Abstraction
- Unified interface for multiple merchants
- Parallel offer collection
- Graceful degradation on merchant failures

### 7. Chaos Engineering
- Built-in chaos scenarios for resilience testing
- Configurable failure modes
- Validates system behavior under adverse conditions

## Scalability Considerations

### Horizontal Scaling
- Stateless API design enables horizontal scaling
- Database connection pooling (AsyncPG)
- Merchant client connection reuse

### Performance
- Async/await throughout for non-blocking I/O
- Parallel merchant queries for offer collection
- Efficient database queries with proper indexing

### Reliability
- Health checks for all services
- Graceful error handling
- Retry logic for merchant API calls
- Webhook retry mechanisms

## Security

### Authentication
- Bearer token authentication for API access
- Configurable API keys per environment

### Webhook Security
- HMAC signature verification for webhooks
- Configurable webhook secrets

### Data Protection
- Environment-based configuration
- Secrets management (via environment variables)
- No hardcoded credentials

## Deployment Architecture

### Local Development
- Docker Compose orchestrates all services
- Single PostgreSQL instance
- Service discovery via Docker networking

### Production (GCP)
- **Cloud Run**: Serverless containers for API and MCP server
- **Cloud SQL**: Managed PostgreSQL instance
- **Artifact Registry**: Docker image storage
- **Private IP**: Database connectivity via private IP

## Integration Points

### AI Agent Integrations

1. **MCP Server** (Claude, Cline, VS Code)
   - SSE transport over HTTP
   - 8 MCP tools

2. **ChatGPT Actions**
   - OpenAPI specification import
   - REST API integration
   - Custom GPT configuration

3. **Gemini Function Calling**
   - Python client library
   - Function declarations
   - Interactive chat interface

### External Systems

- **Merchant APIs**: HTTP REST APIs
- **Webhooks**: Incoming HTTP POST from merchants
- **Database**: PostgreSQL via SQLAlchemy

## Monitoring & Observability

### Logging
- Structured logging with structlog
- JSON format for production
- Request ID correlation throughout

### Health Checks
- `/health` endpoint on all services
- Database connectivity checks
- Merchant availability checks

### Error Handling
- Consistent error response format
- Error codes for categorization
- Request ID for traceability

## Future Considerations

### Potential Enhancements
- Event sourcing for audit trail
- CQRS for read/write separation
- GraphQL API option
- Real-time order tracking via WebSockets
- Multi-region deployment
- Advanced caching strategies
- Rate limiting and throttling
- Enhanced monitoring and metrics

### Extensibility
- Plugin architecture for merchant integrations
- Custom state machine extensions
- Additional approval workflows
- Multi-currency support
- Tax calculation integration
