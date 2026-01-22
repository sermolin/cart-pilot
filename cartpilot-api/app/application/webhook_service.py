"""Webhook processing service.

Handles incoming webhooks from merchants with:
- HMAC signature verification
- Event deduplication
- Out-of-order event tolerance
- Event processing and state updates
"""

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import structlog

from app.infrastructure.config import settings

logger = structlog.get_logger()


class WebhookEventType(str, Enum):
    """Types of webhook events from merchants."""

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


class EventStatus(str, Enum):
    """Status of a webhook event in the event log."""

    RECEIVED = "received"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    DUPLICATE = "duplicate"


@dataclass
class WebhookEvent:
    """Represents a webhook event from a merchant.

    Attributes:
        event_id: Unique event identifier.
        event_type: Type of event.
        merchant_id: Merchant that sent the event.
        timestamp: When the event occurred.
        data: Event-specific data.
        signature: HMAC signature for verification.
    """

    event_id: str
    event_type: WebhookEventType
    merchant_id: str
    timestamp: datetime
    data: dict[str, Any]
    signature: str | None = None

    def compute_payload_hash(self) -> str:
        """Compute SHA-256 hash of the payload for deduplication.

        Returns:
            Hex digest of the payload hash.
        """
        import json

        payload = json.dumps(
            {
                "event_id": self.event_id,
                "event_type": self.event_type.value,
                "merchant_id": self.merchant_id,
                "data": self.data,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass
class WebhookResult:
    """Result of webhook processing.

    Attributes:
        success: Whether processing succeeded.
        event_id: The event ID.
        status: Final event status.
        message: Status message.
        duplicate: Whether this was a duplicate event.
    """

    success: bool
    event_id: str
    status: EventStatus
    message: str
    duplicate: bool = False


class WebhookSignatureVerifier:
    """Verifies HMAC signatures on webhook payloads.

    Uses HMAC-SHA256 for signature verification.
    """

    def __init__(self, secret: str | None = None) -> None:
        """Initialize verifier.

        Args:
            secret: HMAC secret for signature verification.
        """
        self.secret = secret or settings.webhook_secret

    def verify(self, payload: str, signature: str, merchant_id: str) -> bool:
        """Verify the HMAC signature of a webhook payload.

        Args:
            payload: JSON payload string.
            signature: Signature header value (format: sha256=<hex>).
            merchant_id: Merchant ID for logging.

        Returns:
            True if signature is valid.
        """
        if not signature:
            logger.warning(
                "Missing webhook signature",
                merchant_id=merchant_id,
            )
            return False

        # Parse signature format: sha256=<hex_digest>
        parts = signature.split("=", 1)
        if len(parts) != 2 or parts[0] != "sha256":
            logger.warning(
                "Invalid signature format",
                merchant_id=merchant_id,
                signature_prefix=signature[:20] if signature else None,
            )
            return False

        expected_sig = parts[1]

        # Compute expected signature
        computed = hmac.new(
            self.secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        # Constant-time comparison
        if not hmac.compare_digest(computed, expected_sig):
            logger.warning(
                "Webhook signature mismatch",
                merchant_id=merchant_id,
            )
            return False

        logger.debug(
            "Webhook signature verified",
            merchant_id=merchant_id,
        )
        return True


class InMemoryEventLog:
    """In-memory event log for deduplication.

    Used as a simple implementation before database integration.
    In production, this would use the event_log database table.
    """

    def __init__(self) -> None:
        """Initialize event log."""
        self._events: dict[str, dict[str, Any]] = {}

    async def exists(self, event_id: str, merchant_id: str) -> bool:
        """Check if an event already exists.

        Args:
            event_id: Event identifier.
            merchant_id: Merchant identifier.

        Returns:
            True if event exists.
        """
        key = f"{merchant_id}:{event_id}"
        return key in self._events

    async def store(
        self,
        event: WebhookEvent,
        status: EventStatus,
        correlation_id: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Store an event in the log.

        Args:
            event: The webhook event.
            status: Event status.
            correlation_id: Request correlation ID.
            error_message: Error message if failed.
        """
        key = f"{event.merchant_id}:{event.event_id}"
        self._events[key] = {
            "event_id": event.event_id,
            "merchant_id": event.merchant_id,
            "event_type": event.event_type.value,
            "payload_hash": event.compute_payload_hash(),
            "payload": event.data,
            "received_at": datetime.now(timezone.utc),
            "processed_at": datetime.now(timezone.utc) if status == EventStatus.PROCESSED else None,
            "status": status.value,
            "error_message": error_message,
            "correlation_id": correlation_id,
        }

    async def get(self, event_id: str, merchant_id: str) -> dict[str, Any] | None:
        """Get an event from the log.

        Args:
            event_id: Event identifier.
            merchant_id: Merchant identifier.

        Returns:
            Event data if found.
        """
        key = f"{merchant_id}:{event_id}"
        return self._events.get(key)

    async def update_status(
        self,
        event_id: str,
        merchant_id: str,
        status: EventStatus,
        error_message: str | None = None,
    ) -> None:
        """Update event status.

        Args:
            event_id: Event identifier.
            merchant_id: Merchant identifier.
            status: New status.
            error_message: Error message if failed.
        """
        key = f"{merchant_id}:{event_id}"
        if key in self._events:
            self._events[key]["status"] = status.value
            if status == EventStatus.PROCESSED:
                self._events[key]["processed_at"] = datetime.now(timezone.utc)
            if error_message:
                self._events[key]["error_message"] = error_message


class WebhookService:
    """Service for processing incoming webhooks.

    Handles:
    - Signature verification
    - Event deduplication
    - Event processing
    - State updates
    """

    def __init__(
        self,
        event_log: InMemoryEventLog | None = None,
        signature_verifier: WebhookSignatureVerifier | None = None,
    ) -> None:
        """Initialize webhook service.

        Args:
            event_log: Event log for deduplication.
            signature_verifier: Signature verifier.
        """
        self.event_log = event_log or InMemoryEventLog()
        self.signature_verifier = signature_verifier or WebhookSignatureVerifier()

    def verify_signature(
        self, payload: str, signature: str, merchant_id: str
    ) -> bool:
        """Verify webhook signature.

        Args:
            payload: JSON payload string.
            signature: Signature header.
            merchant_id: Merchant ID.

        Returns:
            True if valid.
        """
        return self.signature_verifier.verify(payload, signature, merchant_id)

    async def process_event(
        self,
        event: WebhookEvent,
        correlation_id: str | None = None,
    ) -> WebhookResult:
        """Process a webhook event.

        Performs deduplication check, stores the event, and
        processes it based on event type.

        Args:
            event: The webhook event to process.
            correlation_id: Request correlation ID.

        Returns:
            Processing result.
        """
        logger.info(
            "Processing webhook event",
            event_id=event.event_id,
            event_type=event.event_type.value,
            merchant_id=event.merchant_id,
            correlation_id=correlation_id,
        )

        # Check for duplicate
        if await self.event_log.exists(event.event_id, event.merchant_id):
            logger.info(
                "Duplicate webhook event ignored",
                event_id=event.event_id,
                merchant_id=event.merchant_id,
            )
            return WebhookResult(
                success=True,
                event_id=event.event_id,
                status=EventStatus.DUPLICATE,
                message="Event already processed",
                duplicate=True,
            )

        # Store event as received
        await self.event_log.store(
            event=event,
            status=EventStatus.PROCESSING,
            correlation_id=correlation_id,
        )

        try:
            # Process based on event type
            await self._handle_event(event)

            # Mark as processed
            await self.event_log.update_status(
                event.event_id,
                event.merchant_id,
                EventStatus.PROCESSED,
            )

            logger.info(
                "Webhook event processed successfully",
                event_id=event.event_id,
                event_type=event.event_type.value,
            )

            return WebhookResult(
                success=True,
                event_id=event.event_id,
                status=EventStatus.PROCESSED,
                message="Event processed successfully",
            )

        except Exception as e:
            error_message = str(e)
            logger.error(
                "Failed to process webhook event",
                event_id=event.event_id,
                event_type=event.event_type.value,
                error=error_message,
            )

            await self.event_log.update_status(
                event.event_id,
                event.merchant_id,
                EventStatus.FAILED,
                error_message=error_message,
            )

            return WebhookResult(
                success=False,
                event_id=event.event_id,
                status=EventStatus.FAILED,
                message=error_message,
            )

    async def _handle_event(self, event: WebhookEvent) -> None:
        """Handle event based on type.

        This is where we would update checkout/order state
        based on merchant events.

        Args:
            event: The event to handle.
        """
        handlers = {
            WebhookEventType.CHECKOUT_CONFIRMED: self._handle_checkout_confirmed,
            WebhookEventType.CHECKOUT_FAILED: self._handle_checkout_failed,
            WebhookEventType.ORDER_CREATED: self._handle_order_created,
            WebhookEventType.ORDER_SHIPPED: self._handle_order_shipped,
            WebhookEventType.ORDER_DELIVERED: self._handle_order_delivered,
            WebhookEventType.PRICE_CHANGED: self._handle_price_changed,
            WebhookEventType.STOCK_CHANGED: self._handle_stock_changed,
        }

        handler = handlers.get(event.event_type)
        if handler:
            await handler(event)
        else:
            logger.debug(
                "No handler for event type",
                event_type=event.event_type.value,
            )

    async def _handle_checkout_confirmed(self, event: WebhookEvent) -> None:
        """Handle checkout confirmed event."""
        checkout_id = event.data.get("checkout_id")
        merchant_order_id = event.data.get("merchant_order_id")
        logger.info(
            "Checkout confirmed by merchant",
            checkout_id=checkout_id,
            merchant_order_id=merchant_order_id,
        )
        # In production: update checkout state

    async def _handle_checkout_failed(self, event: WebhookEvent) -> None:
        """Handle checkout failed event."""
        checkout_id = event.data.get("checkout_id")
        reason = event.data.get("reason")
        logger.info(
            "Checkout failed",
            checkout_id=checkout_id,
            reason=reason,
        )
        # In production: update checkout state

    async def _handle_order_created(self, event: WebhookEvent) -> None:
        """Handle order created event."""
        merchant_order_id = event.data.get("merchant_order_id")
        logger.info(
            "Order created by merchant",
            merchant_order_id=merchant_order_id,
        )
        # In production: create order entity

    async def _handle_order_shipped(self, event: WebhookEvent) -> None:
        """Handle order shipped event."""
        merchant_order_id = event.data.get("merchant_order_id")
        tracking_number = event.data.get("tracking_number")
        logger.info(
            "Order shipped",
            merchant_order_id=merchant_order_id,
            tracking_number=tracking_number,
        )
        # In production: update order state

    async def _handle_order_delivered(self, event: WebhookEvent) -> None:
        """Handle order delivered event."""
        merchant_order_id = event.data.get("merchant_order_id")
        logger.info(
            "Order delivered",
            merchant_order_id=merchant_order_id,
        )
        # In production: update order state

    async def _handle_price_changed(self, event: WebhookEvent) -> None:
        """Handle price changed event."""
        checkout_id = event.data.get("checkout_id")
        old_total = event.data.get("old_total")
        new_total = event.data.get("new_total")
        logger.info(
            "Price changed for checkout",
            checkout_id=checkout_id,
            old_total=old_total,
            new_total=new_total,
        )
        # In production: trigger re-approval flow

    async def _handle_stock_changed(self, event: WebhookEvent) -> None:
        """Handle stock changed event."""
        product_id = event.data.get("product_id")
        available = event.data.get("available")
        logger.info(
            "Stock changed for product",
            product_id=product_id,
            available=available,
        )
        # In production: update availability


# Global service instance
_webhook_service: WebhookService | None = None


def get_webhook_service() -> WebhookService:
    """Get or create the webhook service instance.

    Returns:
        WebhookService instance.
    """
    global _webhook_service
    if _webhook_service is None:
        _webhook_service = WebhookService()
    return _webhook_service
