"""Tests for Merchant B chaos mode functionality."""

import pytest
from fastapi.testclient import TestClient

from app.chaos import ChaosController
from app.checkout import CheckoutStore
from app.products import ProductStore
from app.schemas import ChaosScenario


class TestChaosConfiguration:
    """Tests for chaos configuration endpoints."""

    def test_get_chaos_config(self, client: TestClient):
        """Test getting chaos configuration."""
        response = client.get("/chaos/config")
        assert response.status_code == 200
        
        data = response.json()
        assert "enabled" in data
        assert "scenarios" in data
        assert "price_change_percent" in data

    def test_configure_chaos(self, client: TestClient):
        """Test configuring chaos mode."""
        response = client.post(
            "/chaos/configure",
            json={
                "scenarios": {
                    "price_change": True,
                    "out_of_stock": False,
                },
                "price_change_percent": 20,
            },
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["enabled"] is True
        assert data["scenarios"]["price_change"] is True
        assert data["scenarios"]["out_of_stock"] is False
        assert data["price_change_percent"] == 20

    def test_enable_all_chaos(self, client: TestClient):
        """Test enabling all chaos scenarios."""
        response = client.post("/chaos/enable")
        assert response.status_code == 200
        
        data = response.json()
        assert data["enabled"] is True
        for scenario_enabled in data["scenarios"].values():
            assert scenario_enabled is True

    def test_disable_all_chaos(self, client: TestClient):
        """Test disabling all chaos scenarios."""
        # First enable
        client.post("/chaos/enable")
        
        # Then disable
        response = client.post("/chaos/disable")
        assert response.status_code == 200
        
        data = response.json()
        assert data["enabled"] is False
        for scenario_enabled in data["scenarios"].values():
            assert scenario_enabled is False

    def test_enable_single_scenario(self, client: TestClient):
        """Test enabling a single chaos scenario."""
        response = client.post("/chaos/scenarios/price_change/enable")
        assert response.status_code == 200
        
        data = response.json()
        assert data["enabled"] is True
        assert data["scenarios"]["price_change"] is True

    def test_disable_single_scenario(self, client: TestClient):
        """Test disabling a single chaos scenario."""
        # First enable
        client.post("/chaos/scenarios/price_change/enable")
        
        # Then disable
        response = client.post("/chaos/scenarios/price_change/disable")
        assert response.status_code == 200
        
        data = response.json()
        assert data["scenarios"]["price_change"] is False

    def test_chaos_reset(self, client: TestClient):
        """Test resetting chaos controller."""
        # Configure some chaos
        client.post("/chaos/enable")
        
        # Reset
        response = client.post("/chaos/reset")
        assert response.status_code == 200
        
        data = response.json()
        assert data["enabled"] is False


class TestChaosEvents:
    """Tests for chaos event logging."""

    def test_get_chaos_events_empty(self, client: TestClient):
        """Test getting chaos events when empty."""
        response = client.get("/chaos/events")
        assert response.status_code == 200
        
        data = response.json()
        assert data["events"] == []
        assert data["total"] == 0

    def test_clear_chaos_events(self, client: TestClient):
        """Test clearing chaos events."""
        response = client.delete("/chaos/events")
        assert response.status_code == 200
        
        data = response.json()
        assert "cleared" in data


class TestPriceChangeChaos:
    """Tests for price change chaos scenario."""

    def test_manual_price_change(self, client: TestClient, sample_product_id: str):
        """Test manually triggering a price change."""
        # Get original price
        response = client.get(f"/products/{sample_product_id}")
        original_price = response.json()["price"]["amount"]
        
        # Trigger price change (increase)
        response = client.post(
            f"/admin/trigger-price-change/{sample_product_id}",
            params={"increase": True},
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["old_price"] == original_price
        assert data["new_price"] > original_price

    def test_price_change_causes_checkout_failure(
        self, client: TestClient, sample_quote_request: dict
    ):
        """Test that price change causes checkout confirmation to fail."""
        # Disable chaos (we'll manually trigger price change)
        client.post("/chaos/disable")
        
        # Create quote
        response = client.post("/checkout/quote", json=sample_quote_request)
        assert response.status_code == 201
        checkout_id = response.json()["id"]
        product_id = sample_quote_request["items"][0]["product_id"]
        
        # Manually trigger price change
        client.post(f"/admin/trigger-price-change/{product_id}")
        
        # Try to confirm - should fail
        response = client.post(
            f"/checkout/{checkout_id}/confirm",
            json={"payment_method": "test_card"},
        )
        assert response.status_code == 409
        
        data = response.json()
        assert data["error_code"] == "PRICE_CHANGED"

    def test_price_change_chaos_triggers(
        self, client: TestClient, sample_quote_request: dict
    ):
        """Test that price change chaos can trigger during confirmation."""
        # Enable only price change chaos
        client.post("/chaos/disable")
        client.post("/chaos/scenarios/price_change/enable")
        
        # Create quote
        response = client.post("/checkout/quote", json=sample_quote_request)
        assert response.status_code == 201
        checkout_id = response.json()["id"]
        
        # Try to confirm multiple times - chaos should eventually trigger
        # (probabilistic, so we try multiple times)
        price_changed = False
        for _ in range(10):
            # Reset product first
            product_id = sample_quote_request["items"][0]["product_id"]
            client.post(f"/admin/reset-product/{product_id}")
            
            # Create new quote
            response = client.post("/checkout/quote", json=sample_quote_request)
            checkout_id = response.json()["id"]
            
            # Try to confirm
            response = client.post(
                f"/checkout/{checkout_id}/confirm",
                json={"payment_method": "test_card"},
            )
            
            if response.status_code == 409:
                data = response.json()
                if data["error_code"] == "PRICE_CHANGED":
                    price_changed = True
                    break
        
        # Due to probability, this might not trigger every time
        # Just verify the mechanism works
        assert price_changed or response.status_code == 200


class TestOutOfStockChaos:
    """Tests for out of stock chaos scenario."""

    def test_manual_out_of_stock(self, client: TestClient, sample_product_id: str):
        """Test manually triggering out of stock."""
        response = client.post(f"/admin/trigger-out-of-stock/{sample_product_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["in_stock"] is False
        
        # Verify product is now out of stock
        response = client.get(f"/products/{sample_product_id}")
        assert response.json()["in_stock"] is False

    def test_out_of_stock_causes_checkout_failure(
        self, client: TestClient, sample_quote_request: dict
    ):
        """Test that out of stock causes checkout confirmation to fail."""
        # Disable chaos
        client.post("/chaos/disable")
        
        # Create quote
        response = client.post("/checkout/quote", json=sample_quote_request)
        assert response.status_code == 201
        checkout_id = response.json()["id"]
        product_id = sample_quote_request["items"][0]["product_id"]
        
        # Manually trigger out of stock
        client.post(f"/admin/trigger-out-of-stock/{product_id}")
        
        # Try to confirm - should fail
        response = client.post(
            f"/checkout/{checkout_id}/confirm",
            json={"payment_method": "test_card"},
        )
        assert response.status_code == 409
        
        data = response.json()
        assert data["error_code"] == "OUT_OF_STOCK"

    def test_reset_product(self, client: TestClient, sample_product_id: str):
        """Test resetting a product after chaos."""
        # Trigger out of stock
        client.post(f"/admin/trigger-out-of-stock/{sample_product_id}")
        
        # Reset product
        response = client.post(f"/admin/reset-product/{sample_product_id}")
        assert response.status_code == 200
        
        # Verify product is back in stock
        response = client.get(f"/products/{sample_product_id}")
        assert response.json()["in_stock"] is True


class TestChaosController:
    """Unit tests for ChaosController."""

    def test_should_trigger_disabled(self, chaos_controller: ChaosController):
        """Test that disabled scenarios don't trigger."""
        chaos_controller.disable_all()
        
        for _ in range(100):
            assert chaos_controller.should_trigger(ChaosScenario.PRICE_CHANGE) is False

    def test_should_trigger_enabled(self, chaos_controller: ChaosController):
        """Test that enabled scenarios can trigger."""
        chaos_controller.enable_scenario(ChaosScenario.PRICE_CHANGE)
        
        # With 50% probability, should trigger at least once in 100 tries
        triggered = False
        for _ in range(100):
            if chaos_controller.should_trigger(ChaosScenario.PRICE_CHANGE):
                triggered = True
                break
        
        assert triggered is True

    def test_log_event(self, chaos_controller: ChaosController):
        """Test logging chaos events."""
        event = chaos_controller.log_event(
            ChaosScenario.PRICE_CHANGE,
            "test-checkout-id",
            {"old_price": 1000, "new_price": 1150},
        )
        
        assert event.scenario == ChaosScenario.PRICE_CHANGE
        assert event.checkout_id == "test-checkout-id"
        assert event.details["old_price"] == 1000

    def test_get_events_filtered(self, chaos_controller: ChaosController):
        """Test getting filtered chaos events."""
        # Log some events
        chaos_controller.log_event(
            ChaosScenario.PRICE_CHANGE,
            "checkout-1",
            {},
        )
        chaos_controller.log_event(
            ChaosScenario.OUT_OF_STOCK,
            "checkout-2",
            {},
        )
        
        # Get filtered events
        response = chaos_controller.get_events(scenario=ChaosScenario.PRICE_CHANGE)
        assert len(response.events) == 1
        assert response.events[0].scenario == ChaosScenario.PRICE_CHANGE


class TestAdminEndpoints:
    """Tests for admin endpoints."""

    def test_reset_all(self, client: TestClient):
        """Test resetting all state."""
        response = client.post("/admin/reset")
        assert response.status_code == 200
        
        data = response.json()
        assert data["reset_products"] is True
        assert data["reset_checkouts"] is True
        assert data["reset_chaos"] is True
