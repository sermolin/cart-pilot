"""In-memory product store for Merchant A.

Generates and stores products with deterministic seeding.
Provides high inventory and stable pricing for happy-path scenarios.
"""

import hashlib
import random
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterator

from app.schemas import (
    PriceSchema,
    ProductSchema,
    ProductVariantSchema,
    Currency,
)


# ============================================================================
# Constants
# ============================================================================

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

ADJECTIVES = [
    "Premium",
    "Elite",
    "Pro",
    "Ultra",
    "Max",
    "Plus",
    "Classic",
    "Essential",
    "Advanced",
    "Smart",
    "Dynamic",
    "Flex",
    "Prime",
    "Apex",
    "Core",
    "Nova",
    "Titan",
]

COLORS = [
    ("Black", "BLK"),
    ("White", "WHT"),
    ("Red", "RED"),
    ("Blue", "BLU"),
    ("Green", "GRN"),
    ("Navy", "NVY"),
    ("Gray", "GRY"),
]

SIZES = [
    ("Small", "S"),
    ("Medium", "M"),
    ("Large", "L"),
    ("X-Large", "XL"),
]

# Product categories with price ranges and variant settings
CATEGORIES = [
    {
        "id": 100,
        "name": "Laptops",
        "path": "Electronics > Computers > Laptops",
        "price_range": (59999, 199999),
        "has_variants": False,
        "templates": ["{brand} {adj} Laptop 15\"", "{brand} Notebook {adj} Pro"],
    },
    {
        "id": 200,
        "name": "Headphones",
        "path": "Electronics > Audio > Headphones",
        "price_range": (2999, 39999),
        "has_variants": True,
        "variant_type": "color",
        "templates": ["{brand} {adj} Headphones", "{brand} Wireless {adj} Earbuds"],
    },
    {
        "id": 300,
        "name": "T-Shirts",
        "path": "Apparel & Accessories > Clothing > Shirts & Tops",
        "price_range": (1999, 4999),
        "has_variants": True,
        "variant_type": "color_size",
        "templates": ["{brand} {adj} T-Shirt", "{brand} Cotton {adj} Shirt"],
    },
    {
        "id": 400,
        "name": "Office Chairs",
        "path": "Furniture > Office Furniture > Chairs",
        "price_range": (19999, 89999),
        "has_variants": True,
        "variant_type": "color",
        "templates": ["{brand} {adj} Office Chair", "{brand} Ergonomic {adj} Chair"],
    },
    {
        "id": 500,
        "name": "Board Games",
        "path": "Toys & Games > Games > Board Games",
        "price_range": (1999, 6999),
        "has_variants": False,
        "templates": ["{brand} {adj} Board Game", "{brand} Strategy {adj}"],
    },
    {
        "id": 600,
        "name": "Coffee Makers",
        "path": "Home & Garden > Kitchen & Dining > Coffee Makers",
        "price_range": (4999, 29999),
        "has_variants": False,
        "templates": ["{brand} {adj} Coffee Maker", "{brand} Brew {adj} System"],
    },
    {
        "id": 700,
        "name": "Backpacks",
        "path": "Luggage & Bags > Backpacks",
        "price_range": (3999, 14999),
        "has_variants": True,
        "variant_type": "color",
        "templates": ["{brand} {adj} Backpack", "{brand} Travel {adj} Pack"],
    },
    {
        "id": 800,
        "name": "Fitness Trackers",
        "path": "Electronics > Wearables > Fitness Trackers",
        "price_range": (4999, 24999),
        "has_variants": True,
        "variant_type": "color",
        "templates": ["{brand} {adj} Fitness Tracker", "{brand} Smart {adj} Band"],
    },
    {
        "id": 900,
        "name": "Desk Lamps",
        "path": "Home & Garden > Lighting > Desk Lamps",
        "price_range": (2999, 9999),
        "has_variants": True,
        "variant_type": "color",
        "templates": ["{brand} {adj} Desk Lamp", "{brand} LED {adj} Light"],
    },
    {
        "id": 1000,
        "name": "Books",
        "path": "Media > Books",
        "price_range": (999, 3999),
        "has_variants": False,
        "templates": ["The {adj} Guide by {brand}", "{brand}'s {adj} Handbook"],
    },
]


# ============================================================================
# Product Store
# ============================================================================


@dataclass
class InMemoryProduct:
    """Internal product representation."""

    id: str
    sku: str
    title: str
    description: str
    brand: str
    category_id: int
    category_path: str
    base_price: int  # in cents
    currency: str
    rating: float
    review_count: int
    image_url: str
    in_stock: bool
    stock_quantity: int
    variants: list[dict] = field(default_factory=list)


