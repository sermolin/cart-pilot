"""CartPilot MCP Server.

Exposes CartPilot capabilities as MCP tools for AI agent interaction.
This is a thin adapter over the CartPilot REST API.

MCP Tools:
1. create_intent - Create purchase intent from text
2. list_offers - Get offers for an intent
3. get_offer_details - Get detailed offer information
4. request_approval - Initiate approval flow for a purchase
5. approve_purchase - Approve a pending purchase
6. get_order_status - Check order status
7. simulate_time - Advance order state for testing
8. trigger_chaos_case - Enable chaos scenarios for testing
"""

import asyncio
import json
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    TextContent,
    Tool,
)
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
import structlog


# ============================================================================
# Configuration
# ============================================================================


class Settings(BaseSettings):
    """MCP Server settings."""

    cartpilot_api_url: str = Field(
        default="http://cartpilot-api:8000",
        description="CartPilot API base URL",
    )
    cartpilot_api_key: str = Field(
        default="dev-api-key-change-in-production",
        description="API key for CartPilot authentication",
    )
    merchant_b_url: str = Field(
        default="http://merchant-b:8002",
        description="Merchant B base URL for chaos endpoints",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level",
    )

    model_config = {
        "env_file": ".env",
        "extra": "ignore",
    }


settings = Settings()

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(message)s",
    stream=sys.stderr,
)
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


# ============================================================================
# Tool Input Schemas
# ============================================================================


class CreateIntentInput(BaseModel):
    """Input schema for create_intent tool."""

    query: str = Field(
        ...,
        description="Natural language description of what to purchase. "
        "Example: 'I want to buy a wireless keyboard under $50'",
    )
    session_id: str | None = Field(
        None,
        description="Optional session ID for tracking the conversation.",
    )


class ListOffersInput(BaseModel):
    """Input schema for list_offers tool."""

    intent_id: str = Field(
        ...,
        description="The intent ID returned from create_intent.",
    )
    page: int = Field(
        default=1,
        ge=1,
        description="Page number for pagination.",
    )
    page_size: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Number of offers per page.",
    )


class GetOfferDetailsInput(BaseModel):
    """Input schema for get_offer_details tool."""

    offer_id: str = Field(
        ...,
        description="The offer ID returned from list_offers.",
    )


class RequestApprovalInput(BaseModel):
    """Input schema for request_approval tool."""

    offer_id: str = Field(
        ...,
        description="The offer ID to create a checkout from.",
    )
    items: list[dict[str, Any]] = Field(
        ...,
        description="List of items to purchase. Each item should have: "
        "product_id (required), variant_id (optional), quantity (required).",
    )
    customer_email: str | None = Field(
        None,
        description="Optional customer email for the receipt.",
    )


class ApprovePurchaseInput(BaseModel):
    """Input schema for approve_purchase tool."""

    checkout_id: str = Field(
        ...,
        description="The checkout ID returned from request_approval.",
    )
    approved_by: str = Field(
        default="user",
        description="Identifier of who is approving (e.g., 'user', 'agent').",
    )
    confirm: bool = Field(
        default=True,
        description="Whether to also confirm the purchase with the merchant.",
    )
    payment_method: str = Field(
        default="test_card",
        description="Payment method to use if confirming.",
    )


class GetOrderStatusInput(BaseModel):
    """Input schema for get_order_status tool."""

    order_id: str = Field(
        ...,
        description="The order ID to check status for.",
    )


class SimulateTimeInput(BaseModel):
    """Input schema for simulate_time tool."""

    order_id: str = Field(
        ...,
        description="The order ID to advance.",
    )
    steps: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Number of state transitions to make (1-5).",
    )


class TriggerChaosInput(BaseModel):
    """Input schema for trigger_chaos_case tool."""

    scenario: str = Field(
        ...,
        description="Chaos scenario name: 'price_change', 'out_of_stock', "
        "'duplicate_webhook', 'delayed_webhook', 'out_of_order_webhook', or 'all'.",
    )
    enable: bool = Field(
        default=True,
        description="Whether to enable (true) or disable (false) the scenario.",
    )


# ============================================================================
# MCP Server Implementation
# ============================================================================


def create_mcp_server() -> Server:
    """Create and configure the MCP server with all tools."""
    server = Server("cartpilot-mcp")

    # Lazy-load tools to avoid import issues
    _tools_instance = None

    async def get_tools():
        """Get or create the MCPTools instance."""
        nonlocal _tools_instance
        if _tools_instance is None:
            from app.api_client import CartPilotAPIClient, MerchantBChaosClient
            from app.tools import MCPTools

            api_client = CartPilotAPIClient(
                base_url=settings.cartpilot_api_url,
                api_key=settings.cartpilot_api_key,
            )
            chaos_client = MerchantBChaosClient(
                base_url=settings.merchant_b_url,
            )
            _tools_instance = MCPTools(
                api_client=api_client,
                chaos_client=chaos_client,
            )
        return _tools_instance

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List all available MCP tools."""
        return [
            Tool(
                name="create_intent",
                description=(
                    "Create a purchase intent from natural language. "
                    "This captures the user's purchase intention and returns an intent ID "
                    "that can be used to get offers from merchants."
                ),
                inputSchema=CreateIntentInput.model_json_schema(),
            ),
            Tool(
                name="list_offers",
                description=(
                    "Get offers from merchants for a purchase intent. "
                    "Returns a list of available products with prices and availability "
                    "from all enabled merchants."
                ),
                inputSchema=ListOffersInput.model_json_schema(),
            ),
            Tool(
                name="get_offer_details",
                description=(
                    "Get detailed information about a specific offer. "
                    "Returns complete product details including descriptions, images, "
                    "ratings, and exact pricing."
                ),
                inputSchema=GetOfferDetailsInput.model_json_schema(),
            ),
            Tool(
                name="request_approval",
                description=(
                    "Initiate the approval flow for a purchase. "
                    "Creates a checkout, gets a quote from the merchant, and requests "
                    "human approval. Returns a frozen receipt for review."
                ),
                inputSchema=RequestApprovalInput.model_json_schema(),
            ),
            Tool(
                name="approve_purchase",
                description=(
                    "Approve a pending purchase and optionally confirm it. "
                    "If confirm=true (default), the purchase is executed with the merchant "
                    "and an order is created."
                ),
                inputSchema=ApprovePurchaseInput.model_json_schema(),
            ),
            Tool(
                name="get_order_status",
                description=(
                    "Check the status of an order. "
                    "Returns current status, shipping information, tracking details, "
                    "and order timeline."
                ),
                inputSchema=GetOrderStatusInput.model_json_schema(),
            ),
            Tool(
                name="simulate_time",
                description=(
                    "Advance order state for testing purposes. "
                    "Simulates time passing to move an order through its lifecycle: "
                    "pending -> confirmed -> shipped -> delivered."
                ),
                inputSchema=SimulateTimeInput.model_json_schema(),
            ),
            Tool(
                name="trigger_chaos_case",
                description=(
                    "Enable or disable chaos scenarios for resilience testing. "
                    "Configures Merchant B to simulate edge cases like price changes, "
                    "out-of-stock, duplicate webhooks, etc."
                ),
                inputSchema=TriggerChaosInput.model_json_schema(),
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        """Handle tool invocation."""
        tools = await get_tools()

        logger.info("Tool called", tool=name, arguments=arguments)

        try:
            if name == "create_intent":
                input_data = CreateIntentInput(**arguments)
                result = await tools.create_intent(
                    query=input_data.query,
                    session_id=input_data.session_id,
                )
            elif name == "list_offers":
                input_data = ListOffersInput(**arguments)
                result = await tools.list_offers(
                    intent_id=input_data.intent_id,
                    page=input_data.page,
                    page_size=input_data.page_size,
                )
            elif name == "get_offer_details":
                input_data = GetOfferDetailsInput(**arguments)
                result = await tools.get_offer_details(
                    offer_id=input_data.offer_id,
                )
            elif name == "request_approval":
                input_data = RequestApprovalInput(**arguments)
                result = await tools.request_approval(
                    offer_id=input_data.offer_id,
                    items=input_data.items,
                    customer_email=input_data.customer_email,
                )
            elif name == "approve_purchase":
                input_data = ApprovePurchaseInput(**arguments)
                result = await tools.approve_purchase(
                    checkout_id=input_data.checkout_id,
                    approved_by=input_data.approved_by,
                    confirm=input_data.confirm,
                    payment_method=input_data.payment_method,
                )
            elif name == "get_order_status":
                input_data = GetOrderStatusInput(**arguments)
                result = await tools.get_order_status(
                    order_id=input_data.order_id,
                )
            elif name == "simulate_time":
                input_data = SimulateTimeInput(**arguments)
                result = await tools.simulate_time(
                    order_id=input_data.order_id,
                    steps=input_data.steps,
                )
            elif name == "trigger_chaos_case":
                input_data = TriggerChaosInput(**arguments)
                result = await tools.trigger_chaos_case(
                    scenario=input_data.scenario,
                    enable=input_data.enable,
                )
            else:
                result = {
                    "success": False,
                    "error": f"Unknown tool: {name}",
                }

            logger.info("Tool completed", tool=name, success=result.get("success"))

            return [
                TextContent(
                    type="text",
                    text=json.dumps(result, indent=2, default=str),
                )
            ]

        except Exception as e:
            logger.exception("Tool execution failed", tool=name)
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "success": False,
                            "error": f"Tool execution failed: {str(e)}",
                        },
                        indent=2,
                    ),
                )
            ]

    return server


async def run_server() -> None:
    """Run the MCP server using stdio transport."""
    logger.info(
        "Starting CartPilot MCP Server",
        cartpilot_api_url=settings.cartpilot_api_url,
        merchant_b_url=settings.merchant_b_url,
    )

    server = create_mcp_server()

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    """Run the MCP server.

    Entry point for the MCP server. Uses stdio transport for
    communication with AI agents.
    """
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
