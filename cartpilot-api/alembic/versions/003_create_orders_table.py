"""Create orders and order_items tables.

Revision ID: 003
Revises: 002
Create Date: 2026-01-20

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create orders and order_items tables."""
    # Create orders table
    op.create_table(
        "orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("checkout_id", sa.String(36), nullable=False, index=True),
        sa.Column("merchant_id", sa.String(100), nullable=False, index=True),
        sa.Column("merchant_order_id", sa.String(100), nullable=True, index=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            default="pending",
            index=True,
        ),
        # Customer info
        sa.Column("customer_email", sa.String(255), nullable=False),
        sa.Column("customer_name", sa.String(255), nullable=True),
        sa.Column("customer_phone", sa.String(50), nullable=True),
        # Shipping address
        sa.Column("shipping_line1", sa.String(255), nullable=False),
        sa.Column("shipping_line2", sa.String(255), nullable=True),
        sa.Column("shipping_city", sa.String(100), nullable=False),
        sa.Column("shipping_state", sa.String(100), nullable=True),
        sa.Column("shipping_postal_code", sa.String(20), nullable=False),
        sa.Column("shipping_country", sa.String(2), nullable=False),
        # Billing address
        sa.Column("billing_line1", sa.String(255), nullable=True),
        sa.Column("billing_line2", sa.String(255), nullable=True),
        sa.Column("billing_city", sa.String(100), nullable=True),
        sa.Column("billing_state", sa.String(100), nullable=True),
        sa.Column("billing_postal_code", sa.String(20), nullable=True),
        sa.Column("billing_country", sa.String(2), nullable=True),
        # Totals
        sa.Column("subtotal_cents", sa.Integer, nullable=False),
        sa.Column("tax_cents", sa.Integer, nullable=False, default=0),
        sa.Column("shipping_cents", sa.Integer, nullable=False, default=0),
        sa.Column("total_cents", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, default="USD"),
        # Shipping info
        sa.Column("tracking_number", sa.String(100), nullable=True),
        sa.Column("carrier", sa.String(100), nullable=True),
        # Cancellation/refund
        sa.Column("cancelled_reason", sa.Text, nullable=True),
        sa.Column("cancelled_by", sa.String(50), nullable=True),
        sa.Column("refund_amount_cents", sa.Integer, nullable=True),
        sa.Column("refund_reason", sa.Text, nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Create order_items table
    op.create_table(
        "order_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "order_id",
            sa.String(36),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("product_id", sa.String(100), nullable=False),
        sa.Column("variant_id", sa.String(100), nullable=True),
        sa.Column("sku", sa.String(100), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("unit_price_cents", sa.Integer, nullable=False),
        sa.Column("line_total_cents", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, default="USD"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Create order status history table for audit trail
    op.create_table(
        "order_status_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "order_id",
            sa.String(36),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("from_status", sa.String(20), nullable=True),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("actor", sa.String(100), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    """Drop orders, order_items, and order_status_history tables."""
    op.drop_table("order_status_history")
    op.drop_table("order_items")
    op.drop_table("orders")
