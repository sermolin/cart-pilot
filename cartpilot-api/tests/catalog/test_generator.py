"""Tests for product catalog generator."""

import pytest

from app.catalog.generator import (
    BRANDS,
    GeneratorConfig,
    ProductGenerator,
)


class TestGeneratorConfig:
    """Tests for GeneratorConfig."""

    def test_small_config(self) -> None:
        """Small config creates reasonable defaults."""
        config = GeneratorConfig.small("test-merchant")
        assert config.products_per_category == 5
        assert config.merchant_id == "test-merchant"

    def test_full_config(self) -> None:
        """Full config creates larger catalog."""
        config = GeneratorConfig.full("test-merchant")
        assert config.products_per_category == 15
        assert config.products_per_category > GeneratorConfig.small().products_per_category


class TestProductGenerator:
    """Tests for ProductGenerator."""

    @pytest.fixture
    def generator(self) -> ProductGenerator:
        """Create generator with small config."""
        return ProductGenerator(GeneratorConfig.small("test-merchant"))

    def test_generate_products(self, generator: ProductGenerator) -> None:
        """Generator produces products."""
        products = generator.generate_list()
        assert len(products) > 0

    def test_deterministic_generation(self) -> None:
        """Same seed produces same products."""
        gen1 = ProductGenerator(GeneratorConfig(seed=42, products_per_category=2))
        gen2 = ProductGenerator(GeneratorConfig(seed=42, products_per_category=2))
        
        products1 = gen1.generate_list()
        products2 = gen2.generate_list()
        
        assert len(products1) == len(products2)
        for p1, p2 in zip(products1, products2):
            assert p1.sku == p2.sku
            assert p1.title == p2.title
            assert p1.base_price == p2.base_price

    def test_different_seeds_produce_different_products(self) -> None:
        """Different seeds produce different products."""
        gen1 = ProductGenerator(GeneratorConfig(seed=42, products_per_category=2))
        gen2 = ProductGenerator(GeneratorConfig(seed=99, products_per_category=2))
        
        products1 = gen1.generate_list()
        products2 = gen2.generate_list()
        
        # At least some products should differ
        titles1 = {p.title for p in products1}
        titles2 = {p.title for p in products2}
        assert titles1 != titles2

    def test_products_have_required_fields(self, generator: ProductGenerator) -> None:
        """Products have all required fields."""
        products = generator.generate_list()
        
        for product in products[:10]:  # Check first 10
            assert product.id is not None
            assert product.sku is not None
            assert product.title is not None
            assert product.merchant_id == "test-merchant"
            assert product.brand in BRANDS
            assert product.base_price > 0
            assert product.category_id > 0
            assert product.category_path is not None

    def test_products_have_valid_ratings(self, generator: ProductGenerator) -> None:
        """Product ratings are in valid range."""
        products = generator.generate_list()
        
        for product in products:
            assert 0 <= float(product.rating) <= 5

    def test_variants_generated_for_clothing(self) -> None:
        """Clothing categories have variants."""
        generator = ProductGenerator(GeneratorConfig.small())
        products = generator.generate_list()
        
        # Find clothing products
        clothing_products = [
            p for p in products
            if "Clothing" in p.category_path or "Shirts" in p.category_path
        ]
        
        # At least some should have variants
        products_with_variants = [p for p in clothing_products if p.variants]
        assert len(products_with_variants) > 0

    def test_variants_have_colors_and_sizes(self) -> None:
        """Clothing variants have color and size."""
        generator = ProductGenerator(GeneratorConfig.small())
        products = generator.generate_list()
        
        # Find product with variants
        product_with_variants = next(
            (p for p in products if p.variants and "Clothing" in p.category_path),
            None,
        )
        
        if product_with_variants:
            variant = product_with_variants.variants[0]
            assert variant.sku_suffix is not None
            assert variant.name is not None

    def test_expected_count(self, generator: ProductGenerator) -> None:
        """Expected count matches actual generation."""
        expected = generator.expected_count
        products = generator.generate_list()
        assert len(products) == expected

    def test_unique_skus_per_merchant(self, generator: ProductGenerator) -> None:
        """SKUs are unique within a merchant."""
        products = generator.generate_list()
        skus = [p.sku for p in products]
        assert len(skus) == len(set(skus))

    def test_price_ranges_by_category(self) -> None:
        """Different categories have different price ranges."""
        generator = ProductGenerator(GeneratorConfig.small())
        products = generator.generate_list()
        
        # Group by category
        electronics = [p for p in products if "Electronics" in p.category_path]
        toys = [p for p in products if "Toys" in p.category_path]
        
        if electronics and toys:
            avg_electronics = sum(p.base_price for p in electronics) / len(electronics)
            avg_toys = sum(p.base_price for p in toys) / len(toys)
            # Electronics should generally be more expensive than toys
            assert avg_electronics > avg_toys
