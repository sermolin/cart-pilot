"""API schemas for CartPilot API.

Pydantic models for request/response validation and serialization.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ============================================================================
# Common Schemas
# ============================================================================


class Currency(str, Enum):
    """Supported currencies."""

    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"


class PriceSchema(BaseModel):
    """Price representation."""

    amount: int = Field(..., description="Amount in smallest currency unit (cents)")
    currency: Currency = Field(default=Currency.USD, description="Currency code")


class ErrorDetail(BaseModel):
    """Detailed error information."""

    field: str | None = Field(default=None, description="Field that caused the error")
    message: str = Field(..., description="Error message")


class ErrorResponse(BaseModel):
    """Standard error response.

    All API errors follow this format for consistency.
    """

    error_code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: list[ErrorDetail] = Field(
        default_factory=list, description="Additional error details"
    )
    request_id: str | None = Field(
        default=None, description="Request ID for correlation"
    )


class PaginationParams(BaseModel):
    """Pagination parameters."""

    page: int = Field(default=1, ge=1, description="Page number (1-based)")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")


class PaginatedResponse(BaseModel):
    """Base paginated response."""

    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")
    has_more: bool = Field(..., description="Whether there are more pages")


# ============================================================================
# Intent Schemas
# ============================================================================


class IntentCreateRequest(BaseModel):
    """Request to create a purchase intent."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Natural language search query (e.g., 'I need wireless headphones under $100')",
    )
    session_id: str | None = Field(
        default=None, description="Optional session identifier for the agent"
    )
    metadata: dict[str, Any] | None = Field(
        default=None, description="Optional metadata (filters, hints)"
    )


class IntentResponse(BaseModel):
    """Response for a purchase intent."""

    id: str = Field(..., description="Unique intent identifier")
    query: str = Field(..., description="The original search query")
    session_id: str | None = Field(default=None, description="Session identifier")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Intent metadata"
    )
    offers_collected: bool = Field(
        default=False, description="Whether offers have been collected"
    )
    offer_count: int = Field(default=0, description="Number of offers collected")
    created_at: datetime = Field(..., description="When the intent was created")
    updated_at: datetime = Field(..., description="When the intent was last updated")


class IntentsListResponse(PaginatedResponse):
    """Paginated list of intents."""

    items: list[IntentResponse] = Field(..., description="List of intents")


# ============================================================================
# Offer Schemas
# ============================================================================


class OfferItemSchema(BaseModel):
    """A product item within an offer."""

    product_id: str = Field(..., description="Merchant's product identifier")
    variant_id: str | None = Field(default=None, description="Variant identifier")
    sku: str | None = Field(default=None, description="Stock keeping unit")
    title: str = Field(..., description="Product title")
    description: str | None = Field(default=None, description="Product description")
    brand: str | None = Field(default=None, description="Product brand")
    category_path: str | None = Field(
        default=None, description="Category hierarchy path"
    )
    price: PriceSchema = Field(..., description="Unit price")
    quantity_available: int = Field(..., description="Available stock")
    image_url: str | None = Field(default=None, description="Product image URL")
    rating: float | None = Field(default=None, ge=0, le=5, description="Product rating")
    review_count: int | None = Field(default=None, description="Number of reviews")


class OfferResponse(BaseModel):
    """Response for a merchant offer."""

    id: str = Field(..., description="Unique offer identifier")
    intent_id: str = Field(..., description="Associated intent identifier")
    merchant_id: str = Field(..., description="Merchant identifier")
    items: list[OfferItemSchema] = Field(..., description="Product items in this offer")
    item_count: int = Field(..., description="Number of items")
    lowest_price: PriceSchema | None = Field(
        default=None, description="Lowest price item"
    )
    highest_price: PriceSchema | None = Field(
        default=None, description="Highest price item"
    )
    expires_at: datetime | None = Field(
        default=None, description="When this offer expires"
    )
    is_expired: bool = Field(default=False, description="Whether offer has expired")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Offer metadata"
    )
    created_at: datetime = Field(..., description="When the offer was created")


class OffersListResponse(PaginatedResponse):
    """Paginated list of offers for an intent."""

    items: list[OfferResponse] = Field(..., description="List of offers")
    intent_id: str = Field(..., description="Associated intent identifier")


