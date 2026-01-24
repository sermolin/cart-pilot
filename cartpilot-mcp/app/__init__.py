"""CartPilot MCP Server.

Exposes CartPilot capabilities as MCP tools for AI agent interaction.

This package provides:
- MCP tools for purchase intent, offers, checkout, and order management
- Thin adapter layer over CartPilot REST API
- Integration with Merchant B chaos mode for testing

Tools:
1. create_intent - Create purchase intent from natural language
2. list_offers - Get offers from merchants
3. get_offer_details - Get detailed offer information
4. request_approval - Initiate approval flow
5. approve_purchase - Approve and confirm purchase
6. get_order_status - Check order status
7. simulate_time - Advance order state (testing)
8. trigger_chaos_case - Enable chaos scenarios (testing)
"""

__version__ = "1.0.0"
