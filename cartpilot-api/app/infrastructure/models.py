"""SQLAlchemy models for database tables.

Provides ORM models for event_log, idempotency_responses, and related tables.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.infrastructure.database import Base


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
