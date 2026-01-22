"""Create event_log and idempotency_responses tables.

Revision ID: 002
Revises: 001
Create Date: 2026-01-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create event_log and idempotency_responses tables."""
    # Event log table for webhook events
    op.create_table(
        'event_log',
        sa.Column('event_id', sa.String(36), primary_key=True),
        sa.Column('merchant_id', sa.String(100), nullable=False, index=True),
        sa.Column('event_type', sa.String(100), nullable=False, index=True),
        sa.Column('payload_hash', sa.String(64), nullable=False),
        sa.Column('payload', postgresql.JSONB, nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='received'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('correlation_id', sa.String(36), nullable=True, index=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
    )

    # Create index for deduplication lookup
    op.create_index(
        'ix_event_log_merchant_event_id',
        'event_log',
        ['merchant_id', 'event_id'],
        unique=True,
    )

    # Create index for status-based queries
    op.create_index(
        'ix_event_log_status_received_at',
        'event_log',
        ['status', 'received_at'],
    )

    # Idempotency responses table
    op.create_table(
        'idempotency_responses',
        sa.Column('idempotency_key', sa.String(100), nullable=False),
        sa.Column('endpoint', sa.String(200), nullable=False),
        sa.Column('method', sa.String(10), nullable=False),
        sa.Column('response_status', sa.Integer(), nullable=False),
        sa.Column('response_body', postgresql.JSONB, nullable=False),
        sa.Column('response_headers', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('request_hash', sa.String(64), nullable=True),
        # Primary key on idempotency_key + endpoint + method
        sa.PrimaryKeyConstraint('idempotency_key', 'endpoint', 'method'),
    )

    # Create index for expiration cleanup
    op.create_index(
        'ix_idempotency_responses_expires_at',
        'idempotency_responses',
        ['expires_at'],
    )


def downgrade() -> None:
    """Drop event_log and idempotency_responses tables."""
    op.drop_table('idempotency_responses')
    op.drop_table('event_log')
