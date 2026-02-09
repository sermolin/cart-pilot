# CartPilot

**Agent-first commerce orchestration backend** built around a UCP-compatible contract.

## Overview

CartPilot provides a stable, deterministic backend for AI assistants to perform test purchases. It demonstrates:

- Protocol-first design (UCP-compatible)
- Agent-safe approval workflows
- Deterministic state machines
- Webhook handling with deduplication
- MCP tools for AI agent integration

## Architecture

```
┌─────────────────┐     ┌─────────────────┐
│   AI Agent      │────▶│  CartPilot MCP  │
└─────────────────┘     └────────┬────────┘
                                MCP
┌─────────────────┐     ┌────────▼────────┐     ┌─────────────────┐
│    Postman      │────▶│  CartPilot API  │────▶│   PostgreSQL    │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                UCP
                   ┌────────────-┴────────────┐
                   ▼                          ▼
          ┌───────────────┐         ┌───────────────┐
          │  Merchant A   │         │  Merchant B   │
          │ (Happy Path)  │         │ (Chaos Mode)  │
          └───────────────┘         └───────────────┘
```

## Quick Start

### Prerequisites

- Docker and Docker Compose
- (Optional) Python 3.11+ for local development

### Running with Docker Compose

```bash
# Start all services
docker compose up

# Or run in background
docker compose up -d

# View logs
docker compose logs -f cartpilot-api
```

### Service Ports

| Service        | Port | URL (from host)          |
|----------------|------|--------------------------|
| CartPilot API  | 8000 | http://localhost:8000    |
| Merchant A     | 8001 | http://localhost:8001    |
| Merchant B     | 8002 | http://localhost:8002    |
| MCP Server     | 8003 | http://localhost:8003    |
| PostgreSQL     | 5432 | localhost:5432           |

### Health Checks

```bash
# CartPilot API
curl http://localhost:8000/health

# Merchant A
curl http://localhost:8001/health

# Merchant B
curl http://localhost:8002/health

# MCP Server
curl http://localhost:8003/health
```

## API Documentation

Once running, access the OpenAPI documentation at:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Reference

### Authentication

All API requests require Bearer token authentication:

```bash
curl -H "Authorization: Bearer dev-api-key-change-in-production" \
     http://localhost:8000/intents
```

### Core Endpoints

#### Intents

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/intents` | Create purchase intent from natural language query |
| GET | `/intents/{id}` | Get intent details |
| GET | `/intents/{id}/offers` | Get offers from merchants for this intent |

#### Offers

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/offers/{id}` | Get detailed offer information |

#### Checkouts

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/checkouts` | Create checkout from an offer |
| GET | `/checkouts/{id}` | Get checkout details |
| POST | `/checkouts/{id}/quote` | Get quote from merchant |
| POST | `/checkouts/{id}/request-approval` | Request human approval |
| POST | `/checkouts/{id}/approve` | Approve the purchase |
| POST | `/checkouts/{id}/confirm` | Execute the purchase |

#### Orders

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/orders` | List orders (paginated) |
| GET | `/orders/{id}` | Get order details |
| POST | `/orders/{id}/cancel` | Cancel an order |
| POST | `/orders/{id}/refund` | Refund an order |
| POST | `/orders/{id}/simulate-advance` | Advance order state (testing) |

#### Webhooks

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/webhooks/merchant` | Receive merchant webhook events |
| GET | `/webhooks/events/{id}` | Get webhook event status |

### Checkout State Machine

```
created → quoted → awaiting_approval → approved → confirmed
                                              ↓
                                           failed
```

### Order State Machine

```
pending → confirmed → shipped → delivered
    ↓          ↓          ↓
cancelled ← cancelled ← cancelled → refunded
```

## Demo Walkthrough

### Complete Purchase Flow

This walkthrough demonstrates a complete purchase from intent to order.

```bash
# Set up variables
API_URL="http://localhost:8000"
API_KEY="dev-api-key-change-in-production"

