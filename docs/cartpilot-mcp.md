# CartPilot MCP Module

## Overview

CartPilot MCP is a Model Context Protocol (MCP) server that exposes CartPilot capabilities as tools for AI agents. It acts as a thin adapter over the CartPilot REST API, providing a standardized interface for AI assistants like Claude Desktop, Cursor, and other MCP-compatible clients.

## Purpose

- **AI Agent Integration**: Provides MCP tools for AI agents to interact with CartPilot
- **Protocol Adapter**: Translates MCP tool calls to CartPilot REST API requests
- **Transport Flexibility**: Supports both stdio (local) and SSE (HTTP/Docker) transport modes
- **Chaos Testing**: Includes tools for enabling chaos scenarios on Merchant B

## Architecture

```
app/
├── main.py          # MCP server setup and transport configuration
├── tools.py         # MCP tool implementations (8 tools)
└── api_client.py    # HTTP client for CartPilot API
```

## Transport Modes

### stdio Mode (Default)
- For local use with AI agents (Claude Desktop, Cursor)
- Communicates via standard input/output
- Best for development and local testing

### SSE Mode (Server-Sent Events)
- For Docker/HTTP deployments
- Uses HTTP with Server-Sent Events
- Exposes endpoints:
  - `GET /sse` - SSE connection endpoint
  - `POST /messages` - Message handling
  - `GET /health` - Health check

## MCP Tools

The server provides 8 tools for AI agent interaction:

### 1. create_intent
Create a purchase intent from natural language description.

**Input:**
- `query` (string): Natural language purchase description
- `session_id` (string, optional): Session ID for tracking

**Output:** Intent ID and details

### 2. list_offers
Get offers from merchants for a purchase intent.

**Input:**
- `intent_id` (string): Intent ID from create_intent
- `page` (int, default: 1): Page number
- `page_size` (int, default: 10): Items per page

**Output:** Paginated list of offers

### 3. get_offer_details
Get detailed information about a specific offer.

**Input:**
- `offer_id` (string): Offer ID from list_offers

**Output:** Complete offer details with product information

### 4. request_approval
Initiate the approval flow for a purchase.

**Input:**
- `offer_id` (string): Offer ID to create checkout from
- `items` (array): List of items to purchase
- `customer_email` (string, optional): Customer email

**Output:** Checkout ID and frozen receipt

### 5. approve_purchase
Approve a pending purchase and optionally confirm it.

**Input:**
- `checkout_id` (string): Checkout ID from request_approval
- `approved_by` (string, default: "user"): Who is approving
- `confirm` (bool, default: true): Whether to confirm purchase
- `payment_method` (string, default: "test_card"): Payment method

**Output:** Approved checkout and order ID (if confirmed)

### 6. get_order_status
Check the status of an order.

**Input:**
- `order_id` (string): Order ID

**Output:** Order status, shipping info, tracking details

### 7. simulate_time
Advance order state for testing purposes.

**Input:**
- `order_id` (string): Order ID to advance
- `steps` (int, default: 1): Number of state transitions (1-5)

**Output:** Updated order status

### 8. trigger_chaos_case
Enable or disable chaos scenarios for resilience testing.

**Input:**
- `scenario` (string): Scenario name (price_change, out_of_stock, duplicate_webhook, delayed_webhook, out_of_order_webhook, or all)
- `enable` (bool, default: true): Enable or disable scenario

**Output:** Updated chaos configuration

## Key Components

### MCPTools Class (`app/tools.py`)

Implements all 8 MCP tools as methods that:
- Call CartPilot REST API via `CartPilotAPIClient`
- Format responses for AI agent consumption
- Handle errors gracefully
- Provide human-readable output

### CartPilotAPIClient (`app/api_client.py`)

HTTP client wrapper for CartPilot API:
- Handles authentication
- Manages request/response formatting
- Error handling and retries
- Type-safe API calls

### MerchantBChaosClient (`app/api_client.py`)

Specialized client for Merchant B chaos endpoints:
- Configure chaos scenarios
- Enable/disable chaos modes
- Query chaos event log

## Configuration

Key environment variables:
- `CARTPILOT_API_URL` - CartPilot API base URL (default: `http://cartpilot-api:8000`)
- `CARTPILOT_API_KEY` - API key for authentication
- `MERCHANT_B_URL` - Merchant B base URL (default: `http://merchant-b:8002`)
- `MCP_TRANSPORT` - Transport mode: `stdio` or `sse` (default: `stdio`)
- `SSE_HOST` - Host for SSE server (default: `0.0.0.0`)
- `SSE_PORT` - Port for SSE server (default: `8003`)
- `LOG_LEVEL` - Logging level (default: `INFO`)

## Usage Examples

### stdio Mode (Local)

```bash
# Run MCP server
python -m app.main

# Configure in Cursor/Claude Desktop
{
  "mcpServers": {
    "cartpilot": {
      "command": "python",
      "args": ["-m", "app.main"],
      "cwd": "/path/to/cartpilot-mcp"
    }
  }
}
```

### SSE Mode (Docker/HTTP)

```bash
# Set transport mode
export MCP_TRANSPORT=sse

# Run server
python -m app.main

# Access via HTTP
curl http://localhost:8003/health
```

## Integration with AI Agents

### Claude Desktop
Configure in `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "cartpilot": {
      "command": "python",
      "args": ["-m", "app.main"],
      "cwd": "/path/to/cartpilot-mcp"
    }
  }
}
```

### Cursor
Configure in `.vscode/mcp.json`:
```json
{
  "mcpServers": {
    "cartpilot": {
      "url": "http://localhost:8003/sse"
    }
  }
}
```

## Error Handling

All tools return structured responses with:
- Success/failure status
- Formatted error messages
- Human-readable output for AI agents

## Testing

Test suite includes:
- `test_main.py` - Server initialization and transport tests
- `test_tools.py` - Tool implementation tests
- `test_api_client.py` - API client tests

## Dependencies

- `mcp` - Model Context Protocol SDK
- `httpx` - HTTP client
- `pydantic` - Data validation
- `structlog` - Structured logging
