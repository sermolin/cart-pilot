"""Tests for Order API endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.application.order_service import (
    AddressDTO,
    CustomerDTO,
    OrderItemDTO,
    get_order_service,
    reset_order_repository,
)
from app.domain.state_machines import OrderStatus
from app.main import app
from app.infrastructure.config import settings


@pytest.fixture
def auth_client() -> TestClient:
    """Create test client with valid API key authentication."""
    return TestClient(
        app,
        headers={"Authorization": f"Bearer {settings.cartpilot_api_key}"},
    )


@pytest.fixture(autouse=True)
def reset_repository():
    """Reset order repository before each test."""
    reset_order_repository()
    yield
    reset_order_repository()


@pytest.fixture
def sample_order_data():
    """Create sample order data."""
    return {
        "checkout_id": "chk_test123",
        "merchant_id": "merchant-a",
        "merchant_order_id": "merchant-order-123",
        "customer": CustomerDTO(
            email="test@example.com",
            name="Test Customer",
            phone="+1234567890",
        ),
        "shipping_address": AddressDTO(
            line1="123 Test Street",
            line2="Apt 4",
            city="Test City",
            state="CA",
            postal_code="12345",
            country="US",
        ),
        "billing_address": AddressDTO(
            line1="123 Test Street",
            city="Test City",
            state="CA",
            postal_code="12345",
            country="US",
        ),
        "items": [
            OrderItemDTO(
                product_id="prod-001",
                title="Test Product",
                quantity=2,
                unit_price_cents=1999,
                currency="USD",
                sku="SKU-001",
            ),
            OrderItemDTO(
                product_id="prod-002",
                title="Another Product",
                quantity=1,
                unit_price_cents=2999,
                currency="USD",
                sku="SKU-002",
            ),
        ],
        "subtotal_cents": 6997,
        "tax_cents": 560,
        "shipping_cents": 500,
        "total_cents": 8057,
        "currency": "USD",
    }


@pytest.fixture
async def created_order(sample_order_data):
    """Create an order for testing."""
    service = get_order_service()
    result = await service.create_order_from_checkout(**sample_order_data)
    assert result.success
    return result.order


class TestListOrders:
    """Tests for GET /orders endpoint."""

    def test_list_orders_empty(self, auth_client):
        """Test listing orders when none exist."""
        response = auth_client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []
        assert data["page"] == 1
        assert data["has_more"] is False

    @pytest.mark.asyncio
    async def test_list_orders_with_data(self, auth_client, sample_order_data):
        """Test listing orders with data."""
        # Create an order first
        service = get_order_service()
        await service.create_order_from_checkout(**sample_order_data)

        response = auth_client.get("/orders")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["merchant_id"] == "merchant-a"
        assert data["items"][0]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_list_orders_pagination(self, auth_client, sample_order_data):
        """Test order pagination."""
        service = get_order_service()

        # Create 5 orders
        for i in range(5):
            order_data = sample_order_data.copy()
            order_data["checkout_id"] = f"chk_test{i}"
            await service.create_order_from_checkout(**order_data)

        # Get first page
        response = auth_client.get("/orders?page=1&page_size=2")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["has_more"] is True

        # Get second page
        response = auth_client.get("/orders?page=2&page_size=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["page"] == 2

    @pytest.mark.asyncio
    async def test_list_orders_filter_by_status(self, auth_client, sample_order_data):
        """Test filtering orders by status."""
        service = get_order_service()

        # Create orders in different states
        result = await service.create_order_from_checkout(**sample_order_data)
        order_id = result.order.id

        # Confirm one order
        await service.confirm_order(order_id)

        # Filter by pending
        response = auth_client.get("/orders?status=pending")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

        # Filter by confirmed
        response = auth_client.get("/orders?status=confirmed")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1


class TestGetOrder:
    """Tests for GET /orders/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_order_success(self, auth_client, sample_order_data):
        """Test getting order details."""
        service = get_order_service()
        result = await service.create_order_from_checkout(**sample_order_data)
        order_id = result.order.id

        response = auth_client.get(f"/orders/{order_id}")
        assert response.status_code == 200
        data = response.json()

        assert data["id"] == order_id
        assert data["merchant_id"] == "merchant-a"
        assert data["status"] == "pending"
        assert data["customer"]["email"] == "test@example.com"
        assert data["shipping_address"]["city"] == "Test City"
        assert len(data["items"]) == 2
        assert data["total"]["amount"] == 8057
        assert len(data["status_history"]) == 1

    def test_get_order_not_found(self, auth_client):
        """Test getting non-existent order."""
        response = auth_client.get("/orders/nonexistent-order")
        assert response.status_code == 404
        data = response.json()
        assert data["error_code"] == "ORDER_NOT_FOUND"


