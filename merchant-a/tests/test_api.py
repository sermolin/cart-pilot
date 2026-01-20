"""Tests for Merchant A API endpoints."""

import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health_check(self, client: TestClient):
        """Test health endpoint returns healthy status."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "merchant-a"
        assert data["ucp_version"] == "1.0.0"

    def test_stats(self, client: TestClient):
        """Test stats endpoint."""
        response = client.get("/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["product_count"] > 0
        assert "checkout_count" in data
        assert data["ucp_version"] == "1.0.0"


class TestProductEndpoints:
    """Tests for product API endpoints."""

    def test_list_products(self, client: TestClient):
        """Test listing products."""
        response = client.get("/products")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "has_more" in data
        assert len(data["items"]) > 0

    def test_list_products_pagination(self, client: TestClient):
        """Test product pagination."""
        response = client.get("/products?page=1&page_size=5")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 5
        assert data["page"] == 1
        assert data["page_size"] == 5

    def test_list_products_filter_by_brand(self, client: TestClient):
        """Test filtering by brand."""
        # First get a valid brand
        response = client.get("/products?page_size=1")
        brand = response.json()["items"][0]["brand"]

        response = client.get(f"/products?brand={brand}")

        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["brand"] == brand

    def test_list_products_filter_by_category(self, client: TestClient):
        """Test filtering by category."""
        response = client.get("/products?category_id=100")

        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["category_id"] == 100

    def test_list_products_price_range(self, client: TestClient):
        """Test price range filter."""
        response = client.get("/products?min_price=1000&max_price=10000")

        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["price"]["amount"] >= 1000
            assert item["price"]["amount"] <= 10000

    def test_list_products_sort_by_price(self, client: TestClient):
        """Test sorting by price."""
        response = client.get("/products?sort_by=price&sort_order=asc")

        assert response.status_code == 200
        data = response.json()
        prices = [item["price"]["amount"] for item in data["items"]]
        assert prices == sorted(prices)

    def test_list_products_sort_by_rating(self, client: TestClient):
        """Test sorting by rating."""
        response = client.get("/products?sort_by=rating&sort_order=desc")

        assert response.status_code == 200
        data = response.json()
        ratings = [item["rating"] for item in data["items"]]
        assert ratings == sorted(ratings, reverse=True)

    def test_list_products_search(self, client: TestClient):
        """Test search functionality."""
        response = client.get("/products?search=Premium")

        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert (
                "premium" in item["title"].lower()
                or "premium" in (item["description"] or "").lower()
            )

    def test_get_product(self, client: TestClient):
        """Test getting single product."""
        # First get a product ID
        response = client.get("/products?page_size=1")
        product_id = response.json()["items"][0]["id"]

        response = client.get(f"/products/{product_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == product_id
        assert "ucp_version" in data

    def test_get_product_not_found(self, client: TestClient):
        """Test getting non-existent product."""
        response = client.get("/products/non-existent-id")

        assert response.status_code == 404
        data = response.json()
        assert data["error_code"] == "PRODUCT_NOT_FOUND"


class TestCheckoutEndpoints:
    """Tests for checkout API endpoints."""

    def test_create_quote(self, client: TestClient):
        """Test creating a quote."""
        # Get a product ID
        response = client.get("/products?page_size=1")
        product_id = response.json()["items"][0]["id"]

        response = client.post(
            "/checkout/quote",
            json={
                "items": [{"product_id": product_id, "quantity": 2}],
                "customer_email": "test@example.com",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["status"] == "quoted"
        assert len(data["items"]) == 1
        assert data["items"][0]["quantity"] == 2
        assert data["customer_email"] == "test@example.com"
        assert data["receipt_hash"] is not None
        assert data["ucp_version"] == "1.0.0"

    def test_create_quote_multiple_items(self, client: TestClient):
        """Test quote with multiple items."""
        response = client.get("/products?page_size=3")
        products = response.json()["items"]

        items = [{"product_id": p["id"], "quantity": 1} for p in products]

        response = client.post(
            "/checkout/quote",
            json={"items": items},
        )

        assert response.status_code == 201
        data = response.json()
        assert len(data["items"]) == 3

    def test_create_quote_idempotency(self, client: TestClient):
        """Test idempotent quote creation."""
        response = client.get("/products?page_size=1")
        product_id = response.json()["items"][0]["id"]

        response1 = client.post(
            "/checkout/quote",
            json={
                "items": [{"product_id": product_id, "quantity": 1}],
                "idempotency_key": "test-idempotency-key",
            },
        )
        response2 = client.post(
            "/checkout/quote",
            json={
                "items": [{"product_id": product_id, "quantity": 1}],
                "idempotency_key": "test-idempotency-key",
            },
        )

        assert response1.status_code == 201
        assert response2.status_code == 201
        assert response1.json()["id"] == response2.json()["id"]

    def test_create_quote_product_not_found(self, client: TestClient):
        """Test quote with non-existent product."""
        response = client.post(
            "/checkout/quote",
            json={"items": [{"product_id": "non-existent", "quantity": 1}]},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == "QUOTE_FAILED"

    def test_create_quote_empty_items(self, client: TestClient):
        """Test quote with empty items list."""
        response = client.post(
            "/checkout/quote",
            json={"items": []},
        )

        assert response.status_code == 422  # Validation error

    def test_get_checkout(self, client: TestClient):
        """Test getting checkout status."""
        # Create a quote first
        response = client.get("/products?page_size=1")
        product_id = response.json()["items"][0]["id"]

        response = client.post(
            "/checkout/quote",
            json={"items": [{"product_id": product_id, "quantity": 1}]},
        )
        checkout_id = response.json()["id"]

        response = client.get(f"/checkout/{checkout_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == checkout_id
        assert data["status"] == "quoted"

    def test_get_checkout_not_found(self, client: TestClient):
        """Test getting non-existent checkout."""
        response = client.get("/checkout/non-existent-id")

        assert response.status_code == 404
        data = response.json()
        assert data["error_code"] == "CHECKOUT_NOT_FOUND"

    def test_confirm_checkout(self, client: TestClient):
        """Test confirming checkout."""
        # Create a quote first
        response = client.get("/products?page_size=1")
        product_id = response.json()["items"][0]["id"]

        response = client.post(
            "/checkout/quote",
            json={"items": [{"product_id": product_id, "quantity": 1}]},
        )
        checkout_id = response.json()["id"]

        response = client.post(
            f"/checkout/{checkout_id}/confirm",
            json={"payment_method": "test_card"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["checkout_id"] == checkout_id
        assert data["merchant_order_id"].startswith("ORD-")
        assert data["status"] == "confirmed"
        assert data["ucp_version"] == "1.0.0"

    def test_confirm_checkout_idempotent(self, client: TestClient):
        """Test that confirmation is idempotent."""
        response = client.get("/products?page_size=1")
        product_id = response.json()["items"][0]["id"]

        response = client.post(
            "/checkout/quote",
            json={"items": [{"product_id": product_id, "quantity": 1}]},
        )
        checkout_id = response.json()["id"]

        response1 = client.post(
            f"/checkout/{checkout_id}/confirm",
            json={"payment_method": "test_card"},
        )
        response2 = client.post(
            f"/checkout/{checkout_id}/confirm",
            json={"payment_method": "test_card"},
        )

        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response1.json()["merchant_order_id"] == response2.json()["merchant_order_id"]

    def test_confirm_checkout_not_found(self, client: TestClient):
        """Test confirming non-existent checkout."""
        response = client.post(
            "/checkout/non-existent/confirm",
            json={"payment_method": "test_card"},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["error_code"] == "CHECKOUT_NOT_FOUND"


class TestHappyPathFlow:
    """Test complete happy path checkout flow."""

    def test_full_checkout_flow(self, client: TestClient):
        """Test complete checkout flow: browse -> quote -> confirm."""
        # 1. Browse products
        response = client.get("/products")
        assert response.status_code == 200
        products = response.json()["items"]
        assert len(products) > 0

        # 2. Get product details
        product_id = products[0]["id"]
        response = client.get(f"/products/{product_id}")
        assert response.status_code == 200
        product = response.json()
        assert product["in_stock"] is True

        # 3. Create quote
        response = client.post(
            "/checkout/quote",
            json={
                "items": [{"product_id": product_id, "quantity": 2}],
                "customer_email": "customer@example.com",
            },
        )
        assert response.status_code == 201
        checkout = response.json()
        checkout_id = checkout["id"]
        assert checkout["status"] == "quoted"

        # 4. Verify quote
        response = client.get(f"/checkout/{checkout_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "quoted"

        # 5. Confirm checkout
        response = client.post(
            f"/checkout/{checkout_id}/confirm",
            json={"payment_method": "test_card"},
        )
        assert response.status_code == 200
        confirmation = response.json()
        assert confirmation["status"] == "confirmed"
        assert confirmation["merchant_order_id"].startswith("ORD-")

        # 6. Verify confirmation
        response = client.get(f"/checkout/{checkout_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"