# Step 1: Create an intent
INTENT=$(curl -s -X POST "$API_URL/intents" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "wireless headphones under $100", "session_id": "demo-session"}')

INTENT_ID=$(echo $INTENT | jq -r '.id')
echo "Created intent: $INTENT_ID"

# Step 2: Get offers from merchants
OFFERS=$(curl -s "$API_URL/intents/$INTENT_ID/offers" \
  -H "Authorization: Bearer $API_KEY")

OFFER_ID=$(echo $OFFERS | jq -r '.items[0].id')
PRODUCT_ID=$(echo $OFFERS | jq -r '.items[0].items[0].product_id')
echo "Got offer: $OFFER_ID with product: $PRODUCT_ID"

# Step 3: Create checkout
CHECKOUT=$(curl -s -X POST "$API_URL/checkouts" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"offer_id\": \"$OFFER_ID\",
    \"items\": [{\"product_id\": \"$PRODUCT_ID\", \"quantity\": 1}]
  }")

CHECKOUT_ID=$(echo $CHECKOUT | jq -r '.id')
echo "Created checkout: $CHECKOUT_ID (status: $(echo $CHECKOUT | jq -r '.status'))"

# Step 4: Get quote from merchant
QUOTE=$(curl -s -X POST "$API_URL/checkouts/$CHECKOUT_ID/quote" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"items\": [{\"product_id\": \"$PRODUCT_ID\", \"quantity\": 1}]}")

echo "Quote total: $(echo $QUOTE | jq -r '.total.amount') cents"
echo "Status: $(echo $QUOTE | jq -r '.status')"

# Step 5: Request approval
APPROVAL_REQ=$(curl -s -X POST "$API_URL/checkouts/$CHECKOUT_ID/request-approval" \
  -H "Authorization: Bearer $API_KEY")

echo "Status: $(echo $APPROVAL_REQ | jq -r '.status')"
echo "Frozen receipt hash: $(echo $APPROVAL_REQ | jq -r '.frozen_receipt.hash')"

# Step 6: Approve the purchase
APPROVED=$(curl -s -X POST "$API_URL/checkouts/$CHECKOUT_ID/approve" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"approved_by": "demo-user"}')

echo "Status: $(echo $APPROVED | jq -r '.status')"

# Step 7: Confirm (execute) the purchase
CONFIRMED=$(curl -s -X POST "$API_URL/checkouts/$CHECKOUT_ID/confirm" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"payment_method": "test_card"}')

ORDER_ID=$(echo $CONFIRMED | jq -r '.order_id')
echo "Purchase confirmed! Order ID: $ORDER_ID"

# Step 8: Check order status
ORDER=$(curl -s "$API_URL/orders/$ORDER_ID" \
  -H "Authorization: Bearer $API_KEY")

echo "Order status: $(echo $ORDER | jq -r '.status')"
echo "Total: $(echo $ORDER | jq -r '.total.amount') $(echo $ORDER | jq -r '.total.currency')"
```

### Testing Chaos Scenarios (Merchant B)

```bash
MERCHANT_B="http://localhost:8002"

# Enable price change chaos
curl -X POST "$MERCHANT_B/chaos/configure" \
  -H "Content-Type: application/json" \
  -d '{
    "scenarios": {"price_change": true},
    "price_change_percent": 20
  }'

# Enable all chaos scenarios
curl -X POST "$MERCHANT_B/chaos/enable-all"

# Disable all chaos
curl -X POST "$MERCHANT_B/chaos/disable-all"

# Check chaos status
curl "$MERCHANT_B/chaos/config"
```

### Order Lifecycle Simulation

```bash
# Simulate order advancement (for testing)
curl -X POST "$API_URL/orders/$ORDER_ID/simulate-advance" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"steps": 1}'

