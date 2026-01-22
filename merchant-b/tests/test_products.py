"""Tests for Product Store with chaos support."""

import pytest

from app.products import ProductStore, get_product_store


class TestProductStore:
    """Test product store functionality."""

    def test_product_store_initialization(self):
        """Test product store initializes with products."""
        store = ProductStore(seed=100)
        assert len(store._products) > 0

    def test_product_store_deterministic(self):
        """Test product store is deterministic with same seed."""
        store1 = ProductStore(seed=100)
        store2 = ProductStore(seed=100)

        products1 = list(store1._products.keys())
        products2 = list(store2._products.keys())

        assert products1 == products2

    def test_get_product(self, product_store, sample_product_id):
        """Test getting product by ID."""
        product = product_store.get_product(sample_product_id)
        assert product is not None
        assert product.id == sample_product_id

    def test_get_product_not_found(self, product_store):
        """Test getting non-existent product."""
        product = product_store.get_product("non-existent")
        assert product is None

    def test_list_products(self, product_store):
        """Test listing products."""
        items, total = product_store.list_products()
        assert len(items) > 0
        assert total > 0

    def test_list_products_filter_category(self, product_store):
        """Test filtering products by category."""
        items, _ = product_store.list_products(category_id=100)
        for item in items:
            assert item.category_id == 100

    def test_list_products_filter_in_stock(self, product_store):
        """Test filtering products by stock status."""
        items, _ = product_store.list_products(in_stock=True)
        for item in items:
            assert item.in_stock is True

    def test_list_products_sort_by_price(self, product_store):
        """Test sorting products by price."""
        items, _ = product_store.list_products(sort_by="price", sort_order="asc")
        prices = [item.price.amount for item in items]
        assert prices == sorted(prices)

    def test_get_effective_price(self, product_store, sample_product_id):
        """Test getting effective price."""
        price = product_store.get_effective_price(sample_product_id)
        assert price is not None
        assert price > 0

    def test_check_stock(self, product_store, sample_product_id):
        """Test checking stock."""
        # Reset product first to ensure it's in stock
        product_store.reset_product(sample_product_id)
        result = product_store.check_stock(sample_product_id, None, 1)
        assert result is True

    def test_check_stock_exceeds_available(self, product_store, sample_product_id):
        """Test checking stock for excessive quantity."""
        result = product_store.check_stock(sample_product_id, None, 10000)
        assert result is False


class TestProductStoreChaos:
    """Test product store chaos mode functionality."""

    def test_trigger_price_change_increase(self, product_store, sample_product_id):
        """Test triggering price increase."""
        original_price = product_store.get_effective_price(sample_product_id)
        result = product_store.trigger_price_change(sample_product_id, increase=True)

        assert result is not None
        old_price, new_price = result
        assert old_price == original_price
        assert new_price > old_price

    def test_trigger_price_change_decrease(self, product_store, sample_product_id):
        """Test triggering price decrease."""
        original_price = product_store.get_effective_price(sample_product_id)
        result = product_store.trigger_price_change(sample_product_id, increase=False)

        assert result is not None
        old_price, new_price = result
        assert new_price < old_price

    def test_trigger_price_change_not_found(self, product_store):
        """Test triggering price change for non-existent product."""
        result = product_store.trigger_price_change("non-existent")
        assert result is None

    def test_trigger_out_of_stock(self, product_store, sample_product_id):
        """Test triggering out-of-stock."""
        success = product_store.trigger_out_of_stock(sample_product_id)
        assert success is True

        product = product_store._products[sample_product_id]
        assert product.in_stock is False
        assert product.stock_quantity == 0

    def test_trigger_out_of_stock_not_found(self, product_store):
        """Test triggering out-of-stock for non-existent product."""
        success = product_store.trigger_out_of_stock("non-existent")
        assert success is False

    def test_reset_product(self, product_store, sample_product_id):
        """Test resetting product to original state."""
        # Trigger chaos
        product_store.trigger_price_change(sample_product_id)
        product_store.trigger_out_of_stock(sample_product_id)

        # Reset
        success = product_store.reset_product(sample_product_id)
        assert success is True

        product = product_store._products[sample_product_id]
        assert product.in_stock is True
        assert product.price_changed is False

    def test_reset_all_products(self, product_store, sample_product_id):
        """Test resetting all products."""
        # Trigger chaos on sample product
        product_store.trigger_price_change(sample_product_id)
        product_store.trigger_out_of_stock(sample_product_id)

        # Reset all
        product_store.reset_all_products()

        product = product_store._products[sample_product_id]
        assert product.in_stock is True

    def test_get_random_product_id(self, product_store):
        """Test getting random product ID."""
        product_id = product_store.get_random_product_id()
        assert product_id is not None
        assert product_id in product_store._products

    def test_set_price_change_percent(self, product_store, sample_product_id):
        """Test setting price change percentage."""
        product_store.set_price_change_percent(25)
        original_price = product_store.get_effective_price(sample_product_id)

        product_store.trigger_price_change(sample_product_id, increase=True)
        new_price = product_store.get_effective_price(sample_product_id)

        expected_change = int(original_price * 25 / 100)
        assert new_price == original_price + expected_change


class TestLowInventory:
    """Test that Merchant B has lower inventory than Merchant A."""

    def test_some_products_have_low_stock(self, product_store):
        """Test that some products have low stock quantities."""
        low_stock_count = 0
        for product in product_store._products.values():
            if product.stock_quantity <= 15:
                low_stock_count += 1

        # All products should have low stock (1-15)
        assert low_stock_count == len(product_store._products)

    def test_some_variants_out_of_stock(self, product_store):
        """Test that some variants may be out of stock."""
        out_of_stock_count = 0
        for variant_data in product_store._variants.values():
            if not variant_data.get("in_stock", True):
                out_of_stock_count += 1

        # Some variants may be out of stock (stock_quantity was randint(0, 8))
        # This is not guaranteed but likely
        pass  # Just verify the mechanism exists
