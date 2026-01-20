"""Webhook sender service for Merchant A.

Sends webhook notifications to CartPilot on checkout status changes.
"""

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from app.schemas import WebhookEventType, WebhookPayloadSchema

logger = structlog.get_logger()


class WebhookSender:
    """Sends webhook events to CartPilot API.

    Handles HMAC signing and async delivery of webhook events.
    """

    def __init__(
        self,
        webhook_url: str,
        webhook_secret: str,
        merchant_id: str = "merchant-a",
    ) -> None:
        """Initialize webhook sender.

        Args:
            webhook_url: URL to send webhooks to.
            webhook_secret: Secret for HMAC signing.
            merchant_id: Merchant identifier.
        """
        self.webhook_url = webhook_url
        self.webhook_secret = webhook_secret
        self.merchant_id = merchant_id
        self._client = httpx.AsyncClient(timeout=10.0)

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
        self, event_type: WebhookEventType, data: dict[str, Any]
    ) -> WebhookPayloadSchema:
        """Build webhook payload.

        Args:
            event_type: Type of event.
            data: Event-specific data.

        Returns:
            Webhook payload schema.
        """
        return WebhookPayloadSchema(
            event_id=self._generate_event_id(),
            event_type=event_type,
            merchant_id=self.merchant_id,
            timestamp=datetime.now(timezone.utc),
            data=data,
        )

    async def send_event(
        self, event_type: WebhookEventType, data: dict[str, Any]
    ) -> bool:
        """Send webhook event to CartPilot.

        Args:
            event_type: Type of event.
            data: Event-specific data.

        Returns:
            True if delivery succeeded.
        """
        payload = self._build_payload(event_type, data)
        payload_json = payload.model_dump_json()

        signature = self._sign_payload(payload_json)

        headers = {
            "Content-Type": "application/json",
            "X-Merchant-Signature": signature,
            "X-Merchant-Id": self.merchant_id,
            "X-Event-Id": payload.event_id,
        }

        try:
            response = await self._client.post(
                self.webhook_url,
                content=payload_json,
                headers=headers,
            )

            if response.status_code == 200:
                logger.info(
                    "Webhook delivered successfully",
                    event_type=event_type.value,
                    event_id=payload.event_id,
                    status_code=response.status_code,
                )
                return True
            else:
                logger.warning(
                    "Webhook delivery failed",
                    event_type=event_type.value,
                    event_id=payload.event_id,
                    status_code=response.status_code,
                    response_body=response.text[:200],
                )
                return False

        except httpx.RequestError as e:
            logger.error(
                "Webhook delivery error",
                event_type=event_type.value,
                event_id=payload.event_id,
                error=str(e),
            )
            return False

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

    async def close(self) -> None:
        """Close HTTP client."""
        await self._client.aclose()


# Global webhook sender instance
_webhook_sender: WebhookSender | None = None


def get_webhook_sender(
    webhook_url: str = "http://cartpilot-api:8000/webhooks/merchant",
    webhook_secret: str = "dev-webhook-secret-change-in-production",
    merchant_id: str = "merchant-a",
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