# Advance through: pending → confirmed → shipped → delivered
```

## Network Configuration

### Understanding Localhost vs Service Names

When working with CartPilot, it's important to understand the difference between host access and container-to-container communication.

#### From Host (Postman, browser, curl)

Use `localhost` with published ports:

```
http://localhost:8000  - CartPilot API
http://localhost:8001  - Merchant A
http://localhost:8002  - Merchant B
http://localhost:8003  - MCP Server
```

#### Container-to-Container

Services communicate using Docker service names:

```
http://cartpilot-api:8000  - CartPilot API
http://merchant-a:8001     - Merchant A
http://merchant-b:8002     - Merchant B
http://cartpilot-mcp:8003  - MCP Server
```

#### Example: Webhook URLs

Merchants send webhooks to CartPilot. Since merchants are containers, they use the service name:

```yaml
# docker-compose.yml
WEBHOOK_URL: http://cartpilot-api:8000/webhooks/merchant
```

If you're testing webhooks from your host machine:

```bash
# From host, use localhost
curl -X POST http://localhost:8000/webhooks/merchant \
  -H "Content-Type: application/json" \
  -H "X-Merchant-Id: merchant-a" \
  -d '{"event_id": "test", "event_type": "checkout.confirmed", ...}'
```

## Project Structure

```
cart-pilot/
├── cartpilot-api/          # Core orchestration backend
│   ├── app/
│   │   ├── api/            # FastAPI routes, schemas
│   │   ├── application/    # Use cases, workflows
│   │   ├── domain/         # Entities, state machines
│   │   └── infrastructure/ # DB, HTTP clients
│   ├── alembic/            # Database migrations
│   ├── scripts/            # Utility scripts
│   └── tests/
│       ├── api/            # API endpoint tests
│       ├── domain/         # Domain logic tests
│       ├── catalog/        # Catalog tests
│       └── e2e/            # End-to-end integration tests
├── merchant-a/             # Happy path merchant simulator
├── merchant-b/             # Chaos mode merchant simulator
├── cartpilot-mcp/          # MCP server for AI agents
├── docs/                   # Additional documentation
└── docker-compose.yml
```

## Environment Variables

Copy `.env.example` to `.env` and adjust as needed:

```bash
cp .env.example .env
```

Key variables:

| Variable              | Description                    | Default                    |
|-----------------------|--------------------------------|----------------------------|
| `DATABASE_URL`        | PostgreSQL connection string   | (see docker-compose.yml)   |
| `CARTPILOT_API_KEY`   | API authentication key         | dev-api-key-...            |
| `WEBHOOK_SECRET`      | HMAC secret for webhooks       | dev-webhook-secret-...     |
| `CATALOG_SEED_MODE`   | Catalog size (small/full)      | small                      |
| `MERCHANT_A_ENABLED`  | Enable Merchant A              | true                       |
| `MERCHANT_B_ENABLED`  | Enable Merchant B              | true                       |

## Development

### Local Development (without Docker)

```bash
cd cartpilot-api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Start with hot reload
uvicorn app.main:app --reload --port 8000
```

### Running Tests

```bash
# All tests
cd cartpilot-api
pytest

# E2E tests only
pytest tests/e2e/

# With coverage
pytest --cov=app --cov-report=html

# Specific test file
pytest tests/e2e/test_scenarios.py -v
```

### E2E Test Scenarios

The E2E test suite covers 8 core scenarios:

1. **Happy Path Purchase** - Complete flow from intent to order with Merchant A
2. **Idempotency Retry** - Same idempotency key returns same result
3. **Price Change Re-approval** - Price change triggers re-approval requirement
4. **Out-of-Stock Failure** - Handling when items become unavailable
5. **Duplicate Webhooks** - Same webhook processed idempotently
6. **Out-of-Order Webhooks** - Late-arriving webhooks handled gracefully
7. **Partial Failure Recovery** - Recovery from failed steps
8. **Refund Flow** - Cancel and refund an order

### Database Migrations

```bash
cd cartpilot-api

# Create a new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

## MCP Tools for AI Agents

The MCP server provides 8 tools for AI agent integration:

