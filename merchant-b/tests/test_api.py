"""Tests for Merchant B API endpoints."""

import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Tests for health endpoints."""

    def test_health_check(self, client: TestClient):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "merchant-b"
        assert data["ucp_version"] == "1.0.0"
        assert "chaos_enabled" in data

    def test_stats(self, client: TestClient):
        """Test stats endpoint."""
        response = client.get("/stats")
        assert response.status_code == 200
        
        data = response.json()
        assert data["merchant_id"] == "merchant-b"
        assert "product_count" in data
        assert "checkout_count" in data
        assert "chaos_event_count" in data


class TestProductEndpoints:
    """Tests for product endpoints."""

    def test_list_products(self, client: TestClient):
        """Test listing products."""
        response = client.get("/products")
        assert response.status_code == 200
        
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert len(data["items"]) > 0

    def test_list_products_with_pagination(self, client: TestClient):
        """Test product pagination."""
        response = client.get("/products", params={"page": 1, "page_size": 5})
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["items"]) <= 5
        assert data["page"] == 1
        assert data["page_size"] == 5

    def test_list_products_with_filters(self, client: TestClient):
        """Test product filtering."""
        response = client.get("/products", params={"in_stock": True})
        assert response.status_code == 200
        
        data = response.json()
        for product in data["items"]:
            assert product["in_stock"] is True

    def test_get_product(self, client: TestClient, sample_product_id: str):
        """Test getting a single product."""
        response = client.get(f"/products/{sample_product_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["id"] == sample_product_id

    def test_get_product_not_found(self, client: TestClient):
        """Test getting non-existent product."""
        response = client.get("/products/nonexistent")
        assert response.status_code == 404
        
        data = response.json()
        assert data["error_code"] == "PRODUCT_NOT_FOUND"


class TestCheckoutEndpoints:
    """Tests for checkout endpoints."""

    def test_create_quote(self, client: TestClient, sample_quote_request: dict):
        """Test creating a quote."""
        response = client.post("/checkout/quote", json=sample_quote_request)
        assert response.status_code == 201
        
        data = response.json()
        assert "id" in data
        assert data["status"] == "quoted"
        assert len(data["items"]) == 1
        assert "total" in data
        assert "receipt_hash" in data

    def test_create_quote_idempotency(self, client: TestClient, sample_quote_request: dict):
        """Test quote idempotency."""
        sample_quote_request["idempotency_key"] = "test-key-123"
        
        response1 = client.post("/checkout/quote", json=sample_quote_request)
        assert response1.status_code == 201
        
        response2 = client.post("/checkout/quote", json=sample_quote_request)
        assert response2.status_code == 201
        
        assert response1.json()["id"] == response2.json()["id"]

    def test_get_checkout(self, client: TestClient, sample_quote_request: dict):
        """Test getting a checkout."""
        # Create quote first
        response = client.post("/checkout/quote", json=sample_quote_request)
        checkout_id = response.json()["id"]
        
        # Get checkout
        response = client.get(f"/checkout/{checkout_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["id"] == checkout_id

    def test_get_checkout_not_found(self, client: TestClient):
        """Test getting non-existent checkout."""
        response = client.get("/checkout/nonexistent")
        assert response.status_code == 404

    def test_confirm_checkout(self, client: TestClient, sample_quote_request: dict):
        """Test confirming a checkout (happy path, no chaos)."""
        # Make sure chaos is disabled
        client.post("/chaos/disable")
        
        # Create quote
        response = client.post("/checkout/quote", json=sample_quote_request)
        checkout_id = response.json()["id"]
        
        # Confirm checkout
        response = client.post(
            f"/checkout/{checkout_id}/confirm",
            json={"payment_method": "test_card"},
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "confirmed"
        assert "merchant_order_id" in data

    def test_confirm_checkout_not_found(self, client: TestClient):
        """Test confirming non-existent checkout."""
        response = client.post(
            "/checkout/nonexistent/confirm",
            json={"payment_method": "test_card"},
        )
        assert response.status_code == 404
