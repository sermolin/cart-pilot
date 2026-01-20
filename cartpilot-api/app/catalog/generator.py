"""Product catalog generator with deterministic seeding.

Generates realistic product catalogs using Google Product Taxonomy
and synthetic data. Uses seeded random for reproducibility.
"""

import hashlib
import random
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterator

from app.catalog.models import Product, ProductVariant
from app.catalog.taxonomy import Category, TaxonomyParser


# ============================================================================
# Constants
# ============================================================================

# Synthetic brand names (fictional companies)
BRANDS = [
    "Acme",
    "Contoso",
    "Northwind",
    "Fabrikam",
    "Tailwind",
    "Globex",
    "Initech",
    "Umbrella",
    "Stark",
    "Wayne",
]

# Price ranges by category keywords (in cents)
PRICE_RANGES: dict[str, tuple[int, int]] = {
    "Electronics": (2999, 199999),
    "Computers": (49999, 299999),
    "Laptops": (59999, 349999),
    "Tablets": (29999, 149999),
    "Mobile Phones": (19999, 149999),
    "Audio": (1999, 49999),
    "Headphones": (2999, 39999),
    "Speakers": (4999, 79999),
    "Video Game": (4999, 69999),
    "Furniture": (9999, 299999),
    "Apparel": (1999, 29999),
    "Clothing": (1999, 19999),
    "Shoes": (4999, 39999),
    "Toys": (999, 9999),
    "Games": (1999, 6999),
    "Books": (999, 4999),
    "Food": (299, 4999),
    "Health": (999, 9999),
    "Beauty": (999, 14999),
    "Sports": (1999, 49999),
    "Home": (1999, 49999),
    "Garden": (1999, 29999),
    "Office": (499, 19999),
    "Pet": (999, 9999),
    "Baby": (999, 19999),
    "default": (999, 9999),
}

# Categories that should have color variants
COLOR_CATEGORIES = {
    "Clothing", "Shirts", "Tops", "Pants", "Dresses", "Outerwear",
    "Shoes", "Bags", "Backpacks", "Furniture", "Chairs",
}

# Categories that should have size variants
SIZE_CATEGORIES = {
    "Clothing", "Shirts", "Tops", "Pants", "Dresses", "Outerwear", "Shoes",
}

# Available colors
COLORS = [
    ("Black", "BLK"),
    ("White", "WHT"),
    ("Red", "RED"),
    ("Blue", "BLU"),
    ("Green", "GRN"),
    ("Navy", "NVY"),
    ("Gray", "GRY"),
]

# Available sizes
SIZES = [
    ("Small", "S"),
    ("Medium", "M"),
    ("Large", "L"),
    ("X-Large", "XL"),
]

# Shoe sizes
SHOE_SIZES = [
    ("US 7", "7"),
    ("US 8", "8"),
    ("US 9", "9"),
    ("US 10", "10"),
    ("US 11", "11"),
    ("US 12", "12"),
]