| Tool | Description |
|------|-------------|
| `create_intent` | Create purchase intent from natural language |
| `list_offers` | Get offers from merchants for an intent |
| `get_offer_details` | Get detailed offer information |
| `request_approval` | Initiate approval flow for a purchase |
| `approve_purchase` | Approve and optionally confirm purchase |
| `get_order_status` | Check order status and tracking |
| `simulate_time` | Advance order state for testing |
| `trigger_chaos_case` | Enable chaos scenarios on Merchant B |

Example MCP tool usage:

```python
# Create intent
result = await mcp.create_intent(
    query="wireless headphones under $100",
    session_id="agent-session-123"
)

# List offers
offers = await mcp.list_offers(intent_id=result["intent_id"])

# Request approval
approval = await mcp.request_approval(
    offer_id=offers["offers"][0]["offer_id"],
    items=[{"product_id": "prod-001", "quantity": 1}]
)

# Approve and confirm
order = await mcp.approve_purchase(
    checkout_id=approval["checkout_id"],
    approved_by="ai-agent"
)

# Check status
status = await mcp.get_order_status(order_id=order["order_id"])
```

## Postman Collection

Import the Postman collection from `docs/CartPilot.postman_collection.json` for ready-to-use API examples.

The collection includes:

- Health checks for all services
- Complete purchase flow
- Chaos mode configuration
- Order lifecycle management
- Webhook testing

## Troubleshooting

### Services not starting

```bash
# Check container status
docker compose ps

# View logs
docker compose logs -f

# Rebuild containers
docker compose up --build
```

### Database connection issues

```bash
# Reset database
docker compose down -v
docker compose up -d db
docker compose up
```

### Port conflicts

```bash
# Check what's using a port
lsof -i :8000

# Use different ports in .env
CARTPILOT_API_PORT=9000
```

## Deployment

### GCP Deployment (Production)

CartPilot can be deployed to Google Cloud Platform using Cloud Run and Cloud SQL.

#### Prerequisites

- Google Cloud SDK (`gcloud` CLI)
- Docker
- GCP project with billing enabled

#### Quick Deployment

```bash
# 1. Set up GCP project and Artifact Registry
./deploy/gcp/setup.sh

# 2. Deploy Cloud SQL database
./deploy/gcp/deploy-cloudsql.sh

# 3. Set secrets
export CARTPILOT_API_KEY="your-secure-api-key"
export WEBHOOK_SECRET="your-webhook-secret"

# 4. Build and deploy all services
./deploy/gcp/deploy.sh
```

#### Deployment Steps

1. **Initial Setup** (`deploy/gcp/setup.sh`)
   - Creates/uses GCP project
   - Enables required APIs
   - Sets up Artifact Registry
   - Creates service account

2. **Cloud SQL** (`deploy/gcp/deploy-cloudsql.sh`)
   - Creates PostgreSQL instance
   - Configures private IP
   - Creates database and user

3. **Cloud Run** (`deploy/gcp/deploy.sh`)
   - Builds Docker images
   - Pushes to Artifact Registry
   - Deploys services in correct order

For detailed instructions, see [GCP Deployment Guide](deploy/gcp/README.md).

#### Service URLs

After deployment, services will be available at:

- `https://cartpilot-api-xxxx.run.app`
- `https://cartpilot-mcp-xxxx.run.app`
- `https://merchant-a-xxxx.run.app`
- `https://merchant-b-xxxx.run.app`

#### Cost Estimation

For demo/testing:
- Cloud Run: ~$0-5/month
- Cloud SQL (db-f1-micro): ~$7-10/month
- Artifact Registry: ~$0.10/GB/month
- **Total: ~$10-20/month**

For production:
- Cloud Run: ~$20-50/month
- Cloud SQL (db-f1-small): ~$15-20/month
- **Total: ~$40-75/month**

## LLM Integrations

CartPilot provides multiple integration options for AI assistants:

### 1. MCP Server (Claude, Cline, VS Code)

The MCP server provides tools via Server-Sent Events (SSE) for MCP-compatible agents.

**Setup:**

1. Deploy CartPilot MCP server (included in deployment)
2. Configure MCP client with SSE endpoint:
   ```
   https://cartpilot-mcp-xxxx.run.app/sse
   ```

