"""Catalog service for product operations.

High-level service that combines repository operations with
business logic for catalog management.
"""

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")

from app.catalog.generator import GeneratorConfig, ProductGenerator
from app.catalog.models import Product
from app.catalog.repository import ProductRepository
from app.catalog.taxonomy import Category, TaxonomyParser


@dataclass
class ProductFilter:
    """Filter parameters for product search.

    Attributes:
        merchant_id: Filter by merchant.
        category_id: Filter by category ID.
        category_path: Filter by category path prefix.
        brand: Filter by brand.
        brands: Filter by multiple brands.
        min_price: Minimum price in cents.
        max_price: Maximum price in cents.
        in_stock: Filter by availability.
        search: Text search in title/description.
    """

    merchant_id: str | None = None
    category_id: int | None = None
    category_path: str | None = None
    brand: str | None = None
    brands: list[str] | None = None
    min_price: int | None = None
    max_price: int | None = None
    in_stock: bool | None = None
    search: str | None = None


@dataclass
class PaginationParams:
    """Pagination parameters.

    Attributes:
        page: Page number (1-indexed).
        page_size: Items per page.
        sort_by: Sort field.
        sort_order: Sort order (asc/desc).
    """

    page: int = 1
    page_size: int = 20
    sort_by: str = "created_at"
    sort_order: str = "desc"

    @property
    def offset(self) -> int:
        """Calculate offset from page number."""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """Get limit (alias for page_size)."""
        return self.page_size


@dataclass
class PaginatedResult(Generic[T]):
    """Paginated result container.

    Attributes:
        items: List of items.
        total: Total count.
        page: Current page.
        page_size: Items per page.
        total_pages: Total number of pages.
    """

    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        """Calculate total pages."""
        return (self.total + self.page_size - 1) // self.page_size

    @property
    def has_next(self) -> bool:
        """Check if there's a next page."""
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        """Check if there's a previous page."""
        return self.page > 1


class CatalogService:
    """Service for catalog operations.

    Provides high-level operations for product catalog including
    seeding, searching, and filtering.

    Example usage:
        async with get_session() as session:
            service = CatalogService(session)
            
            # Seed catalog
            await service.seed_catalog("merchant-a", mode="small")
            
            # Search products
            results = await service.search_products(
                ProductFilter(brand="Acme", in_stock=True),
                PaginationParams(page=1, sort_by="price"),
            )
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize service with database session.

        Args:
            session: Async SQLAlchemy session.
        """
        self.session = session
        self.repository = ProductRepository(session)
        self.taxonomy = TaxonomyParser()
        self.taxonomy.parse_embedded()

    async def seed_catalog(
        self,
        merchant_id: str,
        mode: str = "small",
        clear_existing: bool = True,
    ) -> dict[str, Any]:
        """Seed product catalog for a merchant.

        Args:
            merchant_id: Merchant to seed products for.
            mode: Catalog size ("small" or "full").
            clear_existing: Whether to delete existing products first.

        Returns:
            Seeding result with counts.
        """
        # Get generator config
        if mode == "full":
            config = GeneratorConfig.full(merchant_id)
        else:
            config = GeneratorConfig.small(merchant_id)

        # Clear existing products if requested
        deleted = 0
        if clear_existing:
            deleted = await self.repository.delete_by_merchant(merchant_id)

        # Generate products
        generator = ProductGenerator(config)
        products = generator.generate_list()

        # Save to database
        await self.repository.save_all(products)
        await self.session.commit()

        # Count variants
        variant_count = sum(len(p.variants) for p in products)

        return {
            "merchant_id": merchant_id,
            "mode": mode,
            "deleted": deleted,
            "products_created": len(products),
            "variants_created": variant_count,
            "categories_used": len(set(p.category_id for p in products)),
            "brands_used": len(set(p.brand for p in products)),
        }

    async def get_product(
        self,
        product_id: str,
        include_variants: bool = True,
    ) -> Product | None:
        """Get product by ID.

        Args:
            product_id: Product ID.
            include_variants: Whether to include variants.

        Returns:
            Product if found.
        """
        return await self.repository.get_by_id(product_id, include_variants)

    async def get_product_by_sku(
        self,
        merchant_id: str,
        sku: str,
    ) -> Product | None:
        """Get product by merchant and SKU.

        Args:
            merchant_id: Merchant ID.
            sku: Product SKU.

        Returns:
            Product if found.
        """
        return await self.repository.get_by_sku(merchant_id, sku)

    async def search_products(
        self,
        filters: ProductFilter,
        pagination: PaginationParams,
    ) -> PaginatedResult[Product]:
        """Search products with filters and pagination.

        Args:
            filters: Filter parameters.
            pagination: Pagination parameters.

        Returns:
            Paginated product results.
        """
        # Get products
        products = await self.repository.find_all(
            merchant_id=filters.merchant_id,
            category_id=filters.category_id,
            category_path_prefix=filters.category_path,
            brand=filters.brand,
            brands=filters.brands,
            min_price=filters.min_price,
            max_price=filters.max_price,
            in_stock=filters.in_stock,
            search=filters.search,
            sort_by=pagination.sort_by,
            sort_order=pagination.sort_order,
            limit=pagination.limit,
            offset=pagination.offset,
            include_variants=True,
        )

        # Get total count
        total = await self.repository.count(
            merchant_id=filters.merchant_id,
            category_id=filters.category_id,
            brand=filters.brand,
            in_stock=filters.in_stock,
        )

        return PaginatedResult(
            items=list(products),
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    async def get_brands(self, merchant_id: str | None = None) -> list[str]:
        """Get available brands.

        Args:
            merchant_id: Optional merchant filter.

        Returns:
            List of brand names.
        """
        return await self.repository.get_brands(merchant_id)

    async def get_categories(
        self,
        merchant_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get categories with product counts.

        Args:
            merchant_id: Optional merchant filter.

        Returns:
            List of category info.
        """
        return await self.repository.get_categories(merchant_id)

    def get_taxonomy_categories(self) -> list[Category]:
        """Get all taxonomy categories.

        Returns:
            List of taxonomy categories.
        """
        return self.taxonomy.get_all()

    def search_taxonomy(self, query: str) -> list[Category]:
        """Search taxonomy categories.

        Args:
            query: Search query.

        Returns:
            Matching categories.
        """
        return self.taxonomy.search(query)