# Product name templates by category
PRODUCT_TEMPLATES: dict[str, list[str]] = {
    "Electronics": [
        "{brand} Smart Device Pro",
        "{brand} Digital {adj} System",
        "{brand} Electronic {adj} Unit",
    ],
    "Computers": [
        "{brand} {adj} Computer",
        "{brand} Computing System {adj}",
    ],
    "Laptops": [
        "{brand} {adj} Laptop 15\"",
        "{brand} Notebook {adj} Pro",
        "{brand} UltraBook {adj}",
    ],
    "Tablets": [
        "{brand} Tablet {adj}",
        "{brand} {adj} Pad Pro",
    ],
    "Mobile Phones": [
        "{brand} Phone {adj}",
        "{brand} Smartphone {adj} Pro",
    ],
    "Headphones": [
        "{brand} {adj} Headphones",
        "{brand} Wireless {adj} Earbuds",
        "{brand} Over-Ear {adj}",
    ],
    "Speakers": [
        "{brand} {adj} Speaker",
        "{brand} Bluetooth {adj} Sound",
        "{brand} Portable {adj} Speaker",
    ],
    "Shirts & Tops": [
        "{brand} {adj} T-Shirt",
        "{brand} Cotton {adj} Shirt",
        "{brand} {adj} Polo",
    ],
    "Pants": [
        "{brand} {adj} Jeans",
        "{brand} Casual {adj} Pants",
        "{brand} {adj} Chinos",
    ],
    "Shoes": [
        "{brand} {adj} Sneakers",
        "{brand} Running {adj}",
        "{brand} {adj} Athletic Shoes",
    ],
    "Furniture": [
        "{brand} {adj} Furniture Set",
        "{brand} Modern {adj}",
    ],
    "Chairs": [
        "{brand} {adj} Office Chair",
        "{brand} Ergonomic {adj} Chair",
        "{brand} {adj} Desk Chair",
    ],
    "Tables": [
        "{brand} {adj} Table",
        "{brand} {adj} Desk",
        "{brand} Coffee {adj} Table",
    ],
    "Toys": [
        "{brand} {adj} Toy Set",
        "{brand} Kids {adj} Playset",
    ],
    "Games": [
        "{brand} {adj} Game",
        "{brand} {adj} Challenge",
    ],
    "Board Games": [
        "{brand} {adj} Board Game",
        "{brand} Strategy {adj}",
        "{brand} Family {adj} Game",
    ],
    "Video Games": [
        "{brand} {adj} Adventure",
        "{brand} {adj} Quest",
        "{brand} {adj} Legends",
    ],
    "default": [
        "{brand} {adj} Product",
        "{brand} Premium {adj}",
        "{brand} {adj} Essential",
    ],
}

# Adjectives for product names
ADJECTIVES = [
    "Premium", "Elite", "Pro", "Ultra", "Max", "Plus",
    "Classic", "Essential", "Advanced", "Smart", "Dynamic",
    "Flex", "Prime", "Apex", "Core", "Nova", "Titan",
]


# ============================================================================
# Generator Configuration
# ============================================================================


@dataclass
class GeneratorConfig:
    """Configuration for product generation.

    Attributes:
        seed: Random seed for reproducibility.
        products_per_category: Number of products per category.
        include_variants: Whether to generate variants.
        variants_per_product: Max variants per product.
        merchant_id: Merchant ID for generated products.
    """

    seed: int = 42
    products_per_category: int = 10
    include_variants: bool = True
    variants_per_product: int = 4
    merchant_id: str = "merchant-a"

    @classmethod
    def small(cls, merchant_id: str = "merchant-a") -> "GeneratorConfig":
        """Create config for small catalog (~100 products).

        Args:
            merchant_id: Merchant ID.

        Returns:
            Config for small catalog.
        """
        return cls(
            seed=42,
            products_per_category=5,
            include_variants=True,
            variants_per_product=3,
            merchant_id=merchant_id,
        )

    @classmethod
    def full(cls, merchant_id: str = "merchant-a") -> "GeneratorConfig":
        """Create config for full catalog (~500+ products).

        Args:
            merchant_id: Merchant ID.

        Returns:
            Config for full catalog.
        """
        return cls(
            seed=42,
            products_per_category=15,
            include_variants=True,
            variants_per_product=6,
            merchant_id=merchant_id,
        )


# ============================================================================
# Product Generator
# ============================================================================


