#!/bin/bash
# =============================================================================
# CartPilot Demo: Happy Path Purchase Flow
# =============================================================================
#
# This script demonstrates a complete purchase flow through CartPilot:
# 1. Create intent from natural language query
# 2. Get offers from merchants
# 3. Create checkout
# 4. Get quote
# 5. Request approval
# 6. Approve purchase
# 7. Confirm (execute) purchase
# 8. Check order status
#
# Prerequisites:
# - docker compose up (all services running)
# - jq installed (for JSON parsing)
#
# Usage:
#   ./scripts/demo_happy_path.sh
#
# =============================================================================

set -e

# Configuration
API_URL="${CARTPILOT_API_URL:-http://localhost:8000}"
API_KEY="${CARTPILOT_API_KEY:-dev-api-key-change-in-production}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_step() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}Step $1:${NC} $2"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_info() {
    echo -e "${YELLOW}→${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

check_requirements() {
    if ! command -v jq &> /dev/null; then
        print_error "jq is required but not installed. Please install jq."
        exit 1
    fi
    
    if ! command -v curl &> /dev/null; then
        print_error "curl is required but not installed."
        exit 1
    fi
}

check_api_health() {
    print_info "Checking API health..."
    if curl -s -f "$API_URL/health" > /dev/null; then
        print_success "CartPilot API is healthy"
    else
        print_error "CartPilot API is not responding. Make sure 'docker compose up' is running."
        exit 1
    fi
}

# Main demo flow
main() {
    echo -e "${GREEN}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║           CartPilot Demo: Happy Path Purchase Flow           ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    check_requirements
    check_api_health
    
    # Step 1: Create Intent
    print_step "1" "Create Purchase Intent"
    print_info "Creating intent for: 'wireless headphones under \$100'"
    
    INTENT_RESPONSE=$(curl -s -X POST "$API_URL/intents" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d '{
            "query": "wireless headphones under $100",
            "session_id": "demo-session-'$(date +%s)'",
            "metadata": {"demo": true}
        }')
    
    INTENT_ID=$(echo "$INTENT_RESPONSE" | jq -r '.id')
    if [ "$INTENT_ID" == "null" ] || [ -z "$INTENT_ID" ]; then
        print_error "Failed to create intent"
        echo "$INTENT_RESPONSE" | jq .
        exit 1
    fi
    
    print_success "Intent created: $INTENT_ID"
    echo "$INTENT_RESPONSE" | jq '{id, query, session_id, created_at}'
    
    # Step 2: Get Offers
    print_step "2" "Get Offers from Merchants"
    print_info "Fetching offers for intent..."
    
    OFFERS_RESPONSE=$(curl -s "$API_URL/intents/$INTENT_ID/offers" \
        -H "Authorization: Bearer $API_KEY")
    
    OFFER_COUNT=$(echo "$OFFERS_RESPONSE" | jq '.total')
    print_success "Found $OFFER_COUNT offer(s)"
    
    if [ "$OFFER_COUNT" -eq 0 ]; then
        print_error "No offers found. Make sure merchants are running."
        exit 1
    fi
    
    OFFER_ID=$(echo "$OFFERS_RESPONSE" | jq -r '.items[0].id')
    PRODUCT_ID=$(echo "$OFFERS_RESPONSE" | jq -r '.items[0].items[0].product_id')
    PRODUCT_TITLE=$(echo "$OFFERS_RESPONSE" | jq -r '.items[0].items[0].title')
    MERCHANT_ID=$(echo "$OFFERS_RESPONSE" | jq -r '.items[0].merchant_id')
    
    print_info "Selected offer: $OFFER_ID"
    print_info "Merchant: $MERCHANT_ID"
    print_info "Product: $PRODUCT_TITLE ($PRODUCT_ID)"
    
    # Step 3: Create Checkout
    print_step "3" "Create Checkout"
    print_info "Creating checkout from selected offer..."
    
    CHECKOUT_RESPONSE=$(curl -s -X POST "$API_URL/checkouts" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d "{
            \"offer_id\": \"$OFFER_ID\",
            \"items\": [{\"product_id\": \"$PRODUCT_ID\", \"quantity\": 1}],
            \"idempotency_key\": \"demo-checkout-$(date +%s)\"
        }")
    
    CHECKOUT_ID=$(echo "$CHECKOUT_RESPONSE" | jq -r '.id')
    CHECKOUT_STATUS=$(echo "$CHECKOUT_RESPONSE" | jq -r '.status')
    
    if [ "$CHECKOUT_ID" == "null" ] || [ -z "$CHECKOUT_ID" ]; then
        print_error "Failed to create checkout"
        echo "$CHECKOUT_RESPONSE" | jq .
        exit 1
    fi
    
    print_success "Checkout created: $CHECKOUT_ID"
    print_info "Status: $CHECKOUT_STATUS"
    
    # Step 4: Get Quote
    print_step "4" "Get Quote from Merchant"
    print_info "Requesting quote from $MERCHANT_ID..."
    
    QUOTE_RESPONSE=$(curl -s -X POST "$API_URL/checkouts/$CHECKOUT_ID/quote" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d "{
            \"items\": [{\"product_id\": \"$PRODUCT_ID\", \"quantity\": 1}],
            \"customer_email\": \"demo@example.com\"
        }")
    
    QUOTE_STATUS=$(echo "$QUOTE_RESPONSE" | jq -r '.status')
    QUOTE_TOTAL=$(echo "$QUOTE_RESPONSE" | jq '.total.amount')
    QUOTE_CURRENCY=$(echo "$QUOTE_RESPONSE" | jq -r '.total.currency')
    
    print_success "Quote received"
    print_info "Status: $QUOTE_STATUS"
    print_info "Total: $(echo "scale=2; $QUOTE_TOTAL / 100" | bc) $QUOTE_CURRENCY"
    echo "$QUOTE_RESPONSE" | jq '{status, subtotal, tax, shipping, total}'
    
    # Step 5: Request Approval
    print_step "5" "Request Human Approval"
    print_info "Freezing receipt and requesting approval..."
    
    APPROVAL_REQ_RESPONSE=$(curl -s -X POST "$API_URL/checkouts/$CHECKOUT_ID/request-approval" \
        -H "Authorization: Bearer $API_KEY")
    
    APPROVAL_STATUS=$(echo "$APPROVAL_REQ_RESPONSE" | jq -r '.status')
    FROZEN_HASH=$(echo "$APPROVAL_REQ_RESPONSE" | jq -r '.frozen_receipt.hash')
    FROZEN_TOTAL=$(echo "$APPROVAL_REQ_RESPONSE" | jq '.frozen_receipt.total_cents')
    
    print_success "Approval requested"
    print_info "Status: $APPROVAL_STATUS"
    print_info "Frozen receipt hash: ${FROZEN_HASH:0:16}..."
    print_info "Frozen total: $(echo "scale=2; $FROZEN_TOTAL / 100" | bc) $QUOTE_CURRENCY"
    
    # Step 6: Approve
    print_step "6" "Approve Purchase"
    print_info "Approving checkout as 'demo-user'..."
    
    APPROVE_RESPONSE=$(curl -s -X POST "$API_URL/checkouts/$CHECKOUT_ID/approve" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d '{"approved_by": "demo-user"}')
    
    APPROVED_STATUS=$(echo "$APPROVE_RESPONSE" | jq -r '.status')
    APPROVED_BY=$(echo "$APPROVE_RESPONSE" | jq -r '.approved_by')
    APPROVED_AT=$(echo "$APPROVE_RESPONSE" | jq -r '.approved_at')
    
    print_success "Checkout approved"
    print_info "Status: $APPROVED_STATUS"
    print_info "Approved by: $APPROVED_BY"
    print_info "Approved at: $APPROVED_AT"
    
    # Step 7: Confirm (Execute Purchase)
    print_step "7" "Confirm Purchase (Execute)"
    print_info "Executing purchase with merchant..."
    
    CONFIRM_RESPONSE=$(curl -s -X POST "$API_URL/checkouts/$CHECKOUT_ID/confirm" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d "{
            \"payment_method\": \"test_card\",
            \"idempotency_key\": \"demo-confirm-$(date +%s)\"
        }")
    
    CONFIRM_STATUS=$(echo "$CONFIRM_RESPONSE" | jq -r '.status')
    ORDER_ID=$(echo "$CONFIRM_RESPONSE" | jq -r '.order_id')
    MERCHANT_ORDER_ID=$(echo "$CONFIRM_RESPONSE" | jq -r '.merchant_order_id')
    CONFIRM_TOTAL=$(echo "$CONFIRM_RESPONSE" | jq '.total.amount')
    
    if [ "$CONFIRM_STATUS" != "confirmed" ]; then
        print_error "Confirmation failed"
        echo "$CONFIRM_RESPONSE" | jq .
        exit 1
    fi
    
    print_success "Purchase confirmed!"
    print_info "Status: $CONFIRM_STATUS"
    print_info "Order ID: $ORDER_ID"
    print_info "Merchant Order ID: $MERCHANT_ORDER_ID"
    print_info "Total charged: $(echo "scale=2; $CONFIRM_TOTAL / 100" | bc) $QUOTE_CURRENCY"
    
    # Step 8: Check Order Status
    print_step "8" "Check Order Status"
    print_info "Fetching order details..."
    
    ORDER_RESPONSE=$(curl -s "$API_URL/orders/$ORDER_ID" \
        -H "Authorization: Bearer $API_KEY")
    
    ORDER_STATUS=$(echo "$ORDER_RESPONSE" | jq -r '.status')
    ITEM_COUNT=$(echo "$ORDER_RESPONSE" | jq '.items | length')
    
    print_success "Order retrieved"
    echo "$ORDER_RESPONSE" | jq '{id, status, merchant_id, merchant_order_id, total, created_at}'
    
    # Summary
    echo -e "\n${GREEN}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║                    Demo Complete! 🎉                         ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    echo -e "${YELLOW}Summary:${NC}"
    echo "  Intent ID:         $INTENT_ID"
    echo "  Offer ID:          $OFFER_ID"
    echo "  Checkout ID:       $CHECKOUT_ID"
    echo "  Order ID:          $ORDER_ID"
    echo "  Merchant Order ID: $MERCHANT_ORDER_ID"
    echo "  Order Status:      $ORDER_STATUS"
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo "  # Advance order through lifecycle"
    echo "  curl -X POST '$API_URL/orders/$ORDER_ID/simulate-advance' \\"
    echo "    -H 'Authorization: Bearer $API_KEY' \\"
    echo "    -H 'Content-Type: application/json' \\"
    echo "    -d '{\"steps\": 1}'"
    echo ""
    echo "  # Check order status"
    echo "  curl '$API_URL/orders/$ORDER_ID' -H 'Authorization: Bearer $API_KEY'"
}

main "$@"
