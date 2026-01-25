#!/bin/bash
# =============================================================================
# CartPilot Demo: Chaos Mode Testing
# =============================================================================
#
# This script demonstrates testing with Merchant B's chaos mode:
# - Price changes between quote and confirm
# - Out-of-stock scenarios
# - Duplicate webhook handling
#
# Prerequisites:
# - docker compose up (all services running)
# - jq installed (for JSON parsing)
#
# Usage:
#   ./scripts/demo_chaos_mode.sh [scenario]
#
# Scenarios:
#   price_change     - Test price change re-approval flow
#   out_of_stock     - Test out-of-stock handling
#   duplicate_webhook - Test duplicate webhook deduplication
#   all              - Enable all chaos scenarios
#   reset            - Reset chaos controller to defaults
#
# =============================================================================

set -e

# Configuration
API_URL="${CARTPILOT_API_URL:-http://localhost:8000}"
MERCHANT_B_URL="${MERCHANT_B_URL:-http://localhost:8002}"
API_KEY="${CARTPILOT_API_KEY:-dev-api-key-change-in-production}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# Helper functions
print_header() {
    echo -e "\n${MAGENTA}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${MAGENTA}$1${NC}"
    echo -e "${MAGENTA}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_step() {
    echo -e "\n${BLUE}Step $1:${NC} $2"
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

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

check_services() {
    print_info "Checking services..."
    
    if ! curl -s -f "$API_URL/health" > /dev/null; then
        print_error "CartPilot API not responding"
        exit 1
    fi
    
    if ! curl -s -f "$MERCHANT_B_URL/health" > /dev/null; then
        print_error "Merchant B not responding"
        exit 1
    fi
    
    print_success "All services healthy"
}

get_chaos_config() {
    curl -s "$MERCHANT_B_URL/chaos/config"
}

show_chaos_status() {
    print_header "Current Chaos Configuration"
    get_chaos_config | jq .
}

enable_price_change() {
    print_header "Enabling Price Change Chaos"
    
    RESPONSE=$(curl -s -X POST "$MERCHANT_B_URL/chaos/configure" \
        -H "Content-Type: application/json" \
        -d '{
            "scenarios": {"price_change": true},
            "price_change_percent": 20
        }')
    
    print_success "Price change chaos enabled (20% increase)"
    echo "$RESPONSE" | jq '{enabled, scenarios, price_change_percent}'
    
    echo ""
    print_warning "Now when you create a checkout with Merchant B,"
    print_warning "the price may change between quote and confirm."
    print_warning ""
    print_warning "Expected behavior:"
    echo "  1. Create checkout and get quote"
    echo "  2. Request approval (price frozen)"
    echo "  3. Try to confirm → REAPPROVAL_REQUIRED error"
    echo "  4. Re-quote to see new price"
    echo "  5. Request approval again"
    echo "  6. Approve and confirm with new price"
}

enable_out_of_stock() {
    print_header "Enabling Out-of-Stock Chaos"
    
    RESPONSE=$(curl -s -X POST "$MERCHANT_B_URL/chaos/configure" \
        -H "Content-Type: application/json" \
        -d '{
            "scenarios": {"out_of_stock": true},
            "out_of_stock_probability": 0.5
        }')
    
    print_success "Out-of-stock chaos enabled (50% probability)"
    echo "$RESPONSE" | jq '{enabled, scenarios, out_of_stock_probability}'
    
    echo ""
    print_warning "Now ~50% of Merchant B products may become out-of-stock"
    print_warning "during checkout or confirmation."
}

enable_duplicate_webhook() {
    print_header "Enabling Duplicate Webhook Chaos"
    
    RESPONSE=$(curl -s -X POST "$MERCHANT_B_URL/chaos/configure" \
        -H "Content-Type: application/json" \
        -d '{
            "scenarios": {"duplicate_webhook": true},
            "duplicate_webhook_count": 3
        }')
    
    print_success "Duplicate webhook chaos enabled (3 copies)"
    echo "$RESPONSE" | jq '{enabled, scenarios, duplicate_webhook_count}'
    
    echo ""
    print_warning "Merchant B will now send webhooks 3 times."
    print_warning "CartPilot should deduplicate by event_id."
}

enable_all_chaos() {
    print_header "Enabling ALL Chaos Scenarios"
    
    RESPONSE=$(curl -s -X POST "$MERCHANT_B_URL/chaos/enable-all")
    
    print_success "All chaos scenarios enabled!"
    echo "$RESPONSE" | jq .
    
    echo ""
    print_warning "⚡ CHAOS MODE FULLY ACTIVE ⚡"
    print_warning "Merchant B will now exhibit unpredictable behavior."
}

reset_chaos() {
    print_header "Resetting Chaos Controller"
    
    RESPONSE=$(curl -s -X POST "$MERCHANT_B_URL/chaos/reset")
    
    print_success "Chaos controller reset to defaults"
    echo "$RESPONSE" | jq '{enabled, scenarios}'
}

show_chaos_events() {
    print_header "Recent Chaos Events"
    
    RESPONSE=$(curl -s "$MERCHANT_B_URL/chaos/events?limit=10")
    
    EVENT_COUNT=$(echo "$RESPONSE" | jq '.total')
    print_info "Total events: $EVENT_COUNT"
    echo "$RESPONSE" | jq '.events[:5] | .[] | {scenario, checkout_id, triggered_at, details}'
}

demo_price_change_flow() {
    print_header "Demo: Price Change Re-approval Flow"
    
    # First enable price change chaos
    print_step "1" "Enable price change chaos"
    curl -s -X POST "$MERCHANT_B_URL/chaos/configure" \
        -H "Content-Type: application/json" \
        -d '{"scenarios": {"price_change": true}, "price_change_percent": 25}' | jq .
    
    print_step "2" "Create intent"
    INTENT=$(curl -s -X POST "$API_URL/intents" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d '{"query": "test product", "session_id": "chaos-demo"}')
    INTENT_ID=$(echo "$INTENT" | jq -r '.id')
    print_info "Intent: $INTENT_ID"
    
    print_step "3" "Get offers (from Merchant B)"
    OFFERS=$(curl -s "$API_URL/intents/$INTENT_ID/offers" \
        -H "Authorization: Bearer $API_KEY")
    
    # Find Merchant B offer
    MERCHANT_B_OFFER=$(echo "$OFFERS" | jq '.items[] | select(.merchant_id == "merchant-b")')
    
    if [ -z "$MERCHANT_B_OFFER" ] || [ "$MERCHANT_B_OFFER" == "null" ]; then
        print_warning "No Merchant B offer found. Using first available offer."
        OFFER_ID=$(echo "$OFFERS" | jq -r '.items[0].id')
        PRODUCT_ID=$(echo "$OFFERS" | jq -r '.items[0].items[0].product_id')
    else
        OFFER_ID=$(echo "$MERCHANT_B_OFFER" | jq -r '.id')
        PRODUCT_ID=$(echo "$MERCHANT_B_OFFER" | jq -r '.items[0].product_id')
    fi
    
    print_info "Offer: $OFFER_ID"
    print_info "Product: $PRODUCT_ID"
    
    print_step "4" "Create checkout"
    CHECKOUT=$(curl -s -X POST "$API_URL/checkouts" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d "{
            \"offer_id\": \"$OFFER_ID\",
            \"items\": [{\"product_id\": \"$PRODUCT_ID\", \"quantity\": 1}]
        }")
    CHECKOUT_ID=$(echo "$CHECKOUT" | jq -r '.id')
    print_info "Checkout: $CHECKOUT_ID"
    
    print_step "5" "Get initial quote"
    QUOTE1=$(curl -s -X POST "$API_URL/checkouts/$CHECKOUT_ID/quote" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d "{\"items\": [{\"product_id\": \"$PRODUCT_ID\", \"quantity\": 1}]}")
    TOTAL1=$(echo "$QUOTE1" | jq '.total.amount')
    print_info "Initial total: $(echo "scale=2; $TOTAL1 / 100" | bc) USD"
    
    print_step "6" "Request approval (freeze receipt)"
    APPROVAL_REQ=$(curl -s -X POST "$API_URL/checkouts/$CHECKOUT_ID/request-approval" \
        -H "Authorization: Bearer $API_KEY")
    FROZEN_TOTAL=$(echo "$APPROVAL_REQ" | jq '.frozen_receipt.total_cents')
    print_info "Frozen total: $(echo "scale=2; $FROZEN_TOTAL / 100" | bc) USD"
    print_info "Receipt hash: $(echo "$APPROVAL_REQ" | jq -r '.frozen_receipt.hash' | head -c 16)..."
    
    print_step "7" "Get new quote (price may change)"
    QUOTE2=$(curl -s -X POST "$API_URL/checkouts/$CHECKOUT_ID/quote" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d "{\"items\": [{\"product_id\": \"$PRODUCT_ID\", \"quantity\": 1}]}")
    TOTAL2=$(echo "$QUOTE2" | jq '.total.amount')
    print_info "New total: $(echo "scale=2; $TOTAL2 / 100" | bc) USD"
    
    if [ "$TOTAL1" != "$TOTAL2" ]; then
        print_warning "⚡ Price changed! Re-approval needed."
        print_info "Price difference: $(echo "scale=2; ($TOTAL2 - $TOTAL1) / 100" | bc) USD"
        
        print_step "8" "Request re-approval with new price"
        REAPPROVAL=$(curl -s -X POST "$API_URL/checkouts/$CHECKOUT_ID/request-approval" \
            -H "Authorization: Bearer $API_KEY")
        NEW_FROZEN=$(echo "$REAPPROVAL" | jq '.frozen_receipt.total_cents')
        print_info "New frozen total: $(echo "scale=2; $NEW_FROZEN / 100" | bc) USD"
    else
        print_info "Price unchanged (chaos didn't trigger this time)"
    fi
    
    # Reset chaos
    print_step "9" "Reset chaos controller"
    curl -s -X POST "$MERCHANT_B_URL/chaos/reset" > /dev/null
    print_success "Chaos reset"
    
    echo ""
    print_success "Price change demo complete!"
}

usage() {
    echo "Usage: $0 [scenario]"
    echo ""
    echo "Scenarios:"
    echo "  price_change      Enable price change chaos"
    echo "  out_of_stock      Enable out-of-stock chaos"
    echo "  duplicate_webhook Enable duplicate webhook chaos"
    echo "  all               Enable all chaos scenarios"
    echo "  reset             Reset chaos controller"
    echo "  status            Show current chaos configuration"
    echo "  events            Show recent chaos events"
    echo "  demo              Run price change demo flow"
    echo ""
    echo "Examples:"
    echo "  $0 price_change   # Enable price change scenario"
    echo "  $0 all            # Enable all chaos"
    echo "  $0 reset          # Disable all chaos"
    echo "  $0 demo           # Run interactive demo"
}

main() {
    echo -e "${MAGENTA}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║              CartPilot Chaos Mode Controller                  ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    check_services
    
    SCENARIO="${1:-status}"
    
    case "$SCENARIO" in
        price_change)
            enable_price_change
            ;;
        out_of_stock)
            enable_out_of_stock
            ;;
        duplicate_webhook)
            enable_duplicate_webhook
            ;;
        all)
            enable_all_chaos
            ;;
        reset)
            reset_chaos
            ;;
        status)
            show_chaos_status
            ;;
        events)
            show_chaos_events
            ;;
        demo)
            demo_price_change_flow
            ;;
        help|--help|-h)
            usage
            ;;
        *)
            print_error "Unknown scenario: $SCENARIO"
            usage
            exit 1
            ;;
    esac
}

main "$@"
