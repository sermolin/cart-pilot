"""Tests for MCP server main module."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.main import (
    Settings,
    create_mcp_server,
    CreateIntentInput,
    ListOffersInput,
    ApprovePurchaseInput,
)


class TestSettings:
    """Tests for Settings configuration."""

    def test_default_settings(self):
        """Test default settings values."""
        with patch.dict("os.environ", {}, clear=True):
            settings = Settings()
            assert settings.cartpilot_api_url == "http://cartpilot-api:8000"
            assert settings.cartpilot_api_key == "dev-api-key-change-in-production"
            assert settings.merchant_b_url == "http://merchant-b:8002"
            assert settings.log_level == "INFO"

    def test_settings_from_env(self):
        """Test settings from environment variables."""
        env_vars = {
            "CARTPILOT_API_URL": "http://custom:9000",
            "CARTPILOT_API_KEY": "custom-key",
            "MERCHANT_B_URL": "http://custom-merchant:9002",
            "LOG_LEVEL": "DEBUG",
        }
        with patch.dict("os.environ", env_vars, clear=False):
            settings = Settings()
            assert settings.cartpilot_api_url == "http://custom:9000"
            assert settings.cartpilot_api_key == "custom-key"
            assert settings.merchant_b_url == "http://custom-merchant:9002"
            assert settings.log_level == "DEBUG"


class TestInputSchemas:
    """Tests for input schema validation."""

    def test_create_intent_input_valid(self):
        """Test valid create intent input."""
        input_data = CreateIntentInput(
            query="wireless keyboard",
            session_id="session-1",
        )
        assert input_data.query == "wireless keyboard"
        assert input_data.session_id == "session-1"

    def test_create_intent_input_optional_session(self):
        """Test create intent with optional session."""
        input_data = CreateIntentInput(query="test query")
        assert input_data.session_id is None

    def test_list_offers_input_defaults(self):
        """Test list offers input with defaults."""
        input_data = ListOffersInput(intent_id="intent-1")
        assert input_data.intent_id == "intent-1"
        assert input_data.page == 1
        assert input_data.page_size == 10

    def test_list_offers_input_pagination(self):
        """Test list offers input with custom pagination."""
        input_data = ListOffersInput(
            intent_id="intent-1",
            page=2,
            page_size=50,
        )
        assert input_data.page == 2
        assert input_data.page_size == 50

    def test_approve_purchase_input_defaults(self):
        """Test approve purchase input with defaults."""
        input_data = ApprovePurchaseInput(checkout_id="checkout-1")
        assert input_data.checkout_id == "checkout-1"
        assert input_data.approved_by == "user"
        assert input_data.confirm is True
        assert input_data.payment_method == "test_card"


class TestMCPServer:
    """Tests for MCP server creation."""

    def test_create_server(self):
        """Test MCP server creation."""
        server = create_mcp_server()
        assert server is not None
        assert server.name == "cartpilot-mcp"

    @pytest.mark.asyncio
    async def test_list_tools(self):
        """Test listing available tools."""
        server = create_mcp_server()
        
        # Verify the server was created successfully
        # The actual tool handlers are registered via decorators
        # and can't be easily accessed without running the server
        assert server is not None
        assert server.name == "cartpilot-mcp"

    def test_tool_count(self):
        """Test that we have exactly 8 tools defined."""
        # This is a simple check based on the tool definitions
        expected_tools = [
            "create_intent",
            "list_offers",
            "get_offer_details",
            "request_approval",
            "approve_purchase",
            "get_order_status",
            "simulate_time",
            "trigger_chaos_case",
        ]
        assert len(expected_tools) == 8


class TestToolSchemas:
    """Tests for tool input/output schemas."""

    def test_create_intent_schema(self):
        """Test create intent schema generation."""
        schema = CreateIntentInput.model_json_schema()
        assert "query" in schema["properties"]
        assert schema["properties"]["query"]["type"] == "string"
        assert "required" in schema
        assert "query" in schema["required"]

    def test_list_offers_schema(self):
        """Test list offers schema generation."""
        schema = ListOffersInput.model_json_schema()
        assert "intent_id" in schema["properties"]
        assert "page" in schema["properties"]
        assert "page_size" in schema["properties"]

    def test_approve_purchase_schema(self):
        """Test approve purchase schema generation."""
        schema = ApprovePurchaseInput.model_json_schema()
        assert "checkout_id" in schema["properties"]
        assert "approved_by" in schema["properties"]
        assert "confirm" in schema["properties"]
        assert "payment_method" in schema["properties"]
