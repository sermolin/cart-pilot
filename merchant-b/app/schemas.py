"""Pydantic schemas for Merchant B API.

Defines request/response models for products, checkout, webhooks, and chaos configuration.
Same UCP contract as Merchant A with additional chaos mode schemas.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field


# ============================================================================
# Common Types
# ============================================================================


class Currency(str, Enum):
    """Supported currencies."""

    USD = "USD"
    EUR = "EUR"


class PriceSchema(BaseModel):
    """Price with amount and currency."""

    amount: int = Field(..., description="Amount in cents")
    currency: Currency = Field(default=Currency.USD, description="Currency code")

    @property
    def amount_decimal(self) -> Decimal:
        """Get amount as decimal."""
        return Decimal(self.amount) / 100


class UCPMixin:
    """Mixin for UCP (Universal Commerce Protocol) version."""

    ucp_version: str = Field(default="1.0.0", description="UCP protocol version")


# ============================================================================
# Product Schemas
# ============================================================================


class ProductVariantSchema(BaseModel):
    """Product variant (size/color combination)."""

    id: str = Field(..., description="Variant ID")
    sku_suffix: str = Field(..., description="SKU suffix for variant")
    name: str = Field(..., description="Variant name (e.g., 'Red, Large')")
    color: str | None = Field(None, description="Color if applicable")
    size: str | None = Field(None, description="Size if applicable")
    price_modifier: int = Field(default=0, description="Price modifier in cents")
    in_stock: bool = Field(default=True, description="Variant availability")
    stock_quantity: int = Field(default=50, description="Available quantity")


class ProductSchema(BaseModel, UCPMixin):
    """Product details."""

    id: str = Field(..., description="Product ID")
    sku: str = Field(..., description="Stock Keeping Unit")
    title: str = Field(..., description="Product title")
    description: str | None = Field(None, description="Product description")
    brand: str = Field(..., description="Brand name")
    category_id: int = Field(..., description="Category ID")
    category_path: str = Field(..., description="Full category path")
    price: PriceSchema = Field(..., description="Product price")
    rating: float = Field(..., ge=0, le=5, description="Average rating")
    review_count: int = Field(..., ge=0, description="Number of reviews")
    image_url: str | None = Field(None, description="Product image URL")
    in_stock: bool = Field(default=True, description="Product availability")
    stock_quantity: int = Field(default=100, description="Available quantity")
    variants: list[ProductVariantSchema] = Field(
        default_factory=list, description="Product variants"
    )


class ProductListResponse(BaseModel, UCPMixin):
    """Paginated product list response."""

    items: list[ProductSchema] = Field(..., description="List of products")
    total: int = Field(..., description="Total number of products")
    page: int = Field(default=1, ge=1, description="Current page")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")
    has_more: bool = Field(..., description="Whether more pages exist")


class ProductFilterParams(BaseModel):
    """Product filtering parameters."""

    category_id: int | None = Field(None, description="Filter by category ID")
    brand: str | None = Field(None, description="Filter by brand name")
    min_price: int | None = Field(None, ge=0, description="Minimum price in cents")
    max_price: int | None = Field(None, ge=0, description="Maximum price in cents")
    in_stock: bool | None = Field(None, description="Filter by availability")
    search: str | None = Field(None, description="Search in title/description")


# ============================================================================
# Checkout Schemas
# ============================================================================


class CheckoutStatus(str, Enum):
    """Checkout session status."""

    CREATED = "created"
    QUOTED = "quoted"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    EXPIRED = "expired"


class CheckoutItemRequest(BaseModel):
    """Item to add to checkout."""

    product_id: str = Field(..., description="Product ID")
    variant_id: str | None = Field(None, description="Variant ID if applicable")
    quantity: int = Field(..., ge=1, description="Quantity to purchase")


class QuoteRequest(BaseModel):
    """Request to create a quote for items."""

    items: list[CheckoutItemRequest] = Field(
        ..., min_length=1, description="Items to quote"
    )
    customer_email: str | None = Field(None, description="Customer email for receipt")
    idempotency_key: str | None = Field(None, description="Idempotency key")


class CheckoutItemSchema(BaseModel):
    """Item in checkout with calculated price."""

    product_id: str = Field(..., description="Product ID")
    variant_id: str | None = Field(None, description="Variant ID")
    sku: str = Field(..., description="Product SKU")
    title: str = Field(..., description="Product title")
    unit_price: PriceSchema = Field(..., description="Unit price")
    quantity: int = Field(..., ge=1, description="Quantity")
    line_total: PriceSchema = Field(..., description="Line total")


class CheckoutSchema(BaseModel, UCPMixin):
    """Checkout session details."""

    id: str = Field(..., description="Checkout session ID")
    status: CheckoutStatus = Field(..., description="Current status")
    items: list[CheckoutItemSchema] = Field(..., description="Checkout items")
    subtotal: PriceSchema = Field(..., description="Subtotal before tax/shipping")
    tax: PriceSchema = Field(..., description="Tax amount")
    shipping: PriceSchema = Field(..., description="Shipping cost")
    total: PriceSchema = Field(..., description="Total amount")
    customer_email: str | None = Field(None, description="Customer email")
    receipt_hash: str | None = Field(None, description="Hash of frozen receipt")
    merchant_order_id: str | None = Field(
        None, description="Merchant order ID after confirmation"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    expires_at: datetime | None = Field(None, description="Expiration timestamp")
    failure_reason: str | None = Field(None, description="Failure reason if failed")


class ConfirmRequest(BaseModel):
    """Request to confirm a checkout."""

    idempotency_key: str | None = Field(None, description="Idempotency key")
    payment_method: str = Field(
        default="test_card", description="Payment method identifier"
    )


class ConfirmResponse(BaseModel, UCPMixin):
    """Response after checkout confirmation."""

    checkout_id: str = Field(..., description="Checkout session ID")
    merchant_order_id: str = Field(..., description="Merchant's order ID")
    status: CheckoutStatus = Field(..., description="Final status")
    total: PriceSchema = Field(..., description="Total charged")
    confirmed_at: datetime = Field(..., description="Confirmation timestamp")


# ============================================================================
# Webhook Schemas
# ============================================================================


class WebhookEventType(str, Enum):
    """Types of webhook events."""

    CHECKOUT_CREATED = "checkout.created"
    CHECKOUT_QUOTED = "checkout.quoted"
    CHECKOUT_CONFIRMED = "checkout.confirmed"
    CHECKOUT_FAILED = "checkout.failed"
    CHECKOUT_EXPIRED = "checkout.expired"
    ORDER_CREATED = "order.created"
    ORDER_SHIPPED = "order.shipped"
    ORDER_DELIVERED = "order.delivered"
    PRICE_CHANGED = "price.changed"
    STOCK_CHANGED = "stock.changed"


class WebhookPayloadSchema(BaseModel):
    """Webhook event payload."""

    event_id: str = Field(..., description="Unique event ID")
    event_type: WebhookEventType = Field(..., description="Event type")
    merchant_id: str = Field(..., description="Merchant ID")
    timestamp: datetime = Field(..., description="Event timestamp")
    data: dict = Field(..., description="Event-specific data")
    ucp_version: str = Field(default="1.0.0", description="UCP version")


# ============================================================================
# Chaos Mode Schemas
# ============================================================================


class ChaosScenario(str, Enum):
    """Available chaos scenarios."""

    PRICE_CHANGE = "price_change"
    OUT_OF_STOCK = "out_of_stock"
    DUPLICATE_WEBHOOK = "duplicate_webhook"
    DELAYED_WEBHOOK = "delayed_webhook"
    OUT_OF_ORDER_WEBHOOK = "out_of_order_webhook"


class ChaosConfigRequest(BaseModel):
    """Request to configure chaos mode."""

    scenarios: dict[ChaosScenario, bool] = Field(
        default_factory=dict,
        description="Map of scenario to enabled status",
    )
    price_change_percent: int = Field(
        default=15,
        ge=1,
        le=50,
        description="Percentage of price change (1-50%)",
    )
    out_of_stock_probability: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Probability of item going out of stock",
    )
    duplicate_webhook_count: int = Field(
        default=3,
        ge=2,
        le=10,
        description="Number of duplicate webhooks to send",
    )
    webhook_delay_seconds: float = Field(
        default=5.0,
        ge=0.5,
        le=30.0,
        description="Delay in seconds for delayed webhooks",
    )


class ChaosConfigResponse(BaseModel):
    """Response with current chaos configuration."""

    enabled: bool = Field(..., description="Whether chaos mode is globally enabled")
    scenarios: dict[ChaosScenario, bool] = Field(
        ..., description="Current scenario states"
    )
    price_change_percent: int = Field(..., description="Price change percentage")
    out_of_stock_probability: float = Field(
        ..., description="Out of stock probability"
    )
    duplicate_webhook_count: int = Field(..., description="Duplicate webhook count")
    webhook_delay_seconds: float = Field(..., description="Webhook delay in seconds")


class ChaosEventLog(BaseModel):
    """Log entry for a triggered chaos event."""

    id: str = Field(..., description="Event ID")
    scenario: ChaosScenario = Field(..., description="Triggered scenario")
    checkout_id: str | None = Field(None, description="Related checkout ID")
    details: dict = Field(default_factory=dict, description="Event details")
    triggered_at: datetime = Field(..., description="When event was triggered")


class ChaosEventsResponse(BaseModel):
    """Response with recent chaos events."""

    events: list[ChaosEventLog] = Field(..., description="Recent chaos events")
    total: int = Field(..., description="Total event count")


# ============================================================================
# Error Schemas
# ============================================================================


class ErrorDetail(BaseModel):
    """Detailed error information."""

    field: str | None = Field(None, description="Field with error")
    message: str = Field(..., description="Error message")
    code: str | None = Field(None, description="Error code")


class ErrorResponse(BaseModel):
    """Standard error response."""

    error_code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    details: list[ErrorDetail] = Field(
        default_factory=list, description="Detailed errors"
    )
    request_id: str | None = Field(None, description="Request ID for tracing")
