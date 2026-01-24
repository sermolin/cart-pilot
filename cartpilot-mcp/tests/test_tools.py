"""Tests for MCP tools."""

from datetime import datetime, timezone

import pytest

from app.tools import MCPTools, format_price, format_error
from app.api_client import APIError, APIResponse
from tests.conftest import make_success_response, make_error_response


class TestFormatHelpers:
    """Tests for formatting helper functions."""

    def test_format_price_usd(self):
        """Test USD price formatting."""
        assert format_price(1999, "USD") == "19.99 USD"
        assert format_price(100, "USD") == "1.00 USD"
        assert format_price(0, "USD") == "0.00 USD"

    def test_format_price_eur(self):
        """Test EUR price formatting."""
        assert format_price(2500, "EUR") == "25.00 EUR"

    def test_format_error(self):
        """Test error formatting."""
        response = make_error_response("TEST_ERROR", "Test message")
        assert format_error(response) == "Error [TEST_ERROR]: Test message"

    def test_format_error_no_error(self):
        """Test error formatting with no error."""
        response = APIResponse(success=False, error=None)
        assert format_error(response) == "Unknown error occurred"


class TestCreateIntent:
    """Tests for create_intent tool."""

    @pytest.mark.asyncio
    async def test_create_intent_success(self, mcp_tools, mock_api_client):
        """Test successful intent creation."""
        mock_api_client.create_intent.return_value = make_success_response({
            "id": "intent-123",
            "query": "wireless keyboard",
            "session_id": "session-1",
            "created_at": "2024-01-15T10:00:00Z",
        })

        result = await mcp_tools.create_intent(
            query="wireless keyboard",
            session_id="session-1",
        )

        assert result["success"] is True
        assert result["intent_id"] == "intent-123"
        assert result["query"] == "wireless keyboard"
        assert "list_offers" in result["message"]

        mock_api_client.create_intent.assert_called_once_with(
            query="wireless keyboard",
            session_id="session-1",
        )

    @pytest.mark.asyncio
    async def test_create_intent_error(self, mcp_tools, mock_api_client):
        """Test intent creation failure."""
        mock_api_client.create_intent.return_value = make_error_response(
            "VALIDATION_ERROR",
            "Query is required",
        )

        result = await mcp_tools.create_intent(query="")

        assert result["success"] is False
        assert "VALIDATION_ERROR" in result["error"]


class TestListOffers:
    """Tests for list_offers tool."""

    @pytest.mark.asyncio
    async def test_list_offers_success(self, mcp_tools, mock_api_client):
        """Test successful offers listing."""
        mock_api_client.get_intent_offers.return_value = make_success_response({
            "items": [
                {
                    "id": "offer-1",
                    "merchant_id": "merchant-a",
                    "item_count": 5,
                    "items": [
                        {
                            "product_id": "prod-1",
                            "title": "Wireless Keyboard",
                            "brand": "Acme",
                            "price": {"amount": 4999, "currency": "USD"},
                            "quantity_available": 10,
                        },
                    ],
                    "lowest_price": {"amount": 2999, "currency": "USD"},
                    "highest_price": {"amount": 7999, "currency": "USD"},
                    "is_expired": False,
                },
            ],
            "total": 1,
            "page": 1,
            "has_more": False,
        })

        result = await mcp_tools.list_offers(intent_id="intent-123")

        assert result["success"] is True
        assert result["intent_id"] == "intent-123"
        assert len(result["offers"]) == 1
        assert result["offers"][0]["offer_id"] == "offer-1"
        assert result["offers"][0]["merchant_id"] == "merchant-a"
        assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_list_offers_not_found(self, mcp_tools, mock_api_client):
        """Test offers listing for non-existent intent."""
        mock_api_client.get_intent_offers.return_value = make_error_response(
            "INTENT_NOT_FOUND",
            "Intent not found",
            status_code=404,
        )

        result = await mcp_tools.list_offers(intent_id="bad-id")

        assert result["success"] is False
        assert "INTENT_NOT_FOUND" in result["error"]


class TestGetOfferDetails:
    """Tests for get_offer_details tool."""

    @pytest.mark.asyncio
    async def test_get_offer_details_success(self, mcp_tools, mock_api_client):
        """Test successful offer details retrieval."""
        mock_api_client.get_offer.return_value = make_success_response({
            "id": "offer-1",
            "intent_id": "intent-123",
            "merchant_id": "merchant-a",
            "items": [
                {
                    "product_id": "prod-1",
                    "variant_id": None,
                    "sku": "KB-001",
                    "title": "Wireless Keyboard",
                    "description": "A great keyboard",
                    "brand": "Acme",
                    "category_path": "Electronics > Keyboards",
                    "price": {"amount": 4999, "currency": "USD"},
                    "quantity_available": 10,
                    "rating": 4.5,
                    "review_count": 120,
                    "image_url": "https://example.com/kb.jpg",
                },
            ],
            "item_count": 1,
            "lowest_price": {"amount": 4999, "currency": "USD"},
            "highest_price": {"amount": 4999, "currency": "USD"},
            "expires_at": None,
            "is_expired": False,
        })

        result = await mcp_tools.get_offer_details(offer_id="offer-1")

        assert result["success"] is True
        assert result["offer_id"] == "offer-1"
        assert result["merchant_id"] == "merchant-a"
        assert len(result["items"]) == 1
        assert result["items"][0]["title"] == "Wireless Keyboard"
        assert result["items"][0]["price"]["formatted"] == "49.99 USD"


