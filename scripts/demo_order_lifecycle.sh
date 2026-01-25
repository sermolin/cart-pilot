#!/bin/bash
# =============================================================================
# CartPilot Demo: Order Lifecycle Simulation
# =============================================================================
#
# This script demonstrates the complete order lifecycle:
# 1. Complete a purchase
# 2. Advance through order states
# 3. Show order history at each state
# 4. Optionally cancel and refund
#
# Prerequisites:
# - docker compose up (all services running)
# - jq installed (for JSON parsing)
#
# Usage:
#   ./scripts/demo_order_lifecycle.sh [--refund]
#
# Options:
#   --refund    Also demonstrate cancel and refund flow
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
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Parse arguments
SHOW_REFUND=false
if [ "$1" == "--refund" ]; then
    SHOW_REFUND=true
fi

# Helper functions
print_state() {
    local state=$1
    local icon=""
    
    case "$state" in
        pending)    icon="⏳" ;;
        confirmed)  icon="✅" ;;
        shipped)    icon="🚚" ;;
        delivered)  icon="📦" ;;
        cancelled)  icon="❌" ;;
        refunded)   icon="💰" ;;
        *)          icon="•" ;;
    esac
    
    echo -e "${CYAN}$icon ${state^^}${NC}"
}

print_timeline() {
    local current=$1
    local states=("pending" "confirmed" "shipped" "delivered")
    
    echo -e "\n${BLUE}Order Timeline:${NC}"
    for state in "${states[@]}"; do
        if [ "$state" == "$current" ]; then
            echo -e "  ${GREEN}●━━${NC} $state ${GREEN}← current${NC}"
        else
            # Check if state comes before or after current
            case "$current" in
                pending)
                    echo -e "  ${YELLOW}○  ${NC} $state"
                    ;;
                confirmed)
                    if [ "$state" == "pending" ]; then
                        echo -e "  ${GREEN}●━━${NC} $state"
                    else
                        echo -e "  ${YELLOW}○  ${NC} $state"
                    fi
                    ;;
                shipped)
                    if [ "$state" == "pending" ] || [ "$state" == "confirmed" ]; then
                        echo -e "  ${GREEN}●━━${NC} $state"
                    else
                        echo -e "  ${YELLOW}○  ${NC} $state"
                    fi
                    ;;
                delivered)
                    echo -e "  ${GREEN}●━━${NC} $state"
                    ;;
            esac
        fi
    done
}

check_api() {
    if ! curl -s -f "$API_URL/health" > /dev/null; then
        echo -e "${RED}Error: CartPilot API not responding${NC}"
        exit 1
    fi
}

create_order() {
    echo -e "\n${BLUE}━━━ Creating Order ━━━${NC}"
    
    # Create intent
    echo -e "${YELLOW}→${NC} Creating intent..."
    INTENT=$(curl -s -X POST "$API_URL/intents" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d '{"query": "test order", "session_id": "lifecycle-demo"}')
    INTENT_ID=$(echo "$INTENT" | jq -r '.id')
    
    # Get offers
    echo -e "${YELLOW}→${NC} Getting offers..."
    OFFERS=$(curl -s "$API_URL/intents/$INTENT_ID/offers" \
        -H "Authorization: Bearer $API_KEY")
    OFFER_ID=$(echo "$OFFERS" | jq -r '.items[0].id')
    PRODUCT_ID=$(echo "$OFFERS" | jq -r '.items[0].items[0].product_id')
    
    if [ "$OFFER_ID" == "null" ]; then
        echo -e "${RED}No offers available${NC}"
        exit 1
    fi
    
    # Create checkout
    echo -e "${YELLOW}→${NC} Creating checkout..."
    CHECKOUT=$(curl -s -X POST "$API_URL/checkouts" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d "{\"offer_id\": \"$OFFER_ID\", \"items\": [{\"product_id\": \"$PRODUCT_ID\", \"quantity\": 1}]}")
    CHECKOUT_ID=$(echo "$CHECKOUT" | jq -r '.id')
    
    # Quote
    echo -e "${YELLOW}→${NC} Getting quote..."
    curl -s -X POST "$API_URL/checkouts/$CHECKOUT_ID/quote" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d "{\"items\": [{\"product_id\": \"$PRODUCT_ID\", \"quantity\": 1}]}" > /dev/null
    
    # Request approval
    echo -e "${YELLOW}→${NC} Requesting approval..."
    curl -s -X POST "$API_URL/checkouts/$CHECKOUT_ID/request-approval" \
        -H "Authorization: Bearer $API_KEY" > /dev/null
    
    # Approve
    echo -e "${YELLOW}→${NC} Approving..."
    curl -s -X POST "$API_URL/checkouts/$CHECKOUT_ID/approve" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d '{"approved_by": "demo"}' > /dev/null
    
    # Confirm
    echo -e "${YELLOW}→${NC} Confirming purchase..."
    CONFIRM=$(curl -s -X POST "$API_URL/checkouts/$CHECKOUT_ID/confirm" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d '{"payment_method": "test_card"}')
    
    ORDER_ID=$(echo "$CONFIRM" | jq -r '.order_id')
    
    if [ "$ORDER_ID" == "null" ]; then
        echo -e "${RED}Failed to create order${NC}"
        echo "$CONFIRM" | jq .
        exit 1
    fi
    
    echo -e "${GREEN}✓${NC} Order created: $ORDER_ID"
    echo "$ORDER_ID"
}