**Available Tools:**
- `create_intent` - Create purchase intent
- `list_offers` - Get offers from merchants
- `get_offer_details` - Get detailed offer info
- `request_approval` - Request approval
- `approve_purchase` - Approve purchase
- `get_order_status` - Check order status
- `simulate_time` - Advance order state
- `trigger_chaos_case` - Enable chaos scenarios

**Example Configuration** (`.vscode/mcp.json`):
```json
{
  "mcpServers": {
    "cartpilot": {
      "url": "https://cartpilot-mcp-xxxx.run.app/sse"
    }
  }
}
```

### 2. ChatGPT Actions

Integrate CartPilot with ChatGPT using OpenAPI specification.

**Setup:**

1. Deploy CartPilot API to Cloud Run
2. Update `docs/openapi.yaml` with your API URL
3. Create Custom GPT in ChatGPT:
   - Go to ChatGPT Custom GPTs
   - Add Action → Import OpenAPI schema
   - Configure authentication (Bearer token)
   - Add API key

**Features:**
- Natural language purchase intents
- Product search across merchants
- Checkout approval workflow
- Order tracking

For detailed instructions, see [ChatGPT Actions Guide](docs/CHATGPT_ACTIONS.md).

### 3. Gemini Function Calling

Use CartPilot with Google Gemini via Function Calling.

**Setup:**

```bash
# Install dependencies
pip install -r integrations/requirements.txt

# Set environment variables
export GEMINI_API_KEY="your-gemini-api-key"
export CARTPILOT_API_URL="https://cartpilot-api-xxxx.run.app"
export CARTPILOT_API_KEY="your-cartpilot-api-key"
```

**Usage:**

```python
from integrations.gemini_client import CartPilotGeminiClient
import google.generativeai as genai

# Initialize
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
client = CartPilotGeminiClient(
    cartpilot_api_url=os.getenv("CARTPILOT_API_URL"),
    api_key=os.getenv("CARTPILOT_API_KEY")
)

# Get functions for Gemini
functions = client.get_function_declarations()

# Create model with functions
model = genai.GenerativeModel(
    model_name="gemini-1.5-pro",
    tools=[{"function_declarations": functions}]
)

# Use in chat
chat = model.start_chat()
response = chat.send_message("I need wireless headphones under $100")

# Handle function calls
for candidate in response.candidates:
    for part in candidate.content.parts:
        if hasattr(part, "function_call") and part.function_call:
            result = await client.handle_function_call(part.function_call)
            # Send result back to Gemini
            chat.send_message(genai.protos.FunctionResponse(
                name=result["name"],
                response=result["response"]
            ))
```

**Interactive Example:**

```bash
python integrations/example_chat.py
```

For detailed documentation, see [Gemini Integration Guide](integrations/README.md).

### Integration Comparison

| Feature | MCP Server | ChatGPT Actions | Gemini Function Calling |
|---------|------------|-----------------|------------------------|
| **Protocol** | MCP SSE | OpenAPI REST | Function Calling |
| **Best For** | Claude, Cline | ChatGPT | Gemini |
| **Setup** | Configure URL | Import OpenAPI | Python client |
| **Tools/Functions** | 8 tools | 15+ endpoints | 11 functions |
| **Approval Flow** | ✅ | ✅ | ✅ |
| **Order Tracking** | ✅ | ✅ | ✅ |

## Additional Documentation

- [GCP Deployment Guide](deploy/gcp/README.md) - Detailed GCP deployment instructions
- [ChatGPT Actions Guide](docs/CHATGPT_ACTIONS.md) - ChatGPT integration setup
- [Gemini Integration Guide](integrations/README.md) - Gemini Function Calling guide
- [OpenAPI Specification](docs/openapi.yaml) - Complete API specification
- [Docker Optimization](deploy/DOCKER_OPTIMIZATION.md) - Production Dockerfile details
- [Local Compatibility](deploy/LOCAL_COMPATIBILITY.md) - Local development notes

## License

MIT
