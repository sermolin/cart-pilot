"""Pytest configuration and fixtures for MCP server tests."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from app.api_client import APIResponse, CartPilotAPIClient, MerchantBChaosClient
from app.tools import MCPTools


@pytest.fixture
def mock_api_client() -> MagicMock:
    """Create a mock CartPilot API client."""
    client = MagicMock(spec=CartPilotAPIClient)
    
    # Make all methods async
    client.create_intent = AsyncMock()
    client.get_intent = AsyncMock()
    client.get_intent_offers = AsyncMock()
    client.get_offer = AsyncMock()
    client.create_checkout = AsyncMock()
    client.get_checkout = AsyncMock()
    client.quote_checkout = AsyncMock()
    client.request_approval = AsyncMock()
    client.approve_checkout = AsyncMock()
    client.confirm_checkout = AsyncMock()
    client.get_order = AsyncMock()
    client.list_orders = AsyncMock()
    client.simulate_advance_order = AsyncMock()
    client.close = AsyncMock()
    
    return client


@pytest.fixture
def mock_chaos_client() -> MagicMock:
    """Create a mock Merchant B chaos client."""
    client = MagicMock(spec=MerchantBChaosClient)
    
    client.get_chaos_config = AsyncMock()
    client.configure_chaos = AsyncMock()
    client.enable_scenario = AsyncMock()
    client.disable_scenario = AsyncMock()
    client.enable_all = AsyncMock()
    client.disable_all = AsyncMock()
    client.reset = AsyncMock()
    client.get_events = AsyncMock()
    client.close = AsyncMock()
    
    return client


@pytest_asyncio.fixture
async def mcp_tools(
    mock_api_client: MagicMock,
    mock_chaos_client: MagicMock,
) -> MCPTools:
    """Create MCPTools instance with mocked clients."""
    return MCPTools(
        api_client=mock_api_client,
        chaos_client=mock_chaos_client,
    )


def make_success_response(data: dict) -> APIResponse:
    """Create a successful API response."""
    return APIResponse(success=True, data=data)


def make_error_response(
    error_code: str,
    message: str,
    status_code: int = 400,
) -> APIResponse:
    """Create an error API response."""
    from app.api_client import APIError
    
    return APIResponse(
        success=False,
        error=APIError(
            error_code=error_code,
            message=message,
            status_code=status_code,
        ),
    )
