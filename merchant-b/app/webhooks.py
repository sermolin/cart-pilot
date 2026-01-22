"""Webhook sender service for Merchant B (Chaos Mode).

Sends webhook notifications to CartPilot with chaos mode behaviors:
- Duplicate webhooks (same event sent multiple times)
- Delayed webhooks (webhooks sent after a delay)
- Out-of-order webhooks (webhooks sent in wrong sequence)
"""

import asyncio
import hashlib
import hmac
import random
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from app.schemas import ChaosScenario, WebhookEventType, WebhookPayloadSchema

if TYPE_CHECKING:
    from app.chaos import ChaosController

logger = structlog.get_logger()


class WebhookSender:
    """Sends webhook events to CartPilot API with chaos mode support.

    Handles HMAC signing and async delivery of webhook events.
    Supports chaos scenarios for resilience testing.
    """

    def __init__(
        self,
        webhook_url: str,
        webhook_secret: str,
        merchant_id: str = "merchant-b",
        chaos_controller: "ChaosController | None" = None,
    ) -> None:
        """Initialize webhook sender.

        Args:
            webhook_url: URL to send webhooks to.
            webhook_secret: Secret for HMAC signing.
            merchant_id: Merchant identifier.
            chaos_controller: Chaos controller for triggering scenarios.
        """
        self.webhook_url = webhook_url
        self.webhook_secret = webhook_secret
        self.merchant_id = merchant_id
        self.chaos_controller = chaos_controller
        self._client = httpx.AsyncClient(timeout=10.0)
        self._pending_webhooks: list[dict] = []  # For out-of-order chaos

    def set_chaos_controller(self, controller: "ChaosController") -> None:
        """Set the chaos controller.

        Args:
            controller: Chaos controller instance.
        """
        self.chaos_controller = controller

    def _generate_event_id(self) -> str:
        """Generate unique event ID."""
        return str(uuid.uuid4())

    def _sign_payload(self, payload: str) -> str:
        """Generate HMAC signature for payload.

        Args:
            payload: JSON payload string.

        Returns:
            HMAC-SHA256 signature.
        """
        signature = hmac.new(
            self.webhook_secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"sha256={signature}"

    def _build_payload(
        self, event_type: WebhookEventType, data: dict[str, Any], event_id: str | None = None
    ) -> WebhookPayloadSchema:
        """Build webhook payload.

        Args:
            event_type: Type of event.
            data: Event-specific data.
            event_id: Optional event ID (for duplicates).

        Returns:
            Webhook payload schema.
        """
        return WebhookPayloadSchema(
            event_id=event_id or self._generate_event_id(),
            event_type=event_type,
            merchant_id=self.merchant_id,
            timestamp=datetime.now(timezone.utc),
            data=data,
        )

    async def _deliver_webhook(
        self, payload: WebhookPayloadSchema, is_duplicate: bool = False
    ) -> bool:
        """Deliver a single webhook.

        Args:
            payload: Webhook payload.
            is_duplicate: Whether this is a duplicate delivery.

        Returns:
            True if delivery succeeded.
        """
        payload_json = payload.model_dump_json()
        signature = self._sign_payload(payload_json)

        headers = {
            "Content-Type": "application/json",
            "X-Merchant-Signature": signature,
            "X-Merchant-Id": self.merchant_id,
            "X-Event-Id": payload.event_id,
        }

        if is_duplicate:
            headers["X-Is-Retry"] = "true"

        try:
            response = await self._client.post(
                self.webhook_url,
                content=payload_json,
                headers=headers,
            )

            if response.status_code == 200:
                logger.info(
                    "Webhook delivered successfully",
                    event_type=payload.event_type.value,
                    event_id=payload.event_id,
                    status_code=response.status_code,
                    is_duplicate=is_duplicate,
                )
                return True
            else:
                logger.warning(
                    "Webhook delivery failed",
                    event_type=payload.event_type.value,
                    event_id=payload.event_id,
                    status_code=response.status_code,
                    response_body=response.text[:200],
                )
                return False

        except httpx.RequestError as e:
            logger.error(
                "Webhook delivery error",
                event_type=payload.event_type.value,
                event_id=payload.event_id,
                error=str(e),
            )
            return False

    async def send_event(
        self,
        event_type: WebhookEventType,
        data: dict[str, Any],
        checkout_id: str | None = None,
    ) -> bool:
        """Send webhook event to CartPilot with potential chaos behaviors.

        Args:
            event_type: Type of event.
            data: Event-specific data.
            checkout_id: Related checkout ID for logging.

        Returns:
            True if primary delivery succeeded.
        """
        payload = self._build_payload(event_type, data)

        # Check for chaos scenarios
        if self.chaos_controller:
            # Out-of-order webhook chaos
            if self.chaos_controller.should_trigger(ChaosScenario.OUT_OF_ORDER_WEBHOOK):
                self._pending_webhooks.append(
                    {
                        "payload": payload,
                        "checkout_id": checkout_id,
                    }
                )
                self.chaos_controller.log_event(
                    ChaosScenario.OUT_OF_ORDER_WEBHOOK,
                    checkout_id,
                    {
                        "event_type": event_type.value,
                        "event_id": payload.event_id,
                        "action": "queued",
                    },
                )
                logger.info(
                    "Webhook queued for out-of-order delivery",
                    event_type=event_type.value,
                    event_id=payload.event_id,
                )
                # Don't send now, it will be sent later
                return True

            # Delayed webhook chaos
            if self.chaos_controller.should_trigger(ChaosScenario.DELAYED_WEBHOOK):
                delay = self.chaos_controller.config.webhook_delay_seconds
                self.chaos_controller.log_event(
                    ChaosScenario.DELAYED_WEBHOOK,
                    checkout_id,
                    {
                        "event_type": event_type.value,
                        "event_id": payload.event_id,
                        "delay_seconds": delay,
                    },
                )
                logger.info(
                    "Delaying webhook delivery",
                    event_type=event_type.value,
                    event_id=payload.event_id,
                    delay=delay,
                )
                await asyncio.sleep(delay)

        # Send primary webhook
        success = await self._deliver_webhook(payload)

        # Duplicate webhook chaos
        if self.chaos_controller and self.chaos_controller.should_trigger(
            ChaosScenario.DUPLICATE_WEBHOOK
        ):
            duplicate_count = self.chaos_controller.config.duplicate_webhook_count
            self.chaos_controller.log_event(
                ChaosScenario.DUPLICATE_WEBHOOK,
                checkout_id,
                {
                    "event_type": event_type.value,
                    "event_id": payload.event_id,
                    "duplicate_count": duplicate_count,
                },
            )
            logger.info(
                "Sending duplicate webhooks",
                event_type=event_type.value,
                event_id=payload.event_id,
                count=duplicate_count,
            )

            # Send duplicates (with same event_id)
            for i in range(duplicate_count - 1):  # -1 because we already sent one
                await asyncio.sleep(0.1)  # Small delay between duplicates
                await self._deliver_webhook(payload, is_duplicate=True)

        return success

    async def flush_pending_webhooks(self) -> int:
        """Send all pending webhooks (for out-of-order chaos).

        Sends webhooks in random order to simulate out-of-order delivery.

        Returns:
            Number of webhooks sent.
        """
        if not self._pending_webhooks:
            return 0

        # Shuffle for random order
        webhooks = self._pending_webhooks.copy()
        random.shuffle(webhooks)
        self._pending_webhooks.clear()

        count = 0
        for webhook in webhooks:
            payload = webhook["payload"]
            checkout_id = webhook["checkout_id"]

            logger.info(
                "Flushing pending webhook (out-of-order)",
                event_type=payload.event_type.value,
                event_id=payload.event_id,
            )

            if self.chaos_controller:
                self.chaos_controller.log_event(
                    ChaosScenario.OUT_OF_ORDER_WEBHOOK,
                    checkout_id,
                    {
                        "event_type": payload.event_type.value,
                        "event_id": payload.event_id,
                        "action": "flushed",
                    },
                )

            await self._deliver_webhook(payload)
            count += 1

        return count

    async def send_checkout_created(
        self, checkout_id: str, total: int, currency: str
    ) -> bool:
        """Send checkout created event.

        Args:
            checkout_id: Checkout ID.
            total: Total amount in cents.
            currency: Currency code.

        Returns:
            True if delivery succeeded.
        """
        return await self.send_event(
            WebhookEventType.CHECKOUT_CREATED,
            {
                "checkout_id": checkout_id,
                "total": total,
                "currency": currency,
            },
            checkout_id=checkout_id,
        )

    async def send_checkout_quoted(
        self,
        checkout_id: str,
        total: int,
        currency: str,
        receipt_hash: str,
    ) -> bool:
        """Send checkout quoted event.

        Args:
            checkout_id: Checkout ID.
            total: Total amount in cents.
            currency: Currency code.
            receipt_hash: Receipt hash for verification.

        Returns:
            True if delivery succeeded.
        """
        return await self.send_event(
            WebhookEventType.CHECKOUT_QUOTED,
            {
                "checkout_id": checkout_id,
                "total": total,
                "currency": currency,
                "receipt_hash": receipt_hash,
            },
            checkout_id=checkout_id,
        )

    async def send_checkout_confirmed(
        self,
        checkout_id: str,
        merchant_order_id: str,
        total: int,
        currency: str,
    ) -> bool:
        """Send checkout confirmed event.

        Args:
            checkout_id: Checkout ID.
            merchant_order_id: Merchant's order ID.
            total: Total charged.
            currency: Currency code.

        Returns:
            True if delivery succeeded.
        """
        return await self.send_event(
            WebhookEventType.CHECKOUT_CONFIRMED,
            {
                "checkout_id": checkout_id,
                "merchant_order_id": merchant_order_id,
                "total": total,
                "currency": currency,
                "confirmed_at": datetime.now(timezone.utc).isoformat(),
            },
            checkout_id=checkout_id,
        )

    async def send_checkout_failed(
        self, checkout_id: str, reason: str, error_code: str
    ) -> bool:
        """Send checkout failed event.

        Args:
            checkout_id: Checkout ID.
            reason: Failure reason.
            error_code: Error code.

        Returns:
            True if delivery succeeded.
        """
        return await self.send_event(
            WebhookEventType.CHECKOUT_FAILED,
            {
                "checkout_id": checkout_id,
                "reason": reason,
                "error_code": error_code,
            },
            checkout_id=checkout_id,
        )

    async def send_order_created(
        self,
        checkout_id: str,
        merchant_order_id: str,
        total: int,
        currency: str,
        items: list[dict],
    ) -> bool:
        """Send order created event.

        Args:
            checkout_id: Original checkout ID.
            merchant_order_id: Merchant's order ID.
            total: Order total.
            currency: Currency code.
            items: Order items.

        Returns:
            True if delivery succeeded.
        """
        return await self.send_event(
            WebhookEventType.ORDER_CREATED,
            {
                "checkout_id": checkout_id,
                "merchant_order_id": merchant_order_id,
                "total": total,
                "currency": currency,
                "items": items,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            checkout_id=checkout_id,
        )

    async def send_order_shipped(
        self,
        merchant_order_id: str,
        tracking_number: str | None,
        carrier: str | None,
    ) -> bool:
        """Send order shipped event.

        Args:
            merchant_order_id: Merchant's order ID.
            tracking_number: Tracking number if available.
            carrier: Shipping carrier.

        Returns:
            True if delivery succeeded.
        """
        return await self.send_event(
            WebhookEventType.ORDER_SHIPPED,
            {
                "merchant_order_id": merchant_order_id,
                "tracking_number": tracking_number,
                "carrier": carrier,
                "shipped_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def send_order_delivered(self, merchant_order_id: str) -> bool:
        """Send order delivered event.

        Args:
            merchant_order_id: Merchant's order ID.

        Returns:
            True if delivery succeeded.
        """
        return await self.send_event(
            WebhookEventType.ORDER_DELIVERED,
            {
                "merchant_order_id": merchant_order_id,
                "delivered_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def send_price_changed(
        self,
        checkout_id: str,
        product_id: str,
        old_price: int,
        new_price: int,
        currency: str,
    ) -> bool:
        """Send price changed event.

        Args:
            checkout_id: Related checkout ID.
            product_id: Product ID.
            old_price: Old price in cents.
            new_price: New price in cents.
            currency: Currency code.

        Returns:
            True if delivery succeeded.
        """
        return await self.send_event(
            WebhookEventType.PRICE_CHANGED,
            {
                "checkout_id": checkout_id,
                "product_id": product_id,
                "old_price": old_price,
                "new_price": new_price,
                "currency": currency,
                "changed_at": datetime.now(timezone.utc).isoformat(),
            },
            checkout_id=checkout_id,
        )

    async def send_stock_changed(
        self,
        checkout_id: str,
        product_id: str,
        variant_id: str | None,
        in_stock: bool,
        quantity: int,
    ) -> bool:
        """Send stock changed event.

        Args:
            checkout_id: Related checkout ID.
            product_id: Product ID.
            variant_id: Variant ID if applicable.
            in_stock: New stock status.
            quantity: New quantity.

        Returns:
            True if delivery succeeded.
        """
        return await self.send_event(
            WebhookEventType.STOCK_CHANGED,
            {
                "checkout_id": checkout_id,
                "product_id": product_id,
                "variant_id": variant_id,
                "in_stock": in_stock,
                "quantity": quantity,
                "changed_at": datetime.now(timezone.utc).isoformat(),
            },
            checkout_id=checkout_id,
        )

    async def close(self) -> None:
        """Close HTTP client."""
        await self._client.aclose()


# Global webhook sender instance
_webhook_sender: WebhookSender | None = None


def get_webhook_sender(
    webhook_url: str = "http://cartpilot-api:8000/webhooks/merchant",
    webhook_secret: str = "dev-webhook-secret-change-in-production",
    merchant_id: str = "merchant-b",
) -> WebhookSender:
    """Get or create webhook sender instance.

    Args:
        webhook_url: Webhook URL.
        webhook_secret: Webhook secret.
        merchant_id: Merchant ID.

    Returns:
        WebhookSender instance.
    """
    global _webhook_sender
    if _webhook_sender is None:
        _webhook_sender = WebhookSender(webhook_url, webhook_secret, merchant_id)
    return _webhook_sender


def reset_webhook_sender() -> None:
    """Reset webhook sender instance (for testing)."""
    global _webhook_sender
    _webhook_sender = None