class TestCancelOrder:
    """Tests for POST /orders/{id}/cancel endpoint."""

    @pytest.mark.asyncio
    async def test_cancel_pending_order(self, auth_client, sample_order_data):
        """Test cancelling a pending order."""
        service = get_order_service()
        result = await service.create_order_from_checkout(**sample_order_data)
        order_id = result.order.id

        response = auth_client.post(
            f"/orders/{order_id}/cancel",
            json={"reason": "Customer changed mind", "cancelled_by": "customer"},
        )
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "cancelled"
        assert data["cancelled_reason"] == "Customer changed mind"
        assert data["cancelled_by"] == "customer"
        assert data["cancelled_at"] is not None

    @pytest.mark.asyncio
    async def test_cancel_confirmed_order(self, auth_client, sample_order_data):
        """Test cancelling a confirmed order."""
        service = get_order_service()
        result = await service.create_order_from_checkout(**sample_order_data)
        order_id = result.order.id

        # Confirm first
        await service.confirm_order(order_id)

        response = auth_client.post(
            f"/orders/{order_id}/cancel",
            json={"reason": "Merchant request", "cancelled_by": "merchant"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_delivered_order_fails(self, auth_client, sample_order_data):
        """Test that delivered orders cannot be cancelled."""
        service = get_order_service()
        result = await service.create_order_from_checkout(**sample_order_data)
        order_id = result.order.id

        # Progress to delivered
        await service.confirm_order(order_id)
        await service.ship_order(order_id, tracking_number="TRACK123")
        await service.deliver_order(order_id)

        response = auth_client.post(
            f"/orders/{order_id}/cancel",
            json={"reason": "Too late", "cancelled_by": "customer"},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == "INVALID_TRANSITION"


class TestRefundOrder:
    """Tests for POST /orders/{id}/refund endpoint."""

    @pytest.mark.asyncio
    async def test_refund_delivered_order(self, auth_client, sample_order_data):
        """Test refunding a delivered order."""
        service = get_order_service()
        result = await service.create_order_from_checkout(**sample_order_data)
        order_id = result.order.id

        # Progress to delivered
        await service.confirm_order(order_id)
        await service.ship_order(order_id, tracking_number="TRACK123")
        await service.deliver_order(order_id)

        response = auth_client.post(
            f"/orders/{order_id}/refund",
            json={"reason": "Customer not satisfied"},
        )
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "refunded"
        assert data["refund_amount"]["amount"] == 8057  # Full refund
        assert data["refund_reason"] == "Customer not satisfied"

    @pytest.mark.asyncio
    async def test_partial_refund(self, auth_client, sample_order_data):
        """Test partial refund."""
        service = get_order_service()
        result = await service.create_order_from_checkout(**sample_order_data)
        order_id = result.order.id

        # Progress to delivered
        await service.confirm_order(order_id)
        await service.ship_order(order_id)
        await service.deliver_order(order_id)

        response = auth_client.post(
            f"/orders/{order_id}/refund",
            json={"refund_amount_cents": 3000, "reason": "Partial refund"},
        )
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "refunded"
        assert data["refund_amount"]["amount"] == 3000

    @pytest.mark.asyncio
    async def test_refund_pending_order_fails(self, auth_client, sample_order_data):
        """Test that pending orders cannot be refunded."""
        service = get_order_service()
        result = await service.create_order_from_checkout(**sample_order_data)
        order_id = result.order.id

        response = auth_client.post(
            f"/orders/{order_id}/refund",
            json={"reason": "Should fail"},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == "INVALID_TRANSITION"


class TestSimulateAdvance:
    """Tests for POST /orders/{id}/simulate-advance endpoint."""

    @pytest.mark.asyncio
    async def test_simulate_one_step(self, auth_client, sample_order_data):
        """Test advancing order by one step."""
        service = get_order_service()
        result = await service.create_order_from_checkout(**sample_order_data)
        order_id = result.order.id

        response = auth_client.post(
            f"/orders/{order_id}/simulate-advance",
            json={"steps": 1},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "confirmed"

    @pytest.mark.asyncio
    async def test_simulate_multiple_steps(self, auth_client, sample_order_data):
        """Test advancing order by multiple steps."""
        service = get_order_service()
        result = await service.create_order_from_checkout(**sample_order_data)
        order_id = result.order.id

        response = auth_client.post(
            f"/orders/{order_id}/simulate-advance",
            json={"steps": 3},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "delivered"
        assert data["shipped_at"] is not None
        assert data["delivered_at"] is not None
        assert data["tracking_number"] is not None

    @pytest.mark.asyncio
    async def test_simulate_max_steps_capped(self, auth_client, sample_order_data):
        """Test that simulation stops at terminal state."""
        service = get_order_service()
        result = await service.create_order_from_checkout(**sample_order_data)
        order_id = result.order.id

        # Already advance to delivered
        await service.confirm_order(order_id)
        await service.ship_order(order_id)
        await service.deliver_order(order_id)

        # Try to advance further
        response = auth_client.post(
            f"/orders/{order_id}/simulate-advance",
            json={"steps": 1},
        )
        assert response.status_code == 200
        data = response.json()
        # Should still be delivered (no change)
        assert data["status"] == "delivered"


class TestOrderStatusHistory:
    """Tests for order status history tracking."""

    @pytest.mark.asyncio
    async def test_status_history_tracked(self, auth_client, sample_order_data):
        """Test that status history is properly tracked."""
        service = get_order_service()
        result = await service.create_order_from_checkout(**sample_order_data)
        order_id = result.order.id

        # Progress through states
        await service.confirm_order(order_id, actor="merchant")
        await service.ship_order(order_id, tracking_number="TRACK123", carrier="FedEx")
        await service.deliver_order(order_id)

        response = auth_client.get(f"/orders/{order_id}")
        assert response.status_code == 200
        data = response.json()

        assert len(data["status_history"]) == 4  # created + 3 transitions

        # Check transitions
        history = data["status_history"]
        assert history[0]["to_status"] == "pending"
        assert history[1]["from_status"] == "pending"
        assert history[1]["to_status"] == "confirmed"
        assert history[2]["to_status"] == "shipped"
        assert history[3]["to_status"] == "delivered"