class OfferSummarySchema(BaseModel):
    """Summary of an offer for listing."""

    id: str = Field(..., description="Unique offer identifier")
    merchant_id: str = Field(..., description="Merchant identifier")
    item_count: int = Field(..., description="Number of items")
    lowest_price: PriceSchema | None = Field(
        default=None, description="Lowest price item"
    )
    is_expired: bool = Field(default=False, description="Whether offer has expired")


# ============================================================================
# Merchant Schemas
# ============================================================================


class MerchantSchema(BaseModel):
    """Merchant information."""

    id: str = Field(..., description="Merchant identifier")
    name: str = Field(..., description="Merchant display name")
    url: str = Field(..., description="Merchant API base URL")
    enabled: bool = Field(..., description="Whether merchant is enabled")


class MerchantListResponse(BaseModel):
    """List of registered merchants."""

    merchants: list[MerchantSchema] = Field(..., description="List of merchants")
    total: int = Field(..., description="Total number of merchants")


# ============================================================================
# Checkout Schemas
# ============================================================================


class CheckoutStatusEnum(str, Enum):
    """Checkout session status."""

    CREATED = "created"
    QUOTED = "quoted"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CheckoutItemRequest(BaseModel):
    """Item to add to checkout."""

    product_id: str = Field(..., description="Product ID")
    variant_id: str | None = Field(default=None, description="Variant ID if applicable")
    quantity: int = Field(..., ge=1, description="Quantity to purchase")


class CheckoutCreateRequest(BaseModel):
    """Request to create a checkout from an offer."""

    offer_id: str = Field(..., description="Offer ID to create checkout from")
    items: list[CheckoutItemRequest] = Field(
        ..., min_length=1, description="Items to include in checkout"
    )
    idempotency_key: str | None = Field(
        default=None, description="Idempotency key for duplicate request detection"
    )


class CheckoutQuoteRequest(BaseModel):
    """Request to get a quote for a checkout."""

    items: list[CheckoutItemRequest] = Field(
        ..., min_length=1, description="Items to quote"
    )
    customer_email: str | None = Field(
        default=None, description="Customer email for receipt"
    )


class CheckoutApproveRequest(BaseModel):
    """Request to approve a checkout."""

    approved_by: str = Field(
        default="user", description="Identifier of who is approving"
    )


class CheckoutConfirmRequest(BaseModel):
    """Request to confirm a checkout (execute purchase)."""

    payment_method: str = Field(
        default="test_card", description="Payment method identifier"
    )
    idempotency_key: str | None = Field(
        default=None, description="Idempotency key for duplicate request detection"
    )


class CheckoutItemSchema(BaseModel):
    """Item in a checkout with pricing."""

    product_id: str = Field(..., description="Product ID")
    variant_id: str | None = Field(default=None, description="Variant ID")
    sku: str = Field(..., description="Product SKU")
    title: str = Field(..., description="Product title")
    unit_price: PriceSchema = Field(..., description="Unit price")
    quantity: int = Field(..., ge=1, description="Quantity")
    line_total: PriceSchema = Field(..., description="Line total")


class FrozenReceiptItemSchema(BaseModel):
    """Item in a frozen receipt."""

    product_id: str = Field(..., description="Product ID")
    variant_id: str | None = Field(default=None, description="Variant ID")
    sku: str = Field(..., description="Product SKU")
    title: str = Field(..., description="Product title")
    unit_price_cents: int = Field(..., description="Unit price in cents at freeze time")
    quantity: int = Field(..., description="Quantity")
    currency: str = Field(default="USD", description="Currency")


class FrozenReceiptSchema(BaseModel):
    """Frozen receipt for approval tracking."""

    hash: str = Field(..., description="Receipt hash for change detection")
    items: list[FrozenReceiptItemSchema] = Field(..., description="Frozen items")
    subtotal_cents: int = Field(..., description="Subtotal at freeze time")
    tax_cents: int = Field(..., description="Tax at freeze time")
    shipping_cents: int = Field(..., description="Shipping at freeze time")
    total_cents: int = Field(..., description="Total at freeze time")
    currency: str = Field(default="USD", description="Currency")
    frozen_at: str = Field(..., description="When receipt was frozen (ISO format)")


