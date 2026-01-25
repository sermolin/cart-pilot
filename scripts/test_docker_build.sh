#!/bin/bash
# Test script for optimized Dockerfile builds
# This script builds and tests all services locally

set -euo pipefail

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=========================================="
echo "  CartPilot Docker Build Test"
echo "==========================================${NC}"
echo ""

# Check Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not running${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Docker is running${NC}"
echo ""

# Step 1: Build images
echo -e "${BLUE}Step 1: Building Docker images...${NC}"
echo ""

if docker compose build; then
    echo -e "${GREEN}✓ All images built successfully${NC}"
else
    echo -e "${RED}✗ Build failed${NC}"
    exit 1
fi

echo ""

# Step 2: Check image sizes
echo -e "${BLUE}Step 2: Checking image sizes...${NC}"
docker images | grep -E "(cartpilot|merchant)" | awk '{printf "  %-30s %10s\n", $1":"$2, $7}'
echo ""

# Step 3: Start services
echo -e "${BLUE}Step 3: Starting services...${NC}"
docker compose up -d

echo ""
echo -e "${YELLOW}Waiting for services to be healthy...${NC}"
sleep 10

# Step 4: Check health endpoints
echo ""
echo -e "${BLUE}Step 4: Testing health endpoints...${NC}"
echo ""

check_health() {
    local service=$1
    local url=$2
    local max_attempts=30
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if curl -sf "$url" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ $service is healthy${NC}"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 2
    done
    
    echo -e "${RED}✗ $service failed to become healthy${NC}"
    return 1
}

check_health "CartPilot API" "http://localhost:8000/health"
check_health "Merchant A" "http://localhost:8001/health"
check_health "Merchant B" "http://localhost:8002/health"
check_health "MCP Server" "http://localhost:8003/health"

echo ""

# Step 5: Check user permissions
echo -e "${BLUE}Step 5: Checking user permissions...${NC}"
echo ""

check_user() {
    local service=$1
    local container=$2
    local user=$(docker compose exec -T "$container" whoami 2>/dev/null || echo "unknown")
    if [ "$user" = "appuser" ]; then
        echo -e "${GREEN}✓ $service running as non-root user (appuser)${NC}"
    else
        echo -e "${YELLOW}⚠ $service running as: $user${NC}"
    fi
}

check_user "CartPilot API" "cartpilot-api"
check_user "Merchant A" "merchant-a"
check_user "Merchant B" "merchant-b"
check_user "MCP Server" "cartpilot-mcp"

echo ""

# Step 6: Test API functionality
echo -e "${BLUE}Step 6: Testing API functionality...${NC}"
echo ""

API_URL="http://localhost:8000"
API_KEY="dev-api-key-change-in-production"

# Test creating an intent
INTENT_RESPONSE=$(curl -s -X POST "$API_URL/intents" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"query": "test product", "session_id": "test-session"}')

if echo "$INTENT_RESPONSE" | grep -q '"id"'; then
    INTENT_ID=$(echo "$INTENT_RESPONSE" | grep -o '"id":"[^"]*"' | cut -d'"' -f4)
    echo -e "${GREEN}✓ Created intent: $INTENT_ID${NC}"
else
    echo -e "${RED}✗ Failed to create intent${NC}"
    echo "Response: $INTENT_RESPONSE"
fi

echo ""

# Summary
echo -e "${BLUE}=========================================="
echo "  Test Summary"
echo "==========================================${NC}"
echo ""
echo -e "${GREEN}All services are running!${NC}"
echo ""
echo "Services available at:"
echo "  - CartPilot API:  http://localhost:8000"
echo "  - Merchant A:     http://localhost:8001"
echo "  - Merchant B:     http://localhost:8002"
echo "  - MCP Server:     http://localhost:8003"
echo ""
echo "To view logs:"
echo "  docker compose logs -f"
echo ""
echo "To stop services:"
echo "  docker compose down"
echo ""
