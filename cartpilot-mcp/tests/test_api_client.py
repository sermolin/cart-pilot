"""Tests for API client."""

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from app.api_client import (
    APIError,
    APIResponse,
    CartPilotAPIClient,
    MerchantBChaosClient,
)


class TestCartPilotAPIClient:
    """Tests for CartPilot API client."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return CartPilotAPIClient(
            base_url="http://localhost:8000",
            api_key="test-key",
        )

    @pytest.mark.asyncio
    async def test_client_initialization(self, client):
        """Test client initialization."""
        assert client.base_url == "http://localhost:8000"
        assert client.api_key == "test-key"
        assert client._client is None

    @pytest.mark.asyncio
    async def test_create_intent_success(self, client):
        """Test successful intent creation."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "intent-123",
            "query": "test query",
        }

        with patch.object(
            client, "_get_client", new_callable=AsyncMock
        ) as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            result = await client.create_intent(query="test query")

            assert result.success is True
            assert result.data["id"] == "intent-123"

    @pytest.mark.asyncio
    async def test_create_intent_error(self, client):
        """Test intent creation with error."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error_code": "VALIDATION_ERROR",
            "message": "Query required",
        }

        with patch.object(
            client, "_get_client", new_callable=AsyncMock
        ) as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            result = await client.create_intent(query="")

            assert result.success is False
            assert result.error.error_code == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_request_timeout(self, client):
        """Test request timeout handling."""
        with patch.object(
            client, "_get_client", new_callable=AsyncMock
        ) as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(
                side_effect=httpx.TimeoutException("Connection timeout")
            )
            mock_get_client.return_value = mock_http_client

            result = await client.create_intent(query="test")

            assert result.success is False
            assert result.error.error_code == "TIMEOUT"
            assert result.error.status_code == 504

    @pytest.mark.asyncio
    async def test_request_error(self, client):
        """Test request error handling."""
        with patch.object(
            client, "_get_client", new_callable=AsyncMock
        ) as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(
                side_effect=httpx.RequestError("Connection failed")
            )
            mock_get_client.return_value = mock_http_client

            result = await client.create_intent(query="test")

            assert result.success is False
            assert result.error.error_code == "REQUEST_ERROR"

    @pytest.mark.asyncio
    async def test_get_offer(self, client):
        """Test getting offer details."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "offer-1",
            "merchant_id": "merchant-a",
            "items": [],
        }

        with patch.object(
            client, "_get_client", new_callable=AsyncMock
        ) as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            result = await client.get_offer("offer-1")

            assert result.success is True
            assert result.data["id"] == "offer-1"
            mock_http_client.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_client(self, client):
        """Test client cleanup."""
        mock_http_client = AsyncMock()
        client._client = mock_http_client

        await client.close()

        mock_http_client.aclose.assert_called_once()
        assert client._client is None


class TestMerchantBChaosClient:
    """Tests for Merchant B chaos client."""

    @pytest.fixture
    def client(self):
        """Create a test chaos client."""
        return MerchantBChaosClient(
            base_url="http://localhost:8002",
        )

    @pytest.mark.asyncio
    async def test_enable_scenario(self, client):
        """Test enabling a chaos scenario."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "enabled": True,
            "scenarios": {"price_change": True},
        }

        with patch.object(
            client, "_get_client", new_callable=AsyncMock
        ) as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            result = await client.enable_scenario("price_change")

            assert result.success is True
            assert result.data["enabled"] is True

    @pytest.mark.asyncio
    async def test_disable_all(self, client):
        """Test disabling all chaos scenarios."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "enabled": False,
            "scenarios": {},
        }

        with patch.object(
            client, "_get_client", new_callable=AsyncMock
        ) as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            result = await client.disable_all()

            assert result.success is True
            assert result.data["enabled"] is False

    @pytest.mark.asyncio
    async def test_configure_chaos(self, client):
        """Test configuring chaos parameters."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "enabled": True,
            "scenarios": {"price_change": True},
            "price_change_percent": 20,
        }

        with patch.object(
            client, "_get_client", new_callable=AsyncMock
        ) as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            result = await client.configure_chaos(
                scenarios={"price_change": True},
                price_change_percent=20,
            )

            assert result.success is True
            assert result.data["price_change_percent"] == 20


class TestAPIResponse:
    """Tests for APIResponse dataclass."""

    def test_success_response(self):
        """Test creating a success response."""
        response = APIResponse(
            success=True,
            data={"key": "value"},
        )
        assert response.success is True
        assert response.data == {"key": "value"}
        assert response.error is None

    def test_error_response(self):
        """Test creating an error response."""
        error = APIError(
            error_code="TEST_ERROR",
            message="Test message",
            status_code=400,
        )
        response = APIResponse(success=False, error=error)
        
        assert response.success is False
        assert response.error.error_code == "TEST_ERROR"
        assert response.error.message == "Test message"
        assert response.error.status_code == 400
