"""Tests for product store."""

import pytest

from app.products import ProductStore


class TestProductStore:
    """Tests for ProductStore class."""

    def test_init_creates_products(self, product_store: ProductStore):
        """Test that initialization creates products."""
        assert len(product_store._products) > 0

    def test_deterministic_generation(self):
        """Test that product generation is deterministic."""
        store1 = ProductStore(seed=123, products_per_category=2)
        store2 = ProductStore(seed=123, products_per_category=2)

        # Same seeds should produce same products
        assert len(store1._products) == len(store2._products)

        for product_id in store1._products:
            assert product_id in store2._products
            p1 = store1._products[product_id]
            p2 = store2._products[product_id]
            assert p1.title == p2.title
            assert p1.base_price == p2.base_price

    def test_different_seeds_produce_different_products(self):
        """Test that different seeds produce different products."""
        store1 = ProductStore(seed=1, products_per_category=2)
        store2 = ProductStore(seed=2, products_per_category=2)

        # Different seeds should produce different product IDs
        ids1 = set(store1._products.keys())
        ids2 = set(store2._products.keys())
        assert ids1 != ids2

    def test_get_product_returns_schema(self, product_store: ProductStore):
        """Test getting a product returns proper schema."""
        product_id = list(product_store._products.keys())[0]
        product = product_store.get_product(product_id)

        assert product is not None
        assert product.id == product_id
        assert product.ucp_version == "1.0.0"

    def test_get_product_not_found_returns_none(self, product_store: ProductStore):
        """Test getting non-existent product returns None."""
        product = product_store.get_product("non-existent-id")
        assert product is None

    def test_list_products_pagination(self, product_store: ProductStore):
        """Test product listing with pagination."""
        products, total = product_store.list_products(page=1, page_size=5)

        assert len(products) <= 5
        assert total > 0

    def test_list_products_filter_by_brand(self, product_store: ProductStore):
        """Test filtering products by brand."""
        # Get a brand that exists
        some_product = list(product_store._products.values())[0]
        brand = some_product.brand

        products, total = product_store.list_products(brand=brand)

        assert all(p.brand == brand for p in products)

    def test_list_products_filter_by_category(self, product_store: ProductStore):
        """Test filtering products by category."""
        products, total = product_store.list_products(category_id=100)

        assert all(p.category_id == 100 for p in products)

    def test_list_products_filter_by_price_range(self, product_store: ProductStore):
        """Test filtering products by price range."""
        products, total = product_store.list_products(
            min_price=5000, max_price=10000
        )

        for p in products:
            assert p.price.amount >= 5000
            assert p.price.amount <= 10000

    def test_list_products_filter_in_stock(self, product_store: ProductStore):
        """Test filtering by in-stock status."""
        products, total = product_store.list_products(in_stock=True)

        assert all(p.in_stock for p in products)

    def test_list_products_search(self, product_store: ProductStore):
        """Test searching products."""
        products, total = product_store.list_products(search="Premium")

        assert all(
            "premium" in p.title.lower() or "premium" in (p.description or "").lower()
            for p in products
        )

    def test_list_products_sort_by_price(self, product_store: ProductStore):
        """Test sorting products by price."""
        products_asc, _ = product_store.list_products(
            sort_by="price", sort_order="asc"
        )
        products_desc, _ = product_store.list_products(
            sort_by="price", sort_order="desc"
        )

        if len(products_asc) > 1:
            prices_asc = [p.price.amount for p in products_asc]
            assert prices_asc == sorted(prices_asc)

            prices_desc = [p.price.amount for p in products_desc]
            assert prices_desc == sorted(prices_desc, reverse=True)

    def test_list_products_sort_by_rating(self, product_store: ProductStore):
        """Test sorting products by rating."""
        products_desc, _ = product_store.list_products(
            sort_by="rating", sort_order="desc"
        )

        if len(products_desc) > 1:
            ratings = [p.rating for p in products_desc]
            assert ratings == sorted(ratings, reverse=True)

    def test_get_effective_price_without_variant(self, product_store: ProductStore):
        """Test getting effective price without variant."""
        product_id = list(product_store._products.keys())[0]
        product = product_store._products[product_id]

        price = product_store.get_effective_price(product_id)

        assert price == product.base_price

    def test_get_effective_price_with_variant(self, product_store: ProductStore):
        """Test getting effective price with variant."""
        # Find a product with variants
        for product in product_store._products.values():
            if product.variants:
                variant = product.variants[0]
                price = product_store.get_effective_price(
                    product.id, variant["id"]
                )
                expected = product.base_price + variant["price_modifier"]
                assert price == expected
                return

    def test_check_stock_available(self, product_store: ProductStore):
        """Test stock check for available product."""
        product_id = list(product_store._products.keys())[0]

        # Should have stock (happy path merchant)
        result = product_store.check_stock(product_id, None, 1)
        assert result is True

    def test_check_stock_not_found(self, product_store: ProductStore):
        """Test stock check for non-existent product."""
        result = product_store.check_stock("non-existent", None, 1)
        assert result is False

    def test_products_have_high_inventory(self, product_store: ProductStore):
        """Test that products have high inventory (happy path)."""
        for product in product_store._products.values():
            assert product.in_stock is True
            assert product.stock_quantity >= 50


class TestProductVariants:
    """Tests for product variants."""

    def test_products_have_variants(self, product_store: ProductStore):
        """Test that some products have variants."""
        has_variants = any(
            p.variants for p in product_store._products.values()
        )
        assert has_variants

    def test_variant_has_required_fields(self, product_store: ProductStore):
        """Test that variants have required fields."""
        for product in product_store._products.values():
            for variant in product.variants:
                assert "id" in variant
                assert "sku_suffix" in variant
                assert "name" in variant
                assert "in_stock" in variant
                assert "stock_quantity" in variant

    def test_get_variant(self, product_store: ProductStore):
        """Test getting variant by ID."""
        # Find a variant
        for product in product_store._products.values():
            if product.variants:
                variant_id = product.variants[0]["id"]
                variant = product_store.get_variant(variant_id)
                assert variant is not None
                assert variant["product_id"] == product.id
                return

    def test_get_variant_not_found(self, product_store: ProductStore):
        """Test getting non-existent variant."""
        variant = product_store.get_variant("non-existent")
        assert variant is None
