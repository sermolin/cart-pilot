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
                                 │
┌─────────────────┐     ┌────────▼────────┐     ┌─────────────────┐
│    Postman      │────▶│  CartPilot API  │────▶│   PostgreSQL    │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    ▼                         ▼
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
```

## API Documentation

Once running, access the OpenAPI documentation at:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

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
│   └── tests/
├── merchant-a/             # Happy path merchant simulator
├── merchant-b/             # Chaos mode merchant simulator
├── cartpilot-mcp/          # MCP server for AI agents
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
| `DATABASE_URL`        | PostgreSQL connection string   | (see .env.example)         |
| `CARTPILOT_API_KEY`   | API authentication key         | dev-api-key-...            |
| `WEBHOOK_SECRET`      | HMAC secret for webhooks       | dev-webhook-secret-...     |
| `CATALOG_SEED_MODE`   | Catalog size (small/full)      | small                      |

## Network Configuration

### From Host (Postman, browser)

Use `localhost` with published ports:
- `http://localhost:8000` for CartPilot API
- `http://localhost:8001` for Merchant A

### Container-to-Container

Use service names:
- `http://cartpilot-api:8000`
- `http://merchant-a:8001`

## Development

### Local Development (without Docker)

```bash
cd cartpilot-api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Running Tests

```bash
cd cartpilot-api
pytest
```

### Database Migrations

```bash
cd cartpilot-api

# Create a new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head
```

## License

MIT
