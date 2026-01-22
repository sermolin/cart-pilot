"""Tests for Merchant B webhook chaos functionality."""

import pytest
from unittest.mock import AsyncMock, patch

from app.chaos import ChaosController
from app.schemas import ChaosScenario, WebhookEventType
from app.webhooks import WebhookSender


class TestWebhookSender:
    """Tests for WebhookSender with chaos mode."""

    @pytest.fixture
    def webhook_sender(self):
        """Create a webhook sender for testing."""
        return WebhookSender(
            webhook_url="http://localhost:8000/webhooks/merchant",
            webhook_secret="test-secret",
            merchant_id="merchant-b",
        )

    @pytest.fixture
    def chaos_controller(self):
        """Create a chaos controller for testing."""
        return ChaosController()

    def test_build_payload(self, webhook_sender: WebhookSender):
        """Test building webhook payload."""
        payload = webhook_sender._build_payload(
            WebhookEventType.CHECKOUT_QUOTED,
            {"checkout_id": "test-123", "total": 1000},
        )
        
        assert payload.event_type == WebhookEventType.CHECKOUT_QUOTED
        assert payload.merchant_id == "merchant-b"
        assert payload.data["checkout_id"] == "test-123"

    def test_sign_payload(self, webhook_sender: WebhookSender):
        """Test payload signing."""
        signature = webhook_sender._sign_payload('{"test": "data"}')
        
        assert signature.startswith("sha256=")
        assert len(signature) > 10

    @pytest.mark.asyncio
    async def test_send_event_without_chaos(self, webhook_sender: WebhookSender):
        """Test sending event without chaos enabled."""
        with patch.object(webhook_sender, "_deliver_webhook", new_callable=AsyncMock) as mock_deliver:
            mock_deliver.return_value = True
            
            result = await webhook_sender.send_event(
                WebhookEventType.CHECKOUT_QUOTED,
                {"checkout_id": "test-123"},
            )
            
            assert result is True
            mock_deliver.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_webhook_chaos(
        self, webhook_sender: WebhookSender, chaos_controller: ChaosController
    ):
        """Test duplicate webhook chaos scenario."""
        webhook_sender.set_chaos_controller(chaos_controller)
        chaos_controller.enable_scenario(ChaosScenario.DUPLICATE_WEBHOOK)
        chaos_controller.config.duplicate_webhook_count = 3
        
        delivery_count = 0
        
        async def count_deliveries(*args, **kwargs):
            nonlocal delivery_count
            delivery_count += 1
            return True
        
        with patch.object(webhook_sender, "_deliver_webhook", side_effect=count_deliveries):
            # Force the scenario to trigger
            chaos_controller._rng.random = lambda: 0.5  # 50% < 70%, will trigger
            
            await webhook_sender.send_event(
                WebhookEventType.CHECKOUT_QUOTED,
                {"checkout_id": "test-123"},
            )
            
            # Should have sent 3 webhooks (1 original + 2 duplicates)
            assert delivery_count == 3

    @pytest.mark.asyncio
    async def test_out_of_order_webhook_chaos(
        self, webhook_sender: WebhookSender, chaos_controller: ChaosController
    ):
        """Test out of order webhook chaos scenario."""
        webhook_sender.set_chaos_controller(chaos_controller)
        chaos_controller.enable_scenario(ChaosScenario.OUT_OF_ORDER_WEBHOOK)
        
        # Force trigger
        chaos_controller._rng.random = lambda: 0.3  # 30% < 40%, will trigger
        
        with patch.object(webhook_sender, "_deliver_webhook", new_callable=AsyncMock) as mock_deliver:
            mock_deliver.return_value = True
            
            # Send event - should be queued
            await webhook_sender.send_event(
                WebhookEventType.CHECKOUT_QUOTED,
                {"checkout_id": "test-123"},
            )
            
            # Should not have delivered yet (queued)
            assert len(webhook_sender._pending_webhooks) == 1
            mock_deliver.assert_not_called()
            
            # Flush pending webhooks
            count = await webhook_sender.flush_pending_webhooks()
            
            assert count == 1
            mock_deliver.assert_called_once()
            assert len(webhook_sender._pending_webhooks) == 0

    @pytest.mark.asyncio
    async def test_flush_pending_webhooks_empty(self, webhook_sender: WebhookSender):
        """Test flushing when no pending webhooks."""
        count = await webhook_sender.flush_pending_webhooks()
        assert count == 0


class TestWebhookChaosIntegration:
    """Integration tests for webhook chaos via API."""

    def test_flush_webhooks_endpoint(self, client):
        """Test the flush webhooks endpoint."""
        response = client.post("/chaos/flush-webhooks")
        assert response.status_code == 200
        
        data = response.json()
        assert "flushed" in data


# Import client fixture from conftest
@pytest.fixture
def client():
    """Create test client."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.chaos import reset_chaos_controller
    from app.checkout import reset_checkout_store
    from app.products import reset_product_store
    from app.webhooks import reset_webhook_sender
    
    reset_product_store()
    reset_checkout_store()
    reset_chaos_controller()
    reset_webhook_sender()
    
    with TestClient(app) as client:
        yield client