get_order_status() {
    local order_id=$1
    curl -s "$API_URL/orders/$order_id" \
        -H "Authorization: Bearer $API_KEY"
}

advance_order() {
    local order_id=$1
    local steps=${2:-1}
    
    curl -s -X POST "$API_URL/orders/$order_id/simulate-advance" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d "{\"steps\": $steps}"
}

show_order() {
    local order_id=$1
    local order=$(get_order_status "$order_id")
    local status=$(echo "$order" | jq -r '.status')
    local total=$(echo "$order" | jq '.total.amount')
    local currency=$(echo "$order" | jq -r '.total.currency')
    
    echo ""
    print_state "$status"
    echo -e "  Order ID: ${YELLOW}$order_id${NC}"
    echo -e "  Total:    $(echo "scale=2; $total / 100" | bc) $currency"
    
    # Show shipping info if available
    local tracking=$(echo "$order" | jq -r '.tracking_number // empty')
    if [ -n "$tracking" ]; then
        local carrier=$(echo "$order" | jq -r '.carrier // "Unknown"')
        echo -e "  Tracking: $tracking ($carrier)"
    fi
    
    print_timeline "$status"
}

main() {
    echo -e "${GREEN}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║           CartPilot Order Lifecycle Demo                      ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    check_api
    
    # Create order
    ORDER_ID=$(create_order)
    
    # Show initial state
    echo -e "\n${BLUE}━━━ Order Lifecycle Progression ━━━${NC}"
    show_order "$ORDER_ID"
    
    read -p "Press Enter to advance to CONFIRMED..."
    
    # Advance to confirmed
    advance_order "$ORDER_ID" 1 > /dev/null
    show_order "$ORDER_ID"
    
    read -p "Press Enter to advance to SHIPPED..."
    
    # Advance to shipped
    advance_order "$ORDER_ID" 1 > /dev/null
    show_order "$ORDER_ID"
    
    read -p "Press Enter to advance to DELIVERED..."
    
    # Advance to delivered
    advance_order "$ORDER_ID" 1 > /dev/null
    show_order "$ORDER_ID"
    
    # Show refund flow if requested
    if [ "$SHOW_REFUND" == "true" ]; then
        echo -e "\n${BLUE}━━━ Refund Flow ━━━${NC}"
        read -p "Press Enter to initiate refund..."
        
        # Refund the order (can refund delivered orders)
        echo -e "${YELLOW}→${NC} Processing refund..."
        REFUND=$(curl -s -X POST "$API_URL/orders/$ORDER_ID/refund" \
            -H "Authorization: Bearer $API_KEY" \
            -H "Content-Type: application/json" \
            -d '{"reason": "Customer return"}')
        
        show_order "$ORDER_ID"
    fi
    
    # Summary
    echo -e "\n${GREEN}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║                    Demo Complete!                             ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    echo "Order lifecycle states demonstrated:"
    echo "  • PENDING    - Order created, awaiting confirmation"
    echo "  • CONFIRMED  - Payment confirmed, preparing for shipment"
    echo "  • SHIPPED    - Order shipped with tracking"
    echo "  • DELIVERED  - Order delivered to customer"
    
    if [ "$SHOW_REFUND" == "true" ]; then
        echo "  • REFUNDED   - Order refunded"
    fi
    
    echo ""
    echo "To run the refund demo: $0 --refund"
}

main "$@"
