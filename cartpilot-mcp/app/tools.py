"""MCP Tools for CartPilot.

Defines the 8 MCP tools as thin adapters over the CartPilot REST API:
1. create_intent - Create purchase intent from text
2. list_offers - Get offers for an intent
3. get_offer_details - Get detailed offer information
4. request_approval - Initiate approval flow for a purchase
5. approve_purchase - Approve a pending purchase
6. get_order_status - Check order status
7. simulate_time - Advance order state for testing
8. trigger_chaos_case - Enable chaos scenarios for testing
"""

import uuid
from typing import Any

import structlog

from app.api_client import APIResponse, CartPilotAPIClient, MerchantBChaosClient

logger = structlog.get_logger()


def format_price(amount: int, currency: str = "USD") -> str:
    """Format price in cents to human-readable string."""
    return f"{amount / 100:.2f} {currency}"


def format_error(response: APIResponse) -> str:
    """Format an API error response for MCP output."""
    if response.error:
        return f"Error [{response.error.error_code}]: {response.error.message}"
    return "Unknown error occurred"


class MCPTools:
    """MCP Tools for CartPilot.

    Provides methods for each MCP tool that wrap the CartPilot API.
    Each method returns a formatted response suitable for AI agent consumption.
    """

    def __init__(
        self,
        api_client: CartPilotAPIClient,
        chaos_client: MerchantBChaosClient | None = None,
    ) -> None:
        """Initialize MCP tools.

        Args:
            api_client: CartPilot API client.
            chaos_client: Optional Merchant B chaos client.
        """
        self.api = api_client
        self.chaos = chaos_client

    # =========================================================================
    # Tool 1: create_intent
    # =========================================================================

    async def create_intent(
        self,
        query: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a purchase intent from natural language.

        This tool captures the user's purchase intention from their query.
        After creating an intent, use list_offers to get available offers.

        Args:
            query: Natural language description of what to purchase.
                   Example: "I want to buy a wireless keyboard under $50"
            session_id: Optional session ID for tracking the conversation.

        Returns:
            Intent details including ID, query, and status.
        """
        logger.info("Creating intent", query=query, session_id=session_id)

        response = await self.api.create_intent(
            query=query,
            session_id=session_id,
        )

        if not response.success:
            return {
                "success": False,
                "error": format_error(response),
            }

        intent = response.data
        return {
            "success": True,
            "intent_id": intent["id"],
            "query": intent["query"],
            "session_id": intent.get("session_id"),
            "created_at": intent["created_at"],
            "message": f"Intent created successfully. Use list_offers with intent_id '{intent['id']}' to get available products.",
        }

    # =========================================================================
    # Tool 2: list_offers
    # =========================================================================

    async def list_offers(
        self,
        intent_id: str,
        page: int = 1,
        page_size: int = 10,
    ) -> dict[str, Any]:
        """Get offers from merchants for an intent.

        This tool retrieves product offers from all enabled merchants
        based on the purchase intent. Returns normalized offers with
        pricing and availability information.

        Args:
            intent_id: The intent ID from create_intent.
            page: Page number for pagination (default: 1).
            page_size: Number of offers per page (default: 10, max: 100).

        Returns:
            List of offers with products, prices, and merchant info.
        """
        logger.info("Listing offers", intent_id=intent_id, page=page)

        response = await self.api.get_intent_offers(
            intent_id=intent_id,
            page=page,
            page_size=page_size,
        )

        if not response.success:
            return {
                "success": False,
                "error": format_error(response),
            }

        data = response.data
        offers = []

        for offer in data.get("items", []):
            items_summary = []
            for item in offer.get("items", [])[:3]:  # Show first 3 items
                price = item.get("price", {})
                items_summary.append({
                    "product_id": item["product_id"],
                    "title": item["title"],
                    "brand": item.get("brand"),
                    "price": format_price(
                        price.get("amount", 0),
                        price.get("currency", "USD"),
                    ),
                    "quantity_available": item.get("quantity_available", 0),
                })

            lowest = offer.get("lowest_price")
            highest = offer.get("highest_price")

            offers.append({
                "offer_id": offer["id"],
                "merchant_id": offer["merchant_id"],
                "item_count": offer["item_count"],
                "items_preview": items_summary,
                "price_range": {
                    "lowest": format_price(
                        lowest["amount"], lowest["currency"]
                    ) if lowest else None,
                    "highest": format_price(
                        highest["amount"], highest["currency"]
                    ) if highest else None,
                },
                "is_expired": offer.get("is_expired", False),
            })

        return {
            "success": True,
            "intent_id": intent_id,
            "offers": offers,
            "total": data.get("total", 0),
            "page": data.get("page", 1),
            "has_more": data.get("has_more", False),
            "message": f"Found {data.get('total', 0)} offer(s). Use get_offer_details to see full product info, or request_approval to start a purchase.",
        }

    # =========================================================================
    # Tool 3: get_offer_details
    # =========================================================================

    async def get_offer_details(
        self,
        offer_id: str,
    ) -> dict[str, Any]:
        """Get detailed information about a specific offer.

        This tool retrieves complete product details, pricing,
        and availability for all items in an offer.

        Args:
            offer_id: The offer ID from list_offers.

        Returns:
            Complete offer details with all product information.
        """
        logger.info("Getting offer details", offer_id=offer_id)

        response = await self.api.get_offer(offer_id)

        if not response.success:
            return {
                "success": False,
                "error": format_error(response),
            }

        offer = response.data
        items = []

        for item in offer.get("items", []):
            price = item.get("price", {})
            items.append({
                "product_id": item["product_id"],
                "variant_id": item.get("variant_id"),
                "sku": item.get("sku"),
                "title": item["title"],
                "description": item.get("description"),
                "brand": item.get("brand"),
                "category": item.get("category_path"),
                "price": {
                    "amount_cents": price.get("amount", 0),
                    "formatted": format_price(
                        price.get("amount", 0),
                        price.get("currency", "USD"),
                    ),
                    "currency": price.get("currency", "USD"),
                },
                "quantity_available": item.get("quantity_available", 0),
                "rating": item.get("rating"),
                "review_count": item.get("review_count"),
                "image_url": item.get("image_url"),
            })

        lowest = offer.get("lowest_price")
        highest = offer.get("highest_price")

        return {
            "success": True,
            "offer_id": offer["id"],
            "intent_id": offer["intent_id"],
            "merchant_id": offer["merchant_id"],
            "items": items,
            "item_count": offer["item_count"],
            "price_range": {
                "lowest": format_price(
                    lowest["amount"], lowest["currency"]
                ) if lowest else None,
                "highest": format_price(
                    highest["amount"], highest["currency"]
                ) if highest else None,
            },
            "expires_at": offer.get("expires_at"),
            "is_expired": offer.get("is_expired", False),
            "message": "Use request_approval with the offer_id and selected items to start the purchase approval flow.",
        }

    # =========================================================================
    # Tool 4: request_approval
    # =========================================================================

    async def request_approval(
        self,
        offer_id: str,
        items: list[dict[str, Any]],
        customer_email: str | None = None,
    ) -> dict[str, Any]:
        """Initiate the approval flow for a purchase.

        This tool creates a checkout from an offer, gets a quote from
        the merchant, and requests human approval. The checkout will be
        in 'awaiting_approval' state with a frozen receipt.

        Args:
            offer_id: The offer ID to purchase from.
            items: List of items to purchase. Each item should have:
                   - product_id: Product ID (required)
                   - variant_id: Variant ID (optional)
                   - quantity: Quantity to purchase (required)
            customer_email: Optional customer email for the receipt.

        Returns:
            Checkout details with frozen receipt awaiting approval.
        """
        logger.info("Requesting approval", offer_id=offer_id, items=items)

        # Generate idempotency key
        idempotency_key = f"approval-{uuid.uuid4()}"

        # Step 1: Create checkout
        create_response = await self.api.create_checkout(
            offer_id=offer_id,
            items=items,
            idempotency_key=idempotency_key,
        )

        if not create_response.success:
            return {
                "success": False,
                "error": format_error(create_response),
                "step": "create_checkout",
            }

        checkout_id = create_response.data["id"]

        # Step 2: Get quote from merchant
        quote_response = await self.api.quote_checkout(
            checkout_id=checkout_id,
            items=items,
            customer_email=customer_email,
        )

        if not quote_response.success:
            return {
                "success": False,
                "error": format_error(quote_response),
                "step": "get_quote",
                "checkout_id": checkout_id,
            }

        # Step 3: Request approval
        approval_response = await self.api.request_approval(checkout_id)

        if not approval_response.success:
            return {
                "success": False,
                "error": format_error(approval_response),
                "step": "request_approval",
                "checkout_id": checkout_id,
            }

        checkout = approval_response.data

        # Format the frozen receipt
        frozen_receipt = checkout.get("frozen_receipt", {})
        items_summary = []
        for item in checkout.get("items", []):
            unit_price = item.get("unit_price", {})
            line_total = item.get("line_total", {})
            items_summary.append({
                "title": item["title"],
                "quantity": item["quantity"],
                "unit_price": format_price(
                    unit_price.get("amount", 0),
                    unit_price.get("currency", "USD"),
                ),
                "line_total": format_price(
                    line_total.get("amount", 0),
                    line_total.get("currency", "USD"),
                ),
            })

        total = checkout.get("total", {})
        subtotal = checkout.get("subtotal", {})
        tax = checkout.get("tax", {})
        shipping = checkout.get("shipping", {})

        return {
            "success": True,
            "checkout_id": checkout["id"],
            "status": checkout["status"],
            "merchant_id": checkout["merchant_id"],
            "items": items_summary,
            "pricing": {
                "subtotal": format_price(
                    subtotal.get("amount", 0),
                    subtotal.get("currency", "USD"),
                ),
                "tax": format_price(
                    tax.get("amount", 0),
                    tax.get("currency", "USD"),
                ),
                "shipping": format_price(
                    shipping.get("amount", 0),
                    shipping.get("currency", "USD"),
                ),
                "total": format_price(
                    total.get("amount", 0),
                    total.get("currency", "USD"),
                ),
            },
            "receipt_hash": frozen_receipt.get("hash") or checkout.get("receipt_hash"),
            "expires_at": checkout.get("expires_at"),
            "message": "Purchase is awaiting approval. Review the details and use approve_purchase to proceed.",
            "requires_action": "approve_purchase",
        }

    # =========================================================================
    # Tool 5: approve_purchase
    # =========================================================================

    async def approve_purchase(
        self,
        checkout_id: str,
        approved_by: str,
        confirm: bool = True,
        payment_method: str = "test_card",
    ) -> dict[str, Any]:
        """Approve a pending purchase and optionally confirm it.

        This tool approves a checkout that is awaiting approval.
        If confirm=True (default), it also confirms the purchase
        with the merchant, creating an order.

        Args:
            checkout_id: The checkout ID to approve.
            approved_by: Identifier of who is approving (e.g., "user", "agent").
            confirm: Whether to also confirm the purchase (default: True).
            payment_method: Payment method to use if confirming (default: "test_card").

        Returns:
            Approval result and order details if confirmed.
        """
        logger.info(
            "Approving purchase",
            checkout_id=checkout_id,
            approved_by=approved_by,
            confirm=confirm,
        )

        # Step 1: Approve the checkout
        approve_response = await self.api.approve_checkout(
            checkout_id=checkout_id,
            approved_by=approved_by,
        )

        if not approve_response.success:
            error = approve_response.error
            if error and error.error_code == "REAPPROVAL_REQUIRED":
                return {
                    "success": False,
                    "error": format_error(approve_response),
                    "reapproval_required": True,
                    "message": "Price has changed since approval was requested. Please review the new price and request approval again.",
                }
            return {
                "success": False,
                "error": format_error(approve_response),
            }

        if not confirm:
            checkout = approve_response.data
            return {
                "success": True,
                "checkout_id": checkout["id"],
                "status": checkout["status"],
                "approved_by": checkout.get("approved_by"),
                "approved_at": checkout.get("approved_at"),
                "message": "Purchase approved. Use confirm=True to execute the purchase.",
            }

        # Step 2: Confirm with merchant
        idempotency_key = f"confirm-{checkout_id}-{uuid.uuid4()}"
        confirm_response = await self.api.confirm_checkout(
            checkout_id=checkout_id,
            payment_method=payment_method,
            idempotency_key=idempotency_key,
        )

        if not confirm_response.success:
            error = confirm_response.error
            if error and error.error_code == "REAPPROVAL_REQUIRED":
                return {
                    "success": False,
                    "error": format_error(confirm_response),
                    "reapproval_required": True,
                    "approved": True,
                    "message": "Price changed during confirmation. Please re-request approval with the new price.",
                }
            return {
                "success": False,
                "error": format_error(confirm_response),
                "approved": True,
                "message": "Checkout was approved but confirmation failed.",
            }

        result = confirm_response.data
        total = result.get("total", {})

        return {
            "success": True,
            "checkout_id": result["checkout_id"],
            "order_id": result.get("order_id"),
            "merchant_order_id": result.get("merchant_order_id"),
            "status": result["status"],
            "total": format_price(
                total.get("amount", 0),
                total.get("currency", "USD"),
            ),
            "confirmed_at": result.get("confirmed_at"),
            "message": f"Purchase confirmed! Order ID: {result.get('order_id', 'N/A')}. Use get_order_status to track the order.",
        }

    # =========================================================================
    # Tool 6: get_order_status
    # =========================================================================

    async def get_order_status(
        self,
        order_id: str,
    ) -> dict[str, Any]:
        """Check the status of an order.

        This tool retrieves the current status and details of an order,
        including shipping information if available.

        Args:
            order_id: The order ID to check.

        Returns:
            Order status, tracking info, and delivery details.
        """
        logger.info("Getting order status", order_id=order_id)

        response = await self.api.get_order(order_id)

        if not response.success:
            return {
                "success": False,
                "error": format_error(response),
            }

        order = response.data
        total = order.get("total", {})

        # Format items
        items = []
        for item in order.get("items", []):
            unit_price = item.get("unit_price", {})
            items.append({
                "product_id": item["product_id"],
                "title": item["title"],
                "quantity": item["quantity"],
                "unit_price": format_price(
                    unit_price.get("amount", 0),
                    unit_price.get("currency", "USD"),
                ),
            })

        # Build status timeline
        timeline = []
        if order.get("created_at"):
            timeline.append({"status": "created", "at": order["created_at"]})
        if order.get("confirmed_at"):
            timeline.append({"status": "confirmed", "at": order["confirmed_at"]})
        if order.get("shipped_at"):
            timeline.append({"status": "shipped", "at": order["shipped_at"]})
        if order.get("delivered_at"):
            timeline.append({"status": "delivered", "at": order["delivered_at"]})
        if order.get("cancelled_at"):
            timeline.append({"status": "cancelled", "at": order["cancelled_at"]})
        if order.get("refunded_at"):
            timeline.append({"status": "refunded", "at": order["refunded_at"]})

        result = {
            "success": True,
            "order_id": order["id"],
            "checkout_id": order.get("checkout_id"),
            "merchant_id": order["merchant_id"],
            "merchant_order_id": order.get("merchant_order_id"),
            "status": order["status"],
            "items": items,
            "total": format_price(
                total.get("amount", 0),
                total.get("currency", "USD"),
            ),
            "timeline": timeline,
        }

        # Add shipping info if available
        if order.get("tracking_number"):
            result["shipping"] = {
                "tracking_number": order["tracking_number"],
                "carrier": order.get("carrier"),
            }

        # Add cancellation/refund info if applicable
        if order.get("cancelled_reason"):
            result["cancellation"] = {
                "reason": order["cancelled_reason"],
                "cancelled_by": order.get("cancelled_by"),
            }

        if order.get("refund_amount"):
            refund = order["refund_amount"]
            result["refund"] = {
                "amount": format_price(
                    refund.get("amount", 0),
                    refund.get("currency", "USD"),
                ),
                "reason": order.get("refund_reason"),
            }

        # Add helpful message based on status
        status_messages = {
            "created": "Order created, awaiting payment confirmation.",
            "pending": "Order is pending processing.",
            "confirmed": "Order confirmed, preparing for shipment.",
            "paid": "Payment received, awaiting shipment.",
            "shipped": f"Order shipped! Tracking: {order.get('tracking_number', 'N/A')}",
            "delivered": "Order delivered successfully.",
            "cancelled": "Order has been cancelled.",
            "refunded": "Order has been refunded.",
        }
        result["message"] = status_messages.get(
            order["status"],
            f"Order status: {order['status']}",
        )

        return result

    # =========================================================================
    # Tool 7: simulate_time
    # =========================================================================

    async def simulate_time(
        self,
        order_id: str,
        steps: int = 1,
    ) -> dict[str, Any]:
        """Advance order state for testing purposes.

        This tool simulates time passing to advance an order through
        its lifecycle states: pending -> confirmed -> shipped -> delivered.
        Useful for testing without waiting for real merchant updates.

        Args:
            order_id: The order ID to advance.
            steps: Number of state transitions to make (default: 1).

        Returns:
            Updated order status after advancement.
        """
        logger.info("Simulating time", order_id=order_id, steps=steps)

        response = await self.api.simulate_advance_order(
            order_id=order_id,
            steps=steps,
        )

        if not response.success:
            return {
                "success": False,
                "error": format_error(response),
            }

        order = response.data
        total = order.get("total", {})

        return {
            "success": True,
            "order_id": order["id"],
            "previous_status": None,  # API doesn't return this
            "new_status": order["status"],
            "steps_advanced": steps,
            "total": format_price(
                total.get("amount", 0),
                total.get("currency", "USD"),
            ),
            "message": f"Order advanced to '{order['status']}' status.",
        }

    # =========================================================================
    # Tool 8: trigger_chaos_case
    # =========================================================================

    async def trigger_chaos_case(
        self,
        scenario: str,
        enable: bool = True,
    ) -> dict[str, Any]:
        """Enable or disable chaos scenarios for testing.

        This tool configures chaos mode on Merchant B to simulate
        edge cases and error conditions for resilience testing.

        Available scenarios:
        - price_change: Prices change between quote and confirm
        - out_of_stock: Items become unavailable after checkout
        - duplicate_webhook: Same webhook sent multiple times
        - delayed_webhook: Webhooks delivered after a delay
        - out_of_order_webhook: Webhooks sent in wrong sequence

        Args:
            scenario: Chaos scenario name (or "all" for all scenarios).
            enable: Whether to enable (True) or disable (False) the scenario.

        Returns:
            Updated chaos configuration.
        """
        if not self.chaos:
            return {
                "success": False,
                "error": "Chaos client not configured. Merchant B may not be available.",
            }

        logger.info("Triggering chaos case", scenario=scenario, enable=enable)

        valid_scenarios = [
            "price_change",
            "out_of_stock",
            "duplicate_webhook",
            "delayed_webhook",
            "out_of_order_webhook",
            "all",
        ]

        if scenario not in valid_scenarios:
            return {
                "success": False,
                "error": f"Invalid scenario. Valid options: {', '.join(valid_scenarios)}",
            }

        try:
            if scenario == "all":
                if enable:
                    response = await self.chaos.enable_all()
                else:
                    response = await self.chaos.disable_all()
            else:
                if enable:
                    response = await self.chaos.enable_scenario(scenario)
                else:
                    response = await self.chaos.disable_scenario(scenario)

            if not response.success:
                return {
                    "success": False,
                    "error": format_error(response),
                }

            config = response.data
            enabled_scenarios = [
                k for k, v in config.get("scenarios", {}).items() if v
            ]

            return {
                "success": True,
                "chaos_enabled": config.get("enabled", False),
                "scenario": scenario,
                "action": "enabled" if enable else "disabled",
                "enabled_scenarios": enabled_scenarios,
                "config": {
                    "price_change_percent": config.get("price_change_percent", 15),
                    "out_of_stock_probability": config.get("out_of_stock_probability", 0.3),
                    "duplicate_webhook_count": config.get("duplicate_webhook_count", 3),
                    "webhook_delay_seconds": config.get("webhook_delay_seconds", 5.0),
                },
                "message": f"Chaos scenario '{scenario}' {'enabled' if enable else 'disabled'}. "
                f"Active scenarios: {', '.join(enabled_scenarios) or 'none'}",
            }

        except Exception as e:
            logger.exception("Chaos trigger failed", scenario=scenario)
            return {
                "success": False,
                "error": f"Failed to configure chaos: {str(e)}",
            }