class AuditEntrySchema(BaseModel):
    """Audit trail entry."""

    timestamp: datetime = Field(..., description="When action occurred")
    action: str = Field(..., description="Action performed")
    from_status: str | None = Field(default=None, description="Previous status")
    to_status: str | None = Field(default=None, description="New status")
    actor: str | None = Field(default=None, description="Who performed action")
    details: dict[str, Any] | None = Field(default=None, description="Additional details")


class CheckoutResponse(BaseModel):
    """Checkout session response."""

    id: str = Field(..., description="Checkout ID")
    offer_id: str = Field(..., description="Source offer ID")
    merchant_id: str = Field(..., description="Merchant ID")
    status: CheckoutStatusEnum = Field(..., description="Current status")
    items: list[CheckoutItemSchema] = Field(
        default_factory=list, description="Checkout items"
    )
    subtotal: PriceSchema | None = Field(default=None, description="Subtotal")
    tax: PriceSchema | None = Field(default=None, description="Tax")
    shipping: PriceSchema | None = Field(default=None, description="Shipping")
    total: PriceSchema | None = Field(default=None, description="Total")
    merchant_checkout_id: str | None = Field(
        default=None, description="Merchant's checkout session ID"
    )
    receipt_hash: str | None = Field(
        default=None, description="Current receipt hash from merchant"
    )
    frozen_receipt: FrozenReceiptSchema | None = Field(
        default=None, description="Frozen receipt for approval tracking"
    )
    merchant_order_id: str | None = Field(
        default=None, description="Merchant order ID after confirmation"
    )
    approved_by: str | None = Field(default=None, description="Who approved")
    approved_at: datetime | None = Field(default=None, description="When approved")
    confirmed_at: datetime | None = Field(default=None, description="When confirmed")
    expires_at: datetime | None = Field(default=None, description="When checkout expires")
    failure_reason: str | None = Field(
        default=None, description="Failure reason if failed"
    )
    audit_trail: list[AuditEntrySchema] = Field(
        default_factory=list, description="State transition audit trail"
    )
    created_at: datetime = Field(..., description="When created")
    updated_at: datetime = Field(..., description="When last updated")


class CheckoutConfirmResponse(BaseModel):
    """Response after checkout confirmation."""

    checkout_id: str = Field(..., description="Checkout ID")
    merchant_order_id: str = Field(..., description="Merchant's order ID")
    order_id: str | None = Field(default=None, description="CartPilot order ID")
    status: CheckoutStatusEnum = Field(..., description="Final status")
    total: PriceSchema = Field(..., description="Total charged")
    confirmed_at: datetime = Field(..., description="Confirmation timestamp")


class ReapprovalRequiredResponse(BaseModel):
    """Response when re-approval is required due to price change."""

    error_code: str = Field(default="REAPPROVAL_REQUIRED", description="Error code")
    message: str = Field(..., description="Error message")
    checkout_id: str = Field(..., description="Checkout ID")
    original_total: PriceSchema = Field(..., description="Original approved total")
    new_total: PriceSchema = Field(..., description="New total after price change")
    price_difference: PriceSchema = Field(..., description="Price difference")


class CheckoutsListResponse(PaginatedResponse):
    """Paginated list of checkouts."""

    items: list[CheckoutResponse] = Field(..., description="List of checkouts")


# ============================================================================
# Order Schemas
# ============================================================================


