"""Pytest fixtures for Merchant B tests."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.chaos import get_chaos_controller, reset_chaos_controller
from app.checkout import get_checkout_store, reset_checkout_store
from app.products import get_product_store, reset_product_store
from app.webhooks import reset_webhook_sender


@pytest.fixture(autouse=True)
def reset_stores():
    """Reset all stores before each test."""
    reset_product_store()
    reset_checkout_store()
    reset_chaos_controller()
    reset_webhook_sender()
    yield
    reset_product_store()
    reset_checkout_store()
    reset_chaos_controller()
    reset_webhook_sender()


@pytest.fixture
def client():
    """Create test client."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
def product_store():
    """Get product store instance."""
    return get_product_store()


@pytest.fixture
def checkout_store():
    """Get checkout store instance."""
    return get_checkout_store()


@pytest.fixture
def chaos_controller():
    """Get chaos controller instance."""
    return get_chaos_controller()


@pytest.fixture
def sample_product_id(product_store):
    """Get a sample product ID from the store."""
    return product_store.get_random_product_id()


@pytest.fixture
def sample_quote_request(sample_product_id):
    """Create a sample quote request."""
    return {
        "items": [
            {
                "product_id": sample_product_id,
                "quantity": 1,
            }
        ],
        "customer_email": "test@example.com",
    }