class TestRequestApproval:
    """Tests for request_approval tool."""

    @pytest.mark.asyncio
    async def test_request_approval_success(self, mcp_tools, mock_api_client):
        """Test successful approval request."""
        # Mock create checkout
        mock_api_client.create_checkout.return_value = make_success_response({
            "id": "checkout-1",
            "status": "created",
        })

        # Mock quote checkout
        mock_api_client.quote_checkout.return_value = make_success_response({
            "id": "checkout-1",
            "status": "quoted",
        })

        # Mock request approval
        mock_api_client.request_approval.return_value = make_success_response({
            "id": "checkout-1",
            "status": "awaiting_approval",
            "merchant_id": "merchant-a",
            "items": [
                {
                    "title": "Wireless Keyboard",
                    "quantity": 1,
                    "unit_price": {"amount": 4999, "currency": "USD"},
                    "line_total": {"amount": 4999, "currency": "USD"},
                },
            ],
            "subtotal": {"amount": 4999, "currency": "USD"},
            "tax": {"amount": 400, "currency": "USD"},
            "shipping": {"amount": 500, "currency": "USD"},
            "total": {"amount": 5899, "currency": "USD"},
            "frozen_receipt": {"hash": "abc123"},
            "expires_at": None,
        })

        result = await mcp_tools.request_approval(
            offer_id="offer-1",
            items=[{"product_id": "prod-1", "quantity": 1}],
        )

        assert result["success"] is True
        assert result["checkout_id"] == "checkout-1"
        assert result["status"] == "awaiting_approval"
        assert "approve_purchase" in result["message"]

    @pytest.mark.asyncio
    async def test_request_approval_checkout_failed(self, mcp_tools, mock_api_client):
        """Test approval request when checkout creation fails."""
        mock_api_client.create_checkout.return_value = make_error_response(
            "OFFER_NOT_FOUND",
            "Offer not found",
            status_code=404,
        )

        result = await mcp_tools.request_approval(
            offer_id="bad-offer",
            items=[{"product_id": "prod-1", "quantity": 1}],
        )

        assert result["success"] is False
        assert result["step"] == "create_checkout"


class TestApprovePurchase:
    """Tests for approve_purchase tool."""

    @pytest.mark.asyncio
    async def test_approve_and_confirm_success(self, mcp_tools, mock_api_client):
        """Test successful approval and confirmation."""
        # Mock approve
        mock_api_client.approve_checkout.return_value = make_success_response({
            "id": "checkout-1",
            "status": "approved",
            "approved_by": "user",
            "approved_at": "2024-01-15T10:00:00Z",
        })

        # Mock confirm
        mock_api_client.confirm_checkout.return_value = make_success_response({
            "checkout_id": "checkout-1",
            "order_id": "order-1",
            "merchant_order_id": "MO-123",
            "status": "confirmed",
            "total": {"amount": 5899, "currency": "USD"},
            "confirmed_at": "2024-01-15T10:01:00Z",
        })

        result = await mcp_tools.approve_purchase(
            checkout_id="checkout-1",
            approved_by="user",
            confirm=True,
        )

        assert result["success"] is True
        assert result["order_id"] == "order-1"
        assert result["status"] == "confirmed"
        assert "confirmed" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_approve_only(self, mcp_tools, mock_api_client):
        """Test approval without confirmation."""
        mock_api_client.approve_checkout.return_value = make_success_response({
            "id": "checkout-1",
            "status": "approved",
            "approved_by": "user",
            "approved_at": "2024-01-15T10:00:00Z",
        })

        result = await mcp_tools.approve_purchase(
            checkout_id="checkout-1",
            approved_by="user",
            confirm=False,
        )

        assert result["success"] is True
        assert result["status"] == "approved"
        mock_api_client.confirm_checkout.assert_not_called()

    @pytest.mark.asyncio
    async def test_approve_reapproval_required(self, mcp_tools, mock_api_client):
        """Test approval when price changed."""
        mock_api_client.approve_checkout.return_value = make_error_response(
            "REAPPROVAL_REQUIRED",
            "Price has changed",
            status_code=409,
        )

        result = await mcp_tools.approve_purchase(
            checkout_id="checkout-1",
            approved_by="user",
        )

        assert result["success"] is False
        assert result["reapproval_required"] is True