class ProductStore:
    """In-memory product store with deterministic generation.

    Generates products with high inventory and stable pricing
    for happy-path testing scenarios.
    """

    def __init__(
        self,
        merchant_id: str = "merchant-a",
        seed: int = 42,
        products_per_category: int = 5,
    ) -> None:
        """Initialize product store.

        Args:
            merchant_id: Merchant identifier.
            seed: Random seed for reproducibility.
            products_per_category: Products per category.
        """
        self.merchant_id = merchant_id
        self.seed = seed
        self.products_per_category = products_per_category
        self._products: dict[str, InMemoryProduct] = {}
        self._variants: dict[str, dict] = {}  # variant_id -> variant data
        self._generate_products()

    def _deterministic_seed(self, *args: str | int) -> int:
        """Create deterministic seed from arguments."""
        data = "|".join(str(a) for a in args)
        hash_bytes = hashlib.md5(data.encode()).digest()
        return int.from_bytes(hash_bytes[:4], "big")

    def _generate_product_id(self, category_id: int, index: int) -> str:
        """Generate deterministic product ID."""
        data = f"{self.merchant_id}:{category_id}:{index}:{self.seed}"
        return hashlib.md5(data.encode()).hexdigest()[:32]

    def _generate_variant_id(self, product_id: str, suffix: str) -> str:
        """Generate deterministic variant ID."""
        data = f"{product_id}:{suffix}"
        return hashlib.md5(data.encode()).hexdigest()[:32]

    def _generate_products(self) -> None:
        """Generate all products."""
        for category in CATEGORIES:
            rng = random.Random(self._deterministic_seed(self.seed, category["id"]))

            for i in range(self.products_per_category):
                product_rng = random.Random(
                    self._deterministic_seed(self.seed, category["id"], i)
                )

                # Select brand and template
                brand = product_rng.choice(BRANDS)
                adj = product_rng.choice(ADJECTIVES)
                template = product_rng.choice(category["templates"])
                title = template.format(brand=brand, adj=adj)

                # Generate SKU
                prefix = category["name"][:3].upper()
                sku = f"{prefix}-{category['id']:04d}-{i:03d}"

                # Generate price
                min_price, max_price = category["price_range"]
                base_price = product_rng.randint(min_price, max_price)
                base_price = (base_price // 100) * 100 + 99  # Round to .99

                # Generate rating
                rating = round(product_rng.uniform(3.5, 5.0), 1)
                review_count = product_rng.randint(10, 500)

                # High inventory for happy path
                stock_quantity = product_rng.randint(50, 200)

                product_id = self._generate_product_id(category["id"], i)

                # Generate variants if applicable
                variants = []
                if category.get("has_variants"):
                    variant_type = category.get("variant_type", "color")
                    variants = self._generate_variants(
                        product_id, variant_type, product_rng
                    )

                product = InMemoryProduct(
                    id=product_id,
                    sku=sku,
                    title=title,
                    description=f"High-quality {category['name'].lower()} from {brand}. "
                    f"Part of our {adj.lower()} collection.",
                    brand=brand,
                    category_id=category["id"],
                    category_path=category["path"],
                    base_price=base_price,
                    currency="USD",
                    rating=rating,
                    review_count=review_count,
                    image_url=f"https://picsum.photos/seed/{product_id[:8]}/400/400",
                    in_stock=True,  # Always in stock for happy path
                    stock_quantity=stock_quantity,
                    variants=variants,
                )

                self._products[product_id] = product

                # Index variants
                for variant in variants:
                    self._variants[variant["id"]] = {
                        **variant,
                        "product_id": product_id,
                    }

    def _generate_variants(
        self, product_id: str, variant_type: str, rng: random.Random
    ) -> list[dict]:
        """Generate variants for a product."""
        variants = []

        if variant_type == "color":
            selected_colors = rng.sample(COLORS, min(4, len(COLORS)))
            for color_name, color_code in selected_colors:
                variant_id = self._generate_variant_id(product_id, color_code)
                variants.append(
                    {
                        "id": variant_id,
                        "sku_suffix": f"-{color_code}",
                        "name": color_name,
                        "color": color_name,
                        "size": None,
                        "price_modifier": 0,
                        "in_stock": True,
                        "stock_quantity": rng.randint(20, 100),
                    }
                )
        elif variant_type == "color_size":
            selected_colors = rng.sample(COLORS, min(3, len(COLORS)))
            for color_name, color_code in selected_colors:
                for size_name, size_code in SIZES:
                    variant_id = self._generate_variant_id(
                        product_id, f"{color_code}-{size_code}"
                    )
                    variants.append(
                        {
                            "id": variant_id,
                            "sku_suffix": f"-{color_code}-{size_code}",
                            "name": f"{color_name}, {size_name}",
                            "color": color_name,
                            "size": size_name,
                            "price_modifier": 0,
                            "in_stock": True,
                            "stock_quantity": rng.randint(10, 50),
                        }
                    )

        return variants

    def get_product(self, product_id: str) -> ProductSchema | None:
        """Get product by ID.

        Args:
            product_id: Product ID.

        Returns:
            Product schema or None if not found.
        """
        product = self._products.get(product_id)
        if not product:
            return None
        return self._to_schema(product)

    def get_variant(self, variant_id: str) -> dict | None:
        """Get variant by ID.

        Args:
            variant_id: Variant ID.

        Returns:
            Variant data or None if not found.
        """
        return self._variants.get(variant_id)

    def list_products(
        self,
        page: int = 1,
        page_size: int = 20,
        category_id: int | None = None,
        brand: str | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        in_stock: bool | None = None,
        search: str | None = None,
        sort_by: str | None = None,
        sort_order: str = "asc",
    ) -> tuple[list[ProductSchema], int]:
        """List products with filtering and pagination.

        Args:
            page: Page number (1-based).
            page_size: Items per page.
            category_id: Filter by category.
            brand: Filter by brand.
            min_price: Minimum price in cents.
            max_price: Maximum price in cents.
            in_stock: Filter by availability.
            search: Search in title/description.
            sort_by: Field to sort by (price, rating).
            sort_order: Sort order (asc, desc).

        Returns:
            Tuple of (products, total_count).
        """
        # Filter products
        filtered = list(self._products.values())

        if category_id is not None:
            filtered = [p for p in filtered if p.category_id == category_id]

        if brand is not None:
            filtered = [p for p in filtered if p.brand.lower() == brand.lower()]

        if min_price is not None:
            filtered = [p for p in filtered if p.base_price >= min_price]

        if max_price is not None:
            filtered = [p for p in filtered if p.base_price <= max_price]

        if in_stock is not None:
            filtered = [p for p in filtered if p.in_stock == in_stock]

        if search:
            search_lower = search.lower()
            filtered = [
                p
                for p in filtered
                if search_lower in p.title.lower()
                or search_lower in p.description.lower()
            ]

        # Sort
        if sort_by == "price":
            filtered.sort(
                key=lambda p: p.base_price, reverse=(sort_order == "desc")
            )
        elif sort_by == "rating":
            filtered.sort(key=lambda p: p.rating, reverse=(sort_order == "desc"))

        # Paginate
        total = len(filtered)
        start = (page - 1) * page_size
        end = start + page_size
        paginated = filtered[start:end]

        return [self._to_schema(p) for p in paginated], total

    def _to_schema(self, product: InMemoryProduct) -> ProductSchema:
        """Convert internal product to schema."""
        return ProductSchema(
            id=product.id,
            sku=product.sku,
            title=product.title,
            description=product.description,
            brand=product.brand,
            category_id=product.category_id,
            category_path=product.category_path,
            price=PriceSchema(amount=product.base_price, currency=Currency.USD),
            rating=product.rating,
            review_count=product.review_count,
            image_url=product.image_url,
            in_stock=product.in_stock,
            stock_quantity=product.stock_quantity,
            variants=[
                ProductVariantSchema(**v) for v in product.variants
            ],
        )

    def get_effective_price(
        self, product_id: str, variant_id: str | None = None
    ) -> int | None:
        """Get effective price for product/variant.

        Args:
            product_id: Product ID.
            variant_id: Optional variant ID.

        Returns:
            Price in cents or None if not found.
        """
        product = self._products.get(product_id)
        if not product:
            return None

        base_price = product.base_price

        if variant_id:
            variant = self._variants.get(variant_id)
            if variant and variant["product_id"] == product_id:
                base_price += variant["price_modifier"]

        return base_price

    def check_stock(
        self, product_id: str, variant_id: str | None, quantity: int
    ) -> bool:
        """Check if requested quantity is available.

        Args:
            product_id: Product ID.
            variant_id: Optional variant ID.
            quantity: Requested quantity.

        Returns:
            True if sufficient stock available.
        """
        product = self._products.get(product_id)
        if not product or not product.in_stock:
            return False

        if variant_id:
            variant = self._variants.get(variant_id)
            if not variant or not variant["in_stock"]:
                return False
            return variant["stock_quantity"] >= quantity

        return product.stock_quantity >= quantity


# Global product store instance
_product_store: ProductStore | None = None


def get_product_store(
    merchant_id: str = "merchant-a",
    seed: int = 42,
    products_per_category: int = 5,
) -> ProductStore:
    """Get or create product store instance.

    Args:
        merchant_id: Merchant identifier.
        seed: Random seed.
        products_per_category: Products per category.

    Returns:
        ProductStore instance.
    """
    global _product_store
    if _product_store is None:
        _product_store = ProductStore(merchant_id, seed, products_per_category)
    return _product_store