class OrderStatusEnum(str, Enum):
    """Order lifecycle status."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    RETURNED = "returned"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class OrderAddressSchema(BaseModel):
    """Shipping or billing address."""

    line1: str = Field(..., description="Address line 1")
    line2: str | None = Field(default=None, description="Address line 2")
    city: str = Field(..., description="City")
    state: str | None = Field(default=None, description="State/Province")
    postal_code: str = Field(..., description="Postal/ZIP code")
    country: str = Field(..., description="Country code (ISO 3166-1 alpha-2)")


class OrderCustomerSchema(BaseModel):
    """Customer information for an order."""

    email: str = Field(..., description="Customer email")
    name: str | None = Field(default=None, description="Customer full name")
    phone: str | None = Field(default=None, description="Customer phone number")


class OrderItemSchema(BaseModel):
    """Item in an order."""

    product_id: str = Field(..., description="Product ID")
    variant_id: str | None = Field(default=None, description="Variant ID")
    sku: str | None = Field(default=None, description="Product SKU")
    title: str = Field(..., description="Product title")
    quantity: int = Field(..., ge=1, description="Quantity ordered")
    unit_price: PriceSchema = Field(..., description="Unit price at time of order")
    line_total: PriceSchema = Field(..., description="Line total")


class OrderStatusHistorySchema(BaseModel):
    """Status history entry for audit trail."""

    from_status: str | None = Field(default=None, description="Previous status")
    to_status: str = Field(..., description="New status")
    reason: str | None = Field(default=None, description="Reason for transition")
    actor: str | None = Field(default=None, description="Who initiated transition")
    metadata: dict[str, Any] | None = Field(default=None, description="Additional data")
    created_at: str = Field(..., description="When transition occurred")


class OrderResponse(BaseModel):
    """Order details response."""

    id: str = Field(..., description="Order ID")
    checkout_id: str = Field(..., description="Source checkout ID")
    merchant_id: str = Field(..., description="Merchant ID")
    merchant_order_id: str | None = Field(
        default=None, description="Merchant's order reference"
    )
    status: OrderStatusEnum = Field(..., description="Current order status")
    customer: OrderCustomerSchema = Field(..., description="Customer information")
    shipping_address: OrderAddressSchema = Field(..., description="Shipping address")
    billing_address: OrderAddressSchema | None = Field(
        default=None, description="Billing address (if different)"
    )
    items: list[OrderItemSchema] = Field(..., description="Order items")
    subtotal: PriceSchema = Field(..., description="Subtotal")
    tax: PriceSchema = Field(..., description="Tax")
    shipping: PriceSchema = Field(..., description="Shipping cost")
    total: PriceSchema = Field(..., description="Order total")
    tracking_number: str | None = Field(
        default=None, description="Shipment tracking number"
    )
    carrier: str | None = Field(default=None, description="Shipping carrier")
    cancelled_reason: str | None = Field(
        default=None, description="Cancellation reason if cancelled"
    )
    cancelled_by: str | None = Field(
        default=None, description="Who cancelled (customer/merchant/system)"
    )
    refund_amount: PriceSchema | None = Field(
        default=None, description="Refund amount if refunded"
    )
    refund_reason: str | None = Field(default=None, description="Refund reason")
    status_history: list[OrderStatusHistorySchema] = Field(
        default_factory=list, description="Order status history"
    )
    created_at: datetime = Field(..., description="When order was created")
    updated_at: datetime = Field(..., description="When order was last updated")
    confirmed_at: datetime | None = Field(
        default=None, description="When order was confirmed"
    )
    shipped_at: datetime | None = Field(default=None, description="When order shipped")
    delivered_at: datetime | None = Field(
        default=None, description="When order was delivered"
    )
    cancelled_at: datetime | None = Field(
        default=None, description="When order was cancelled"
    )
    refunded_at: datetime | None = Field(
        default=None, description="When order was refunded"
    )


class OrderSummarySchema(BaseModel):
    """Order summary for listings."""

    id: str = Field(..., description="Order ID")
    merchant_id: str = Field(..., description="Merchant ID")
    merchant_order_id: str | None = Field(
        default=None, description="Merchant's order reference"
    )
    status: OrderStatusEnum = Field(..., description="Current status")
    total: PriceSchema = Field(..., description="Order total")
    item_count: int = Field(..., description="Number of items")
    customer_email: str = Field(..., description="Customer email")
    created_at: datetime = Field(..., description="When created")


class OrdersListResponse(PaginatedResponse):
    """Paginated list of orders."""

    items: list[OrderSummarySchema] = Field(..., description="List of orders")


class OrderCancelRequest(BaseModel):
    """Request to cancel an order."""

    reason: str = Field(..., description="Cancellation reason")
    cancelled_by: str = Field(
        default="customer", description="Who is cancelling (customer/merchant/system)"
    )


class OrderRefundRequest(BaseModel):
    """Request to refund an order."""

    refund_amount_cents: int | None = Field(
        default=None, description="Refund amount in cents (None for full refund)"
    )
    reason: str = Field(default="", description="Refund reason")


class SimulateTimeRequest(BaseModel):
    """Request to simulate time advancement for order."""

    steps: int = Field(
        default=1,
        ge=1,
        le=3,
        description="Number of status steps to advance (1-3)",
    )
