"""SQLAlchemy models for product catalog.

Defines Product and ProductVariant tables for persistent storage.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base

if TYPE_CHECKING:
    pass


class Product(Base):
    """Product entity in the catalog.

    Represents a product available for purchase from a merchant.

    Attributes:
        id: Unique product identifier (UUID).
        merchant_id: Merchant that sells this product.
        sku: Stock Keeping Unit (unique per merchant).
        title: Product title.
        description: Product description.
        brand: Brand name.
        category_id: Google Product Taxonomy category ID.
        category_path: Full category path (e.g., "Electronics > Computers > Laptops").
        base_price: Base price in cents.
        currency: Currency code (default USD).
        rating: Average rating (0.0-5.0).
        review_count: Number of reviews.
        image_url: Product image URL.
        in_stock: Whether product is available.
        stock_quantity: Available quantity.
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """

    __tablename__ = "products"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    merchant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    category_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    category_path: Mapped[str] = mapped_column(String(500), nullable=False)
    base_price: Mapped[int] = mapped_column(Integer, nullable=False)  # in cents
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    rating: Mapped[Decimal] = mapped_column(Numeric(2, 1), nullable=False, default=Decimal("0.0"))
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    in_stock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    stock_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    variants: Mapped[list["ProductVariant"]] = relationship(
        "ProductVariant",
        back_populates="product",
        cascade="all, delete-orphan",
    )

    # Unique constraint on merchant_id + sku
    __table_args__ = (
        {"schema": None},
    )

    def __repr__(self) -> str:
        """String representation."""
        return f"<Product(id={self.id}, sku={self.sku}, title={self.title[:30]}...)>"

    @property
    def price_decimal(self) -> Decimal:
        """Get price as decimal.

        Returns:
            Price in major currency units.
        """
        return Decimal(self.base_price) / 100

    def to_dict(self) -> dict:
        """Convert to dictionary.

        Returns:
            Dictionary representation.
        """
        return {
            "id": self.id,
            "merchant_id": self.merchant_id,
            "sku": self.sku,
            "title": self.title,
            "description": self.description,
            "brand": self.brand,
            "category_id": self.category_id,
            "category_path": self.category_path,
            "price": {
                "amount": self.base_price,
                "currency": self.currency,
            },
            "rating": float(self.rating),
            "review_count": self.review_count,
            "image_url": self.image_url,
            "in_stock": self.in_stock,
            "stock_quantity": self.stock_quantity,
            "variants": [v.to_dict() for v in self.variants],
        }


class ProductVariant(Base):
    """Product variant (e.g., size, color combinations).

    Variants allow products to have different options like size or color,
    each potentially with different prices and stock levels.

    Attributes:
        id: Unique variant identifier.
        product_id: Parent product ID.
        sku_suffix: SKU suffix (e.g., "-RED-L").
        name: Variant name (e.g., "Red, Large").
        attributes: Variant attributes as JSON-like string.
        price_modifier: Price adjustment in cents (can be negative).
        in_stock: Variant availability.
        stock_quantity: Available quantity for this variant.
    """

    __tablename__ = "product_variants"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    product_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sku_suffix: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    color: Mapped[str | None] = mapped_column(String(50), nullable=True)
    size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    price_modifier: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    in_stock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    stock_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=50)

    # Relationships
    product: Mapped["Product"] = relationship("Product", back_populates="variants")

    def __repr__(self) -> str:
        """String representation."""
        return f"<ProductVariant(id={self.id}, name={self.name})>"

    @property
    def full_sku(self) -> str:
        """Get full SKU including parent product SKU.

        Returns:
            Full SKU string.
        """
        return f"{self.product.sku}{self.sku_suffix}"

    @property
    def final_price(self) -> int:
        """Get final price including modifier.

        Returns:
            Final price in cents.
        """
        return self.product.base_price + self.price_modifier

    def to_dict(self) -> dict:
        """Convert to dictionary.

        Returns:
            Dictionary representation.
        """
        return {
            "id": self.id,
            "sku_suffix": self.sku_suffix,
            "full_sku": self.full_sku if self.product else None,
            "name": self.name,
            "color": self.color,
            "size": self.size,
            "price_modifier": self.price_modifier,
            "in_stock": self.in_stock,
            "stock_quantity": self.stock_quantity,
        }