class TestGetOrderStatus:
    """Tests for get_order_status tool."""

    @pytest.mark.asyncio
    async def test_get_order_status_success(self, mcp_tools, mock_api_client):
        """Test successful order status retrieval."""
        mock_api_client.get_order.return_value = make_success_response({
            "id": "order-1",
            "checkout_id": "checkout-1",
            "merchant_id": "merchant-a",
            "merchant_order_id": "MO-123",
            "status": "shipped",
            "items": [
                {
                    "product_id": "prod-1",
                    "title": "Wireless Keyboard",
                    "quantity": 1,
                    "unit_price": {"amount": 4999, "currency": "USD"},
                },
            ],
            "total": {"amount": 5899, "currency": "USD"},
            "tracking_number": "1Z999AA10123456784",
            "carrier": "UPS",
            "created_at": "2024-01-15T10:00:00Z",
            "confirmed_at": "2024-01-15T10:01:00Z",
            "shipped_at": "2024-01-16T08:00:00Z",
        })

        result = await mcp_tools.get_order_status(order_id="order-1")

        assert result["success"] is True
        assert result["order_id"] == "order-1"
        assert result["status"] == "shipped"
        assert result["shipping"]["tracking_number"] == "1Z999AA10123456784"
        assert "shipped" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_get_order_status_not_found(self, mcp_tools, mock_api_client):
        """Test order status for non-existent order."""
        mock_api_client.get_order.return_value = make_error_response(
            "ORDER_NOT_FOUND",
            "Order not found",
            status_code=404,
        )

        result = await mcp_tools.get_order_status(order_id="bad-id")

        assert result["success"] is False
        assert "ORDER_NOT_FOUND" in result["error"]


class TestSimulateTime:
    """Tests for simulate_time tool."""

    @pytest.mark.asyncio
    async def test_simulate_time_success(self, mcp_tools, mock_api_client):
        """Test successful time simulation."""
        mock_api_client.simulate_advance_order.return_value = make_success_response({
            "id": "order-1",
            "status": "shipped",
            "total": {"amount": 5899, "currency": "USD"},
        })

        result = await mcp_tools.simulate_time(order_id="order-1", steps=1)

        assert result["success"] is True
        assert result["order_id"] == "order-1"
        assert result["new_status"] == "shipped"
        assert result["steps_advanced"] == 1

    @pytest.mark.asyncio
    async def test_simulate_time_error(self, mcp_tools, mock_api_client):
        """Test time simulation failure."""
        mock_api_client.simulate_advance_order.return_value = make_error_response(
            "INVALID_STATE",
            "Cannot advance delivered order",
        )

        result = await mcp_tools.simulate_time(order_id="order-1", steps=1)

        assert result["success"] is False
        assert "INVALID_STATE" in result["error"]


class TestTriggerChaosCase:
    """Tests for trigger_chaos_case tool."""

    @pytest.mark.asyncio
    async def test_trigger_chaos_enable(self, mcp_tools, mock_chaos_client):
        """Test enabling a chaos scenario."""
        mock_chaos_client.enable_scenario.return_value = make_success_response({
            "enabled": True,
            "scenarios": {
                "price_change": True,
                "out_of_stock": False,
            },
            "price_change_percent": 15,
            "out_of_stock_probability": 0.3,
            "duplicate_webhook_count": 3,
            "webhook_delay_seconds": 5.0,
        })

        result = await mcp_tools.trigger_chaos_case(
            scenario="price_change",
            enable=True,
        )

        assert result["success"] is True
        assert result["chaos_enabled"] is True
        assert result["action"] == "enabled"
        assert "price_change" in result["enabled_scenarios"]

    @pytest.mark.asyncio
    async def test_trigger_chaos_disable_all(self, mcp_tools, mock_chaos_client):
        """Test disabling all chaos scenarios."""
        mock_chaos_client.disable_all.return_value = make_success_response({
            "enabled": False,
            "scenarios": {
                "price_change": False,
                "out_of_stock": False,
            },
            "price_change_percent": 15,
            "out_of_stock_probability": 0.3,
            "duplicate_webhook_count": 3,
            "webhook_delay_seconds": 5.0,
        })

        result = await mcp_tools.trigger_chaos_case(
            scenario="all",
            enable=False,
        )

        assert result["success"] is True
        assert result["chaos_enabled"] is False
        assert result["action"] == "disabled"

    @pytest.mark.asyncio
    async def test_trigger_chaos_invalid_scenario(self, mcp_tools, mock_chaos_client):
        """Test triggering with invalid scenario."""
        result = await mcp_tools.trigger_chaos_case(
            scenario="invalid_scenario",
            enable=True,
        )

        assert result["success"] is False
        assert "Invalid scenario" in result["error"]

    @pytest.mark.asyncio
    async def test_trigger_chaos_no_client(self):
        """Test triggering chaos when client not configured."""
        from unittest.mock import MagicMock
        
        tools = MCPTools(
            api_client=MagicMock(),
            chaos_client=None,
        )

        result = await tools.trigger_chaos_case(
            scenario="price_change",
            enable=True,
        )

        assert result["success"] is False
        assert "not configured" in result["error"]
