"""SQLAlchemy models for database tables.

Provides ORM models for event_log, idempotency_responses, orders, and related tables.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.infrastructure.database import Base


# ============================================================================
# Order Models
# ============================================================================


class OrderModel(Base):
    """Order model for database persistence.

    Represents an order created after checkout confirmation.
    Tracks the full order lifecycle from creation to delivery/refund.
    """

    __tablename__ = "orders"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    checkout_id = Column(String(36), nullable=False, index=True)
    merchant_id = Column(String(100), nullable=False, index=True)
    merchant_order_id = Column(String(100), nullable=True, index=True)
    status = Column(String(20), nullable=False, default="pending", index=True)

    # Customer info
    customer_email = Column(String(255), nullable=False)
    customer_name = Column(String(255), nullable=True)
    customer_phone = Column(String(50), nullable=True)

    # Shipping address
    shipping_line1 = Column(String(255), nullable=False)
    shipping_line2 = Column(String(255), nullable=True)
    shipping_city = Column(String(100), nullable=False)
    shipping_state = Column(String(100), nullable=True)
    shipping_postal_code = Column(String(20), nullable=False)
    shipping_country = Column(String(2), nullable=False)

    # Billing address
    billing_line1 = Column(String(255), nullable=True)
    billing_line2 = Column(String(255), nullable=True)
    billing_city = Column(String(100), nullable=True)
    billing_state = Column(String(100), nullable=True)
    billing_postal_code = Column(String(20), nullable=True)
    billing_country = Column(String(2), nullable=True)

    # Totals
    subtotal_cents = Column(Integer, nullable=False)
    tax_cents = Column(Integer, nullable=False, default=0)
    shipping_cents = Column(Integer, nullable=False, default=0)
    total_cents = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False, default="USD")

    # Shipping info
    tracking_number = Column(String(100), nullable=True)
    carrier = Column(String(100), nullable=True)

    # Cancellation/refund
    cancelled_reason = Column(Text, nullable=True)
    cancelled_by = Column(String(50), nullable=True)
    refund_amount_cents = Column(Integer, nullable=True)
    refund_reason = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    shipped_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    refunded_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    items = relationship(
        "OrderItemModel",
        back_populates="order",
        cascade="all, delete-orphan",
    )
    status_history = relationship(
        "OrderStatusHistoryModel",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderStatusHistoryModel.created_at",
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "checkout_id": self.checkout_id,
            "merchant_id": self.merchant_id,
            "merchant_order_id": self.merchant_order_id,
            "status": self.status,
            "customer_email": self.customer_email,
            "customer_name": self.customer_name,
            "total_cents": self.total_cents,
            "currency": self.currency,
            "tracking_number": self.tracking_number,
            "carrier": self.carrier,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "shipped_at": self.shipped_at.isoformat() if self.shipped_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
        }


class OrderItemModel(Base):
    """Order item model for database persistence.

    Represents an item within an order.
    """

    __tablename__ = "order_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    order_id = Column(
        String(36),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id = Column(String(100), nullable=False)
    variant_id = Column(String(100), nullable=True)
    sku = Column(String(100), nullable=True)
    title = Column(String(500), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price_cents = Column(Integer, nullable=False)
    line_total_cents = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    order = relationship("OrderModel", back_populates="items")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "product_id": self.product_id,
            "variant_id": self.variant_id,
            "sku": self.sku,
            "title": self.title,
            "quantity": self.quantity,
            "unit_price_cents": self.unit_price_cents,
            "line_total_cents": self.line_total_cents,
            "currency": self.currency,
        }


class OrderStatusHistoryModel(Base):
    """Order status history model for audit trail.

    Tracks all status transitions for an order.
    """

    __tablename__ = "order_status_history"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    order_id = Column(
        String(36),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_status = Column(String(20), nullable=True)
    to_status = Column(String(20), nullable=False)
    reason = Column(Text, nullable=True)
    actor = Column(String(100), nullable=True)
    metadata = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    order = relationship("OrderModel", back_populates="status_history")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "order_id": self.order_id,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "reason": self.reason,
            "actor": self.actor,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ============================================================================
# Event Log Models
# ============================================================================


class EventLog(Base):
    """Event log model for webhook event tracking and deduplication.

    Stores all received webhook events for:
    - Deduplication by event_id
    - Audit trail
    - Retry handling
    - Out-of-order event tolerance
    """

    __tablename__ = "event_log"

    event_id = Column(String(36), primary_key=True)
    merchant_id = Column(String(100), nullable=False, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    payload_hash = Column(String(64), nullable=False)
    payload = Column(JSONB, nullable=False)
    received_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    processed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="received")
    error_message = Column(Text, nullable=True)
    correlation_id = Column(String(36), nullable=True, index=True)
    retry_count = Column(Integer, nullable=False, default=0)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_id": self.event_id,
            "merchant_id": self.merchant_id,
            "event_type": self.event_type,
            "payload_hash": self.payload_hash,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "status": self.status,
            "correlation_id": self.correlation_id,
        }


class IdempotencyResponse(Base):
    """Idempotency response cache model.

    Stores responses for idempotent requests to return
    consistent results on retries.
    """

    __tablename__ = "idempotency_responses"

    idempotency_key = Column(String(100), primary_key=True)
    endpoint = Column(String(200), primary_key=True)
    method = Column(String(10), primary_key=True)
    response_status = Column(Integer, nullable=False)
    response_body = Column(JSONB, nullable=False)
    response_headers = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    expires_at = Column(DateTime(timezone=True), nullable=False)
    request_hash = Column(String(64), nullable=True)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "idempotency_key": self.idempotency_key,
            "endpoint": self.endpoint,
            "method": self.method,
            "response_status": self.response_status,
            "response_body": self.response_body,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }
