"""In-memory product store for Merchant B (Chaos Mode).

Generates and stores products with lower inventory and price volatility.
Supports dynamic price changes for chaos testing.
"""

import hashlib
import random
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterator

from app.schemas import (
    Currency,
    PriceSchema,
    ProductSchema,
    ProductVariantSchema,
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
    """Internal product representation with chaos support."""

    id: str
    sku: str
    title: str
    description: str
    brand: str
    category_id: int
    category_path: str
    base_price: int  # in cents
    current_price: int  # mutable - can change for chaos mode
    currency: str
    rating: float
    review_count: int
    image_url: str
    in_stock: bool
    stock_quantity: int
    variants: list[dict] = field(default_factory=list)
    # Chaos tracking
    original_price: int = 0  # stores original price before chaos
    price_changed: bool = False


class ProductStore:
    """In-memory product store with chaos mode support.

    Generates products with LOW inventory and price volatility
    for chaos testing scenarios.
    """

    def __init__(
        self,
        merchant_id: str = "merchant-b",
        seed: int = 43,  # Different seed than merchant-a
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
        self._price_change_percent: int = 15  # Default 15% price change
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
        """Generate all products with low inventory."""
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

                # LOW inventory for chaos mode - some items start out of stock
                stock_quantity = product_rng.randint(1, 15)
                in_stock = stock_quantity > 0

                product_id = self._generate_product_id(category["id"], i)

                # Generate variants if applicable (also with low inventory)
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
                    current_price=base_price,
                    original_price=base_price,
                    currency="USD",
                    rating=rating,
                    review_count=review_count,
                    image_url=f"https://picsum.photos/seed/{product_id[:8]}/400/400",
                    in_stock=in_stock,
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
        """Generate variants for a product with LOW inventory."""
        variants = []

        if variant_type == "color":
            selected_colors = rng.sample(COLORS, min(4, len(COLORS)))
            for color_name, color_code in selected_colors:
                variant_id = self._generate_variant_id(product_id, color_code)
                stock_qty = rng.randint(0, 8)  # Low stock, some may be 0
                variants.append(
                    {
                        "id": variant_id,
                        "sku_suffix": f"-{color_code}",
                        "name": color_name,
                        "color": color_name,
                        "size": None,
                        "price_modifier": 0,
                        "in_stock": stock_qty > 0,
                        "stock_quantity": stock_qty,
                    }
                )
        elif variant_type == "color_size":
            selected_colors = rng.sample(COLORS, min(3, len(COLORS)))
            for color_name, color_code in selected_colors:
                for size_name, size_code in SIZES:
                    variant_id = self._generate_variant_id(
                        product_id, f"{color_code}-{size_code}"
                    )
                    stock_qty = rng.randint(0, 5)  # Very low stock
                    variants.append(
                        {
                            "id": variant_id,
                            "sku_suffix": f"-{color_code}-{size_code}",
                            "name": f"{color_name}, {size_name}",
                            "color": color_name,
                            "size": size_name,
                            "price_modifier": 0,
                            "in_stock": stock_qty > 0,
                            "stock_quantity": stock_qty,
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
            filtered = [p for p in filtered if p.current_price >= min_price]

        if max_price is not None:
            filtered = [p for p in filtered if p.current_price <= max_price]

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
                key=lambda p: p.current_price, reverse=(sort_order == "desc")
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
            price=PriceSchema(amount=product.current_price, currency=Currency.USD),
            rating=product.rating,
            review_count=product.review_count,
            image_url=product.image_url,
            in_stock=product.in_stock,
            stock_quantity=product.stock_quantity,
            variants=[ProductVariantSchema(**v) for v in product.variants],
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

        # Use current price (may be modified by chaos)
        price = product.current_price

        if variant_id:
            variant = self._variants.get(variant_id)
            if variant and variant["product_id"] == product_id:
                price += variant["price_modifier"]

        return price

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

    # ========================================================================
    # Chaos Mode Methods
    # ========================================================================

    def set_price_change_percent(self, percent: int) -> None:
        """Set the price change percentage for chaos mode.

        Args:
            percent: Percentage to change prices (1-50).
        """
        self._price_change_percent = max(1, min(50, percent))

    def trigger_price_change(
        self, product_id: str, increase: bool = True
    ) -> tuple[int, int] | None:
        """Trigger a price change for a product (chaos mode).

        Args:
            product_id: Product ID.
            increase: Whether to increase (True) or decrease (False) price.

        Returns:
            Tuple of (old_price, new_price) or None if not found.
        """
        product = self._products.get(product_id)
        if not product:
            return None

        old_price = product.current_price
        change_amount = int(old_price * self._price_change_percent / 100)

        if increase:
            new_price = old_price + change_amount
        else:
            new_price = max(99, old_price - change_amount)  # Minimum 99 cents

        product.current_price = new_price
        product.price_changed = True

        return (old_price, new_price)

    def trigger_out_of_stock(
        self, product_id: str, variant_id: str | None = None
    ) -> bool:
        """Mark a product or variant as out of stock (chaos mode).

        Args:
            product_id: Product ID.
            variant_id: Optional variant ID.

        Returns:
            True if successful.
        """
        product = self._products.get(product_id)
        if not product:
            return False

        if variant_id:
            variant = self._variants.get(variant_id)
            if variant and variant["product_id"] == product_id:
                variant["in_stock"] = False
                variant["stock_quantity"] = 0
                # Update product variants list
                for v in product.variants:
                    if v["id"] == variant_id:
                        v["in_stock"] = False
                        v["stock_quantity"] = 0
                return True
            return False

        product.in_stock = False
        product.stock_quantity = 0
        return True

    def reset_product(self, product_id: str) -> bool:
        """Reset a product to original state (undo chaos changes).

        Args:
            product_id: Product ID.

        Returns:
            True if successful.
        """
        product = self._products.get(product_id)
        if not product:
            return False

        product.current_price = product.original_price
        product.price_changed = False
        product.in_stock = True
        product.stock_quantity = 10  # Reset to reasonable stock

        # Reset variants
        for variant in product.variants:
            variant["in_stock"] = True
            variant["stock_quantity"] = 5

        # Update variant index
        for variant in product.variants:
            if variant["id"] in self._variants:
                self._variants[variant["id"]]["in_stock"] = True
                self._variants[variant["id"]]["stock_quantity"] = 5

        return True

    def reset_all_products(self) -> None:
        """Reset all products to original state."""
        for product_id in self._products:
            self.reset_product(product_id)

    def get_random_product_id(self) -> str | None:
        """Get a random product ID (for chaos testing).

        Returns:
            Random product ID or None if no products.
        """
        if not self._products:
            return None
        return random.choice(list(self._products.keys()))


# Global product store instance
_product_store: ProductStore | None = None


def get_product_store(
    merchant_id: str = "merchant-b",
    seed: int = 43,
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


def reset_product_store() -> None:
    """Reset product store instance (for testing)."""
    global _product_store
    _product_store = None
