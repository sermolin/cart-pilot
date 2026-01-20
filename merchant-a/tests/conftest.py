"""Test fixtures for Merchant A tests."""

import pytest
from fastapi.testclient import TestClient

# Reset global stores before importing app
import app.products as products_module
import app.checkout as checkout_module
import app.webhooks as webhooks_module


@pytest.fixture(autouse=True)
def reset_stores():
    """Reset global stores before each test."""
    products_module._product_store = None
    checkout_module._checkout_store = None
    webhooks_module._webhook_sender = None
    yield
    products_module._product_store = None
    checkout_module._checkout_store = None
    webhooks_module._webhook_sender = None


@pytest.fixture
def client():
    """Create test client."""
    from app.main import app
    with TestClient(app) as client:
        yield client


@pytest.fixture
def product_store():
    """Create product store for testing."""
    from app.products import ProductStore
    return ProductStore(
        merchant_id="test-merchant",
        seed=42,
        products_per_category=3,
    )


@pytest.fixture
def checkout_store(product_store):
    """Create checkout store for testing."""
    from app.checkout import CheckoutStore
    return CheckoutStore(product_store=product_store)