class ProductGenerator:
    """Generates product catalogs with deterministic seeding.

    Uses Google Product Taxonomy for categories and generates
    realistic products with appropriate prices and variants.

    Example usage:
        generator = ProductGenerator(GeneratorConfig.small())
        for product in generator.generate():
            print(product.title)
    """

    def __init__(self, config: GeneratorConfig) -> None:
        """Initialize generator with configuration.

        Args:
            config: Generator configuration.
        """
        self.config = config
        self.rng = random.Random(config.seed)
        self.taxonomy = TaxonomyParser()
        self.taxonomy.parse_embedded()
        self._product_counter = 0

    def _deterministic_seed(self, *args: str | int) -> int:
        """Create deterministic seed from arguments.

        Args:
            args: Values to include in seed.

        Returns:
            Deterministic integer seed.
        """
        data = "|".join(str(a) for a in args)
        hash_bytes = hashlib.md5(data.encode()).digest()
        return int.from_bytes(hash_bytes[:4], "big")

    def _get_price_range(self, category: Category) -> tuple[int, int]:
        """Get price range for category.

        Args:
            category: Product category.

        Returns:
            Tuple of (min_price, max_price) in cents.
        """
        # Check category path parts for matching keywords
        for part in reversed(category.path_parts):
            if part in PRICE_RANGES:
                return PRICE_RANGES[part]
        return PRICE_RANGES["default"]

    def _get_templates(self, category: Category) -> list[str]:
        """Get product name templates for category.

        Args:
            category: Product category.

        Returns:
            List of name templates.
        """
        for part in reversed(category.path_parts):
            if part in PRODUCT_TEMPLATES:
                return PRODUCT_TEMPLATES[part]
        return PRODUCT_TEMPLATES["default"]

    def _should_have_colors(self, category: Category) -> bool:
        """Check if category should have color variants.

        Args:
            category: Product category.

        Returns:
            True if color variants should be generated.
        """
        return any(part in COLOR_CATEGORIES for part in category.path_parts)

    def _should_have_sizes(self, category: Category) -> bool:
        """Check if category should have size variants.

        Args:
            category: Product category.

        Returns:
            True if size variants should be generated.
        """
        return any(part in SIZE_CATEGORIES for part in category.path_parts)

    def _is_shoes(self, category: Category) -> bool:
        """Check if category is shoes (use shoe sizes).

        Args:
            category: Product category.

        Returns:
            True if category is shoes.
        """
        return "Shoes" in category.path_parts

    def _generate_sku(self, category: Category, index: int) -> str:
        """Generate SKU for product.

        Args:
            category: Product category.
            index: Product index within category.

        Returns:
            SKU string.
        """
        # Use first 3 letters of category name
        prefix = "".join(c for c in category.name if c.isalpha())[:3].upper()
        if not prefix:
            prefix = "PRD"
        return f"{prefix}-{category.id:04d}-{index:03d}"

    def _generate_image_url(self, product_id: str) -> str:
        """Generate placeholder image URL.

        Args:
            product_id: Product ID.

        Returns:
            Placeholder image URL.
        """
        # Use placeholder service
        seed = self._deterministic_seed(product_id)
        return f"https://picsum.photos/seed/{seed}/400/400"

    def _generate_product(self, category: Category, index: int) -> Product:
        """Generate a single product.

        Args:
            category: Product category.
            index: Product index within category.

        Returns:
            Generated Product.
        """
        # Seed RNG for this specific product
        seed = self._deterministic_seed(
            self.config.seed,
            category.id,
            index,
        )
        rng = random.Random(seed)

        # Select brand and template
        brand = rng.choice(BRANDS)
        templates = self._get_templates(category)
        template = rng.choice(templates)
        adj = rng.choice(ADJECTIVES)

        # Generate product name
        title = template.format(brand=brand, adj=adj)

        # Generate SKU
        sku = self._generate_sku(category, index)

        # Generate price
        min_price, max_price = self._get_price_range(category)
        base_price = rng.randint(min_price, max_price)
        # Round to .99 cents
        base_price = (base_price // 100) * 100 + 99

        # Generate rating
        rating = Decimal(str(round(rng.uniform(3.0, 5.0), 1)))
        review_count = rng.randint(5, 500)

        # Stock
        in_stock = rng.random() > 0.1  # 90% in stock
        stock_quantity = rng.randint(10, 200) if in_stock else 0

        # Generate product ID deterministically
        product_id = hashlib.md5(
            f"{self.config.merchant_id}:{sku}".encode()
        ).hexdigest()[:8] + "-" + hashlib.md5(
            f"{category.id}:{index}".encode()
        ).hexdigest()[:4] + "-" + hashlib.md5(
            f"{self.config.seed}".encode()
        ).hexdigest()[:4] + "-" + hashlib.md5(
            f"{brand}:{title}".encode()
        ).hexdigest()[:4] + "-" + hashlib.md5(
            f"{sku}:{base_price}".encode()
        ).hexdigest()[:12]

        product = Product(
            id=product_id,
            merchant_id=self.config.merchant_id,
            sku=sku,
            title=title,
            description=f"High-quality {category.name.lower()} from {brand}. "
                        f"Part of our {adj.lower()} collection.",
            brand=brand,
            category_id=category.id,
            category_path=category.full_path,
            base_price=base_price,
            currency="USD",
            rating=rating,
            review_count=review_count,
            image_url=self._generate_image_url(product_id),
            in_stock=in_stock,
            stock_quantity=stock_quantity,
        )

        # Generate variants if enabled
        if self.config.include_variants:
            product.variants = list(self._generate_variants(product, category, rng))

        return product

    def _generate_variants(
        self,
        product: Product,
        category: Category,
        rng: random.Random,
    ) -> Iterator[ProductVariant]:
        """Generate variants for a product.

        Args:
            product: Parent product.
            category: Product category.
            rng: Random number generator.

        Yields:
            ProductVariant instances.
        """
        has_colors = self._should_have_colors(category)
        has_sizes = self._should_have_sizes(category)

        if not has_colors and not has_sizes:
            return

        # Select subset of colors/sizes
        colors = rng.sample(COLORS, min(len(COLORS), self.config.variants_per_product))
        
        if self._is_shoes(category):
            sizes = rng.sample(SHOE_SIZES, min(len(SHOE_SIZES), 4))
        else:
            sizes = SIZES

        variant_count = 0
        max_variants = self.config.variants_per_product

        if has_colors and has_sizes:
            # Generate color+size combinations
            for color_name, color_code in colors:
                if variant_count >= max_variants:
                    break
                for size_name, size_code in sizes:
                    if variant_count >= max_variants:
                        break
                    yield ProductVariant(
                        product_id=product.id,
                        sku_suffix=f"-{color_code}-{size_code}",
                        name=f"{color_name}, {size_name}",
                        color=color_name,
                        size=size_name,
                        price_modifier=0,
                        in_stock=rng.random() > 0.15,
                        stock_quantity=rng.randint(5, 50),
                    )
                    variant_count += 1
        elif has_colors:
            # Color variants only
            for color_name, color_code in colors:
                if variant_count >= max_variants:
                    break
                yield ProductVariant(
                    product_id=product.id,
                    sku_suffix=f"-{color_code}",
                    name=color_name,
                    color=color_name,
                    size=None,
                    price_modifier=0,
                    in_stock=rng.random() > 0.15,
                    stock_quantity=rng.randint(5, 50),
                )
                variant_count += 1
        elif has_sizes:
            # Size variants only
            for size_name, size_code in sizes:
                if variant_count >= max_variants:
                    break
                yield ProductVariant(
                    product_id=product.id,
                    sku_suffix=f"-{size_code}",
                    name=size_name,
                    color=None,
                    size=size_name,
                    price_modifier=0,
                    in_stock=rng.random() > 0.15,
                    stock_quantity=rng.randint(5, 50),
                )
                variant_count += 1

    def generate(self) -> Iterator[Product]:
        """Generate all products.

        Yields:
            Generated Product instances.
        """
        categories = self.taxonomy.get_leaf_categories()
        
        for category in categories:
            for i in range(self.config.products_per_category):
                yield self._generate_product(category, i)
                self._product_counter += 1

    def generate_list(self) -> list[Product]:
        """Generate all products as a list.

        Returns:
            List of generated products.
        """
        return list(self.generate())

    @property
    def expected_count(self) -> int:
        """Get expected number of products.

        Returns:
            Expected product count.
        """
        return (
            len(self.taxonomy.get_leaf_categories())
            * self.config.products_per_category
        )
