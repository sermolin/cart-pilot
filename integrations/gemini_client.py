"""Gemini Function Calling client for CartPilot.

This module provides a Python client for integrating CartPilot API with
Google Gemini Function Calling capabilities.

Example usage:
    import google.generativeai as genai
    from integrations.gemini_client import CartPilotGeminiClient
    
    # Initialize client
    genai.configure(api_key="YOUR_GEMINI_API_KEY")
    client = CartPilotGeminiClient(
        cartpilot_api_url="https://cartpilot-api.run.app",
        api_key="YOUR_CARTPILOT_API_KEY"
    )
    
    # Get function definitions for Gemini
    functions = client.get_function_declarations()
    
    # Start chat with Gemini
    model = genai.GenerativeModel(
        model_name="gemini-1.5-pro",
        tools=[{"function_declarations": functions}]
    )
    
    # Chat loop
    chat = model.start_chat()
    response = chat.send_message("I need wireless headphones under $100")
    
    # Handle function calls
    if response.candidates[0].content.parts[0].function_call:
        result = client.handle_function_call(response.candidates[0].content.parts[0].function_call)
        # Send result back to Gemini
        chat.send_message(result)
"""

import json
from typing import Any, Dict, List, Optional

import google.generativeai as genai
import httpx


class CartPilotAPIClient:
    """Client for CartPilot REST API."""

    def __init__(self, api_url: str, api_key: str):
        """Initialize CartPilot API client.

        Args:
            api_url: Base URL of CartPilot API
            api_key: API key for authentication
        """
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            base_url=self.api_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )

    async def create_intent(self, query: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a purchase intent.

        Args:
            query: Natural language search query
            session_id: Optional session identifier

        Returns:
            Intent response data
        """
        response = await self.client.post(
            "/intents",
            json={"query": query, "session_id": session_id},
        )
        response.raise_for_status()
        return response.json()

    async def get_intent(self, intent_id: str) -> Dict[str, Any]:
        """Get intent details.

        Args:
            intent_id: Intent identifier

        Returns:
            Intent response data
        """
        response = await self.client.get(f"/intents/{intent_id}")
        response.raise_for_status()
        return response.json()

    async def get_intent_offers(
        self, intent_id: str, page: int = 1, page_size: int = 20
    ) -> Dict[str, Any]:
        """Get offers for an intent.

        Args:
            intent_id: Intent identifier
            page: Page number
            page_size: Items per page

        Returns:
            Offers list response
        """
        response = await self.client.get(
            f"/intents/{intent_id}/offers",
            params={"page": page, "page_size": page_size},
        )
        response.raise_for_status()
        return response.json()

    async def get_offer(self, offer_id: str) -> Dict[str, Any]:
        """Get offer details.

        Args:
            offer_id: Offer identifier

        Returns:
            Offer response data
        """
        response = await self.client.get(f"/offers/{offer_id}")
        response.raise_for_status()
        return response.json()

    async def create_checkout(
        self, offer_id: str, items: List[Dict[str, Any]], idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create checkout from offer.

        Args:
            offer_id: Offer identifier
            items: List of items with product_id, variant_id (optional), quantity
            idempotency_key: Optional idempotency key

        Returns:
            Checkout response data
        """
        response = await self.client.post(
            "/checkouts",
            json={"offer_id": offer_id, "items": items, "idempotency_key": idempotency_key},
        )
        response.raise_for_status()
        return response.json()

    async def get_checkout(self, checkout_id: str) -> Dict[str, Any]:
        """Get checkout details.

        Args:
            checkout_id: Checkout identifier

        Returns:
            Checkout response data
        """
        response = await self.client.get(f"/checkouts/{checkout_id}")
        response.raise_for_status()
        return response.json()

    async def quote_checkout(
        self, checkout_id: str, items: List[Dict[str, Any]], customer_email: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get quote from merchant.

        Args:
            checkout_id: Checkout identifier
            items: List of items
            customer_email: Optional customer email

        Returns:
            Checkout response with quote
        """
        response = await self.client.post(
            f"/checkouts/{checkout_id}/quote",
            json={"items": items, "customer_email": customer_email},
        )
        response.raise_for_status()
        return response.json()

    async def request_approval(self, checkout_id: str) -> Dict[str, Any]:
        """Request approval for checkout.

        Args:
            checkout_id: Checkout identifier

        Returns:
            Checkout response with frozen receipt
        """
        response = await self.client.post(f"/checkouts/{checkout_id}/request-approval")
        response.raise_for_status()
        return response.json()

    async def approve_checkout(self, checkout_id: str, approved_by: str = "user") -> Dict[str, Any]:
        """Approve checkout.

        Args:
            checkout_id: Checkout identifier
            approved_by: Who is approving

        Returns:
            Approved checkout response
        """
        response = await self.client.post(
            f"/checkouts/{checkout_id}/approve", json={"approved_by": approved_by}
        )
        response.raise_for_status()
        return response.json()

    async def confirm_checkout(
        self, checkout_id: str, payment_method: str = "test_card", idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Confirm checkout and execute purchase.

        Args:
            checkout_id: Checkout identifier
            payment_method: Payment method identifier
            idempotency_key: Optional idempotency key

        Returns:
            Confirmation response with order ID
        """
        response = await self.client.post(
            f"/checkouts/{checkout_id}/confirm",
            json={"payment_method": payment_method, "idempotency_key": idempotency_key},
        )
        response.raise_for_status()
        return response.json()

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        """Get order details.

        Args:
            order_id: Order identifier

        Returns:
            Order response data
        """
        response = await self.client.get(f"/orders/{order_id}")
        response.raise_for_status()
        return response.json()

    async def list_orders(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        merchant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List orders.

        Args:
            page: Page number
            page_size: Items per page
            status: Filter by status
            merchant_id: Filter by merchant

        Returns:
            Orders list response
        """
        params = {"page": page, "page_size": page_size}
        if status:
            params["status"] = status
        if merchant_id:
            params["merchant_id"] = merchant_id

        response = await self.client.get("/orders", params=params)
        response.raise_for_status()
        return response.json()

    async def cancel_order(self, order_id: str, reason: str, cancelled_by: str = "customer") -> Dict[str, Any]:
        """Cancel an order.

        Args:
            order_id: Order identifier
            reason: Cancellation reason
            cancelled_by: Who is cancelling

        Returns:
            Updated order response
        """
        response = await self.client.post(
            f"/orders/{order_id}/cancel", json={"reason": reason, "cancelled_by": cancelled_by}
        )
        response.raise_for_status()
        return response.json()

    async def refund_order(
        self, order_id: str, refund_amount_cents: Optional[int] = None, reason: str = ""
    ) -> Dict[str, Any]:
        """Refund an order.

        Args:
            order_id: Order identifier
            refund_amount_cents: Refund amount in cents (None for full refund)
            reason: Refund reason

        Returns:
            Updated order response
        """
        response = await self.client.post(
            f"/orders/{order_id}/refund",
            json={"refund_amount_cents": refund_amount_cents, "reason": reason},
        )
        response.raise_for_status()
        return response.json()

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


class CartPilotGeminiClient:
    """Client for integrating CartPilot with Gemini Function Calling."""

    def __init__(self, cartpilot_api_url: str, api_key: str):
        """Initialize Gemini client for CartPilot.

        Args:
            cartpilot_api_url: Base URL of CartPilot API
            api_key: CartPilot API key
        """
        self.api_client = CartPilotAPIClient(cartpilot_api_url, api_key)

    def get_function_declarations(self) -> List[Dict[str, Any]]:
        """Get function declarations for Gemini.

        Returns:
            List of function declarations compatible with Gemini Function Calling
        """
        return [
            {
                "name": "create_intent",
                "description": "Create a purchase intent from a natural language query. Use this when the user wants to buy something or search for products.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language search query describing what the user wants to buy (e.g., 'wireless headphones under $100', 'laptop for programming')",
                        },
                        "session_id": {
                            "type": "string",
                            "description": "Optional session identifier for tracking the conversation",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_intent_offers",
                "description": "Get product offers from merchants for a purchase intent. Call this after creating an intent to see available products and prices.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "intent_id": {
                            "type": "string",
                            "description": "Intent identifier returned from create_intent",
                        },
                        "page": {
                            "type": "integer",
                            "description": "Page number for pagination (default: 1)",
                            "default": 1,
                        },
                        "page_size": {
                            "type": "integer",
                            "description": "Number of offers per page (default: 20, max: 100)",
                            "default": 20,
                        },
                    },
                    "required": ["intent_id"],
                },
            },
            {
                "name": "get_offer_details",
                "description": "Get detailed information about a specific offer including all product items, pricing, and merchant details.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "offer_id": {
                            "type": "string",
                            "description": "Offer identifier from get_intent_offers",
                        },
                    },
                    "required": ["offer_id"],
                },
            },
            {
                "name": "create_checkout",
                "description": "Create a checkout session from an offer. Use this when the user selects products they want to purchase.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "offer_id": {
                            "type": "string",
                            "description": "Offer identifier",
                        },
                        "items": {
                            "type": "array",
                            "description": "List of items to purchase",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "product_id": {
                                        "type": "string",
                                        "description": "Product ID from the offer",
                                    },
                                    "variant_id": {
                                        "type": "string",
                                        "description": "Variant ID if applicable (optional)",
                                    },
                                    "quantity": {
                                        "type": "integer",
                                        "description": "Quantity to purchase",
                                        "minimum": 1,
                                    },
                                },
                                "required": ["product_id", "quantity"],
                            },
                        },
                        "idempotency_key": {
                            "type": "string",
                            "description": "Optional idempotency key for safe retries",
                        },
                    },
                    "required": ["offer_id", "items"],
                },
            },
            {
                "name": "get_checkout",
                "description": "Get current status and details of a checkout session.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "checkout_id": {
                            "type": "string",
                            "description": "Checkout identifier",
                        },
                    },
                    "required": ["checkout_id"],
                },
            },
            {
                "name": "quote_checkout",
                "description": "Get a quote from the merchant for checkout items. This gets current pricing and transitions checkout to 'quoted' state.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "checkout_id": {
                            "type": "string",
                            "description": "Checkout identifier",
                        },
                        "items": {
                            "type": "array",
                            "description": "List of items to quote",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "product_id": {"type": "string"},
                                    "variant_id": {"type": "string"},
                                    "quantity": {"type": "integer", "minimum": 1},
                                },
                                "required": ["product_id", "quantity"],
                            },
                        },
                        "customer_email": {
                            "type": "string",
                            "description": "Customer email for receipt (optional)",
                        },
                    },
                    "required": ["checkout_id", "items"],
                },
            },
            {
                "name": "request_approval",
                "description": "Request approval for a checkout and freeze the receipt. This creates a snapshot of pricing to detect price changes. Call this before asking the user to approve the purchase.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "checkout_id": {
                            "type": "string",
                            "description": "Checkout identifier",
                        },
                    },
                    "required": ["checkout_id"],
                },
            },
            {
                "name": "approve_checkout",
                "description": "Approve a checkout for purchase. Call this after the user explicitly approves the purchase. If price has changed, this will return an error requiring reapproval.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "checkout_id": {
                            "type": "string",
                            "description": "Checkout identifier",
                        },
                        "approved_by": {
                            "type": "string",
                            "description": "Identifier of who is approving (default: 'user')",
                            "default": "user",
                        },
                    },
                    "required": ["checkout_id"],
                },
            },
            {
                "name": "confirm_checkout",
                "description": "Confirm and execute the purchase. This finalizes the checkout and creates an order. Only call this after the checkout has been approved.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "checkout_id": {
                            "type": "string",
                            "description": "Checkout identifier",
                        },
                        "payment_method": {
                            "type": "string",
                            "description": "Payment method identifier (default: 'test_card')",
                            "default": "test_card",
                        },
                        "idempotency_key": {
                            "type": "string",
                            "description": "Optional idempotency key for safe retries",
                        },
                    },
                    "required": ["checkout_id"],
                },
            },
            {
                "name": "get_order_status",
                "description": "Get order details and current status including shipping information and tracking details.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "order_id": {
                            "type": "string",
                            "description": "Order identifier from confirm_checkout",
                        },
                    },
                    "required": ["order_id"],
                },
            },
            {
                "name": "list_orders",
                "description": "List orders with optional filtering by status or merchant.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "page": {
                            "type": "integer",
                            "description": "Page number (default: 1)",
                            "default": 1,
                        },
                        "page_size": {
                            "type": "integer",
                            "description": "Items per page (default: 20, max: 100)",
                            "default": 20,
                        },
                        "status": {
                            "type": "string",
                            "description": "Filter by order status (pending, confirmed, shipped, delivered, cancelled, refunded)",
                            "enum": ["pending", "confirmed", "shipped", "delivered", "cancelled", "refunded"],
                        },
                        "merchant_id": {
                            "type": "string",
                            "description": "Filter by merchant ID",
                        },
                    },
                },
            },
        ]

    async def handle_function_call(self, function_call: Any) -> Dict[str, Any]:
        """Handle a function call from Gemini.

        Args:
            function_call: Function call object from Gemini response

        Returns:
            Function response to send back to Gemini

        Raises:
            ValueError: If function name is not recognized
        """
        function_name = function_call.name
        args = dict(function_call.args)

        try:
            if function_name == "create_intent":
                result = await self.api_client.create_intent(
                    query=args["query"], session_id=args.get("session_id")
                )
            elif function_name == "get_intent_offers":
                result = await self.api_client.get_intent_offers(
                    intent_id=args["intent_id"],
                    page=args.get("page", 1),
                    page_size=args.get("page_size", 20),
                )
            elif function_name == "get_offer_details":
                result = await self.api_client.get_offer(offer_id=args["offer_id"])
            elif function_name == "create_checkout":
                result = await self.api_client.create_checkout(
                    offer_id=args["offer_id"],
                    items=args["items"],
                    idempotency_key=args.get("idempotency_key"),
                )
            elif function_name == "get_checkout":
                result = await self.api_client.get_checkout(checkout_id=args["checkout_id"])
            elif function_name == "quote_checkout":
                result = await self.api_client.quote_checkout(
                    checkout_id=args["checkout_id"],
                    items=args["items"],
                    customer_email=args.get("customer_email"),
                )
            elif function_name == "request_approval":
                result = await self.api_client.request_approval(checkout_id=args["checkout_id"])
            elif function_name == "approve_checkout":
                result = await self.api_client.approve_checkout(
                    checkout_id=args["checkout_id"], approved_by=args.get("approved_by", "user")
                )
            elif function_name == "confirm_checkout":
                result = await self.api_client.confirm_checkout(
                    checkout_id=args["checkout_id"],
                    payment_method=args.get("payment_method", "test_card"),
                    idempotency_key=args.get("idempotency_key"),
                )
            elif function_name == "get_order_status":
                result = await self.api_client.get_order(order_id=args["order_id"])
            elif function_name == "list_orders":
                result = await self.api_client.list_orders(
                    page=args.get("page", 1),
                    page_size=args.get("page_size", 20),
                    status=args.get("status"),
                    merchant_id=args.get("merchant_id"),
                )
            else:
                raise ValueError(f"Unknown function: {function_name}")

            return {
                "name": function_name,
                "response": result,
            }
        except httpx.HTTPStatusError as e:
            error_data = e.response.json() if e.response else {}
            return {
                "name": function_name,
                "response": {
                    "error": True,
                    "error_code": error_data.get("error_code", "HTTP_ERROR"),
                    "message": error_data.get("message", str(e)),
                },
            }
        except Exception as e:
            return {
                "name": function_name,
                "response": {
                    "error": True,
                    "error_code": "UNKNOWN_ERROR",
                    "message": str(e),
                },
            }

    async def close(self):
        """Close the API client."""
        await self.api_client.close()


async def example_usage():
    """Example usage of CartPilot Gemini client."""
    import os

    import google.generativeai as genai

    # Configure Gemini
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

    # Initialize CartPilot client
    client = CartPilotGeminiClient(
        cartpilot_api_url=os.getenv("CARTPILOT_API_URL", "http://localhost:8000"),
        api_key=os.getenv("CARTPILOT_API_KEY", "dev-api-key-change-in-production"),
    )

    # Get function declarations
    functions = client.get_function_declarations()

    # Create Gemini model with functions
    model = genai.GenerativeModel(
        model_name="gemini-1.5-pro",
        tools=[{"function_declarations": functions}],
    )

    # Start chat
    chat = model.start_chat()

    # User message
    user_message = "I need wireless headphones under $100"

    print(f"User: {user_message}")
    response = chat.send_message(user_message)

    # Handle function calls
    for candidate in response.candidates:
        for part in candidate.content.parts:
            if hasattr(part, "function_call") and part.function_call:
                print(f"\nGemini called function: {part.function_call.name}")
                result = await client.handle_function_call(part.function_call)
                print(f"Function result: {json.dumps(result, indent=2)}")

                # Send result back to Gemini
                chat.send_message(
                    genai.protos.FunctionResponse(
                        name=result["name"],
                        response=result["response"],
                    )
                )

                # Get final response
                final_response = chat.send_message("Continue")
                print(f"\nGemini: {final_response.text}")

    await client.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(example_usage())
