"""Product repository for database operations.

Provides CRUD operations for products with filtering and sorting.
"""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.catalog.models import Product, ProductVariant


class ProductRepository:
    """Repository for Product database operations.

    Handles all database interactions for products including
    filtering, sorting, and pagination.

    Example usage:
        async with get_session() as session:
            repo = ProductRepository(session)
            products = await repo.find_all(
                merchant_id="merchant-a",
                category_id=537,
                in_stock=True,
                limit=20,
            )
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: Async SQLAlchemy session.
        """
        self.session = session

    async def save(self, product: Product) -> Product:
        """Save a product to database.

        Args:
            product: Product to save.

        Returns:
            Saved product.
        """
        self.session.add(product)
        await self.session.flush()
        return product

    async def save_all(self, products: list[Product]) -> list[Product]:
        """Save multiple products to database.

        Args:
            products: Products to save.

        Returns:
            Saved products.
        """
        self.session.add_all(products)
        await self.session.flush()
        return products

    async def get_by_id(
        self,
        product_id: str,
        include_variants: bool = True,
    ) -> Product | None:
        """Get product by ID.

        Args:
            product_id: Product ID.
            include_variants: Whether to eagerly load variants.

        Returns:
            Product if found, None otherwise.
        """
        query = select(Product).where(Product.id == product_id)
        
        if include_variants:
            query = query.options(selectinload(Product.variants))
        
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_sku(
        self,
        merchant_id: str,
        sku: str,
        include_variants: bool = True,
    ) -> Product | None:
        """Get product by merchant ID and SKU.

        Args:
            merchant_id: Merchant ID.
            sku: Product SKU.
            include_variants: Whether to eagerly load variants.

        Returns:
            Product if found, None otherwise.
        """
        query = select(Product).where(
            and_(
                Product.merchant_id == merchant_id,
                Product.sku == sku,
            )
        )
        
        if include_variants:
            query = query.options(selectinload(Product.variants))
        
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def find_all(
        self,
        merchant_id: str | None = None,
        category_id: int | None = None,
        category_path_prefix: str | None = None,
        brand: str | None = None,
        brands: list[str] | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        in_stock: bool | None = None,
        search: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        limit: int = 50,
        offset: int = 0,
        include_variants: bool = False,
    ) -> Sequence[Product]:
        """Find products with filtering, sorting, and pagination.

        Args:
            merchant_id: Filter by merchant.
            category_id: Filter by exact category ID.
            category_path_prefix: Filter by category path prefix.
            brand: Filter by single brand.
            brands: Filter by multiple brands (OR).
            min_price: Minimum price in cents.
            max_price: Maximum price in cents.
            in_stock: Filter by stock availability.
            search: Search in title and description.
            sort_by: Sort field (price, rating, created_at, title).
            sort_order: Sort order (asc, desc).
            limit: Maximum results.
            offset: Result offset for pagination.
            include_variants: Whether to eagerly load variants.

        Returns:
            Sequence of matching products.
        """
        query = select(Product)

        # Build filter conditions
        conditions = []

        if merchant_id is not None:
            conditions.append(Product.merchant_id == merchant_id)

        if category_id is not None:
            conditions.append(Product.category_id == category_id)

        if category_path_prefix is not None:
            conditions.append(Product.category_path.startswith(category_path_prefix))

        if brand is not None:
            conditions.append(Product.brand == brand)

        if brands:
            conditions.append(Product.brand.in_(brands))

        if min_price is not None:
            conditions.append(Product.base_price >= min_price)

        if max_price is not None:
            conditions.append(Product.base_price <= max_price)

        if in_stock is not None:
            conditions.append(Product.in_stock == in_stock)

        if search:
            search_pattern = f"%{search}%"
            conditions.append(
                or_(
                    Product.title.ilike(search_pattern),
                    Product.description.ilike(search_pattern),
                    Product.brand.ilike(search_pattern),
                )
            )

        if conditions:
            query = query.where(and_(*conditions))

        # Sorting
        sort_column = self._get_sort_column(sort_by)
        if sort_order.lower() == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # Pagination
        query = query.limit(limit).offset(offset)

        # Eager loading
        if include_variants:
            query = query.options(selectinload(Product.variants))

        result = await self.session.execute(query)
        return result.scalars().all()

    async def count(
        self,
        merchant_id: str | None = None,
        category_id: int | None = None,
        brand: str | None = None,
        in_stock: bool | None = None,
    ) -> int:
        """Count products matching filters.

        Args:
            merchant_id: Filter by merchant.
            category_id: Filter by category.
            brand: Filter by brand.
            in_stock: Filter by stock.

        Returns:
            Count of matching products.
        """
        query = select(func.count(Product.id))

        conditions = []
        if merchant_id is not None:
            conditions.append(Product.merchant_id == merchant_id)
        if category_id is not None:
            conditions.append(Product.category_id == category_id)
        if brand is not None:
            conditions.append(Product.brand == brand)
        if in_stock is not None:
            conditions.append(Product.in_stock == in_stock)

        if conditions:
            query = query.where(and_(*conditions))

        result = await self.session.execute(query)
        return result.scalar_one()

    async def get_brands(self, merchant_id: str | None = None) -> list[str]:
        """Get list of unique brands.

        Args:
            merchant_id: Optional merchant filter.

        Returns:
            List of brand names.
        """
        query = select(Product.brand).distinct()
        
        if merchant_id:
            query = query.where(Product.merchant_id == merchant_id)
        
        query = query.order_by(Product.brand)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_categories(
        self,
        merchant_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get list of categories with product counts.

        Args:
            merchant_id: Optional merchant filter.

        Returns:
            List of category info dicts.
        """
        query = select(
            Product.category_id,
            Product.category_path,
            func.count(Product.id).label("product_count"),
        ).group_by(
            Product.category_id,
            Product.category_path,
        )

        if merchant_id:
            query = query.where(Product.merchant_id == merchant_id)

        query = query.order_by(Product.category_path)

        result = await self.session.execute(query)
        return [
            {
                "category_id": row.category_id,
                "category_path": row.category_path,
                "product_count": row.product_count,
            }
            for row in result.all()
        ]

    async def delete_by_merchant(self, merchant_id: str) -> int:
        """Delete all products for a merchant.

        Args:
            merchant_id: Merchant ID.

        Returns:
            Number of deleted products.
        """
        # First get count
        count = await self.count(merchant_id=merchant_id)
        
        # Get all products
        products = await self.find_all(merchant_id=merchant_id, limit=10000)
        
        for product in products:
            await self.session.delete(product)
        
        await self.session.flush()
        return count

    def _get_sort_column(self, sort_by: str) -> Any:
        """Get SQLAlchemy column for sorting.

        Args:
            sort_by: Sort field name.

        Returns:
            SQLAlchemy column.
        """
        columns = {
            "price": Product.base_price,
            "rating": Product.rating,
            "created_at": Product.created_at,
            "title": Product.title,
            "brand": Product.brand,
            "review_count": Product.review_count,
        }
        return columns.get(sort_by, Product.created_at)
