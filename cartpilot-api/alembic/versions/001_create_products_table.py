"""Create products and product_variants tables.

Revision ID: 001
Revises:
Create Date: 2026-01-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create products and product_variants tables."""
    # Products table
    op.create_table(
        'products',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('merchant_id', sa.String(100), nullable=False, index=True),
        sa.Column('sku', sa.String(100), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('brand', sa.String(100), nullable=False, index=True),
        sa.Column('category_id', sa.Integer(), nullable=False, index=True),
        sa.Column('category_path', sa.String(500), nullable=False),
        sa.Column('base_price', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False, server_default='USD'),
        sa.Column('rating', sa.Numeric(2, 1), nullable=False, server_default='0.0'),
        sa.Column('review_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('image_url', sa.String(1000), nullable=True),
        sa.Column('in_stock', sa.Boolean(), nullable=False, server_default='true', index=True),
        sa.Column('stock_quantity', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )

    # Create unique constraint on merchant_id + sku
    op.create_unique_constraint(
        'uq_products_merchant_sku',
        'products',
        ['merchant_id', 'sku'],
    )

    # Product variants table
    op.create_table(
        'product_variants',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column('product_id', postgresql.UUID(as_uuid=False), 
                  sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('sku_suffix', sa.String(50), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('color', sa.String(50), nullable=True),
        sa.Column('size', sa.String(50), nullable=True),
        sa.Column('price_modifier', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('in_stock', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('stock_quantity', sa.Integer(), nullable=False, server_default='50'),
    )

    # Create unique constraint on product_id + sku_suffix
    op.create_unique_constraint(
        'uq_variants_product_sku',
        'product_variants',
        ['product_id', 'sku_suffix'],
    )


def downgrade() -> None:
    """Drop products and product_variants tables."""
    op.drop_table('product_variants')
    op.drop_table('products')
