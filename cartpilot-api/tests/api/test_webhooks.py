"""Tests for webhook receiver endpoint.

Tests:
- HMAC signature verification
- Event deduplication
- Event processing
- Error handling
"""

import hashlib
import hmac
import json
from datetime import datetime, timezone

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.application.webhook_service import (
    EventStatus,
    InMemoryEventLog,
    WebhookEvent,
    WebhookEventType,
    WebhookService,
    WebhookSignatureVerifier,
)
from app.main import app


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def webhook_secret():
    """Test webhook secret."""
    return "test-webhook-secret"


@pytest.fixture
def merchant_id():
    """Test merchant ID."""
    return "merchant-a"


def sign_payload(payload: str, secret: str) -> str:
    """Generate HMAC signature for payload."""
    signature = hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={signature}"


def create_webhook_payload(
    event_id: str = "evt-001",
    event_type: str = "checkout.confirmed",
    merchant_id: str = "merchant-a",
    data: dict | None = None,
) -> dict:
    """Create a test webhook payload."""
    return {
        "event_id": event_id,
        "event_type": event_type,
        "merchant_id": merchant_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data or {"checkout_id": "checkout-001"},
        "ucp_version": "1.0.0",
    }


# ============================================================================
# Signature Verification Tests
# ============================================================================


class TestWebhookSignatureVerifier:
    """Tests for WebhookSignatureVerifier."""

    def test_verify_valid_signature(self, webhook_secret, merchant_id):
        """Valid signature should be accepted."""
        verifier = WebhookSignatureVerifier(secret=webhook_secret)

        payload = json.dumps({"test": "data"})
        signature = sign_payload(payload, webhook_secret)

        assert verifier.verify(payload, signature, merchant_id) is True

    def test_verify_invalid_signature(self, webhook_secret, merchant_id):
        """Invalid signature should be rejected."""
        verifier = WebhookSignatureVerifier(secret=webhook_secret)

        payload = json.dumps({"test": "data"})
        signature = "sha256=invalid"

        assert verifier.verify(payload, signature, merchant_id) is False

    def test_verify_wrong_secret(self, webhook_secret, merchant_id):
        """Signature with wrong secret should be rejected."""
        verifier = WebhookSignatureVerifier(secret=webhook_secret)

        payload = json.dumps({"test": "data"})
        signature = sign_payload(payload, "wrong-secret")

        assert verifier.verify(payload, signature, merchant_id) is False

    def test_verify_missing_signature(self, webhook_secret, merchant_id):
        """Missing signature should be rejected."""
        verifier = WebhookSignatureVerifier(secret=webhook_secret)

        payload = json.dumps({"test": "data"})

        assert verifier.verify(payload, "", merchant_id) is False

    def test_verify_invalid_format(self, webhook_secret, merchant_id):
        """Invalid signature format should be rejected."""
        verifier = WebhookSignatureVerifier(secret=webhook_secret)

        payload = json.dumps({"test": "data"})

        # Missing sha256= prefix
        assert verifier.verify(payload, "abc123", merchant_id) is False

        # Wrong algorithm prefix
        assert verifier.verify(payload, "md5=abc123", merchant_id) is False


# ============================================================================
# Event Log Tests
# ============================================================================


class TestInMemoryEventLog:
    """Tests for InMemoryEventLog."""

    @pytest.fixture
    def event_log(self):
        """Create event log instance."""
        return InMemoryEventLog()

    @pytest.fixture
    def sample_event(self, merchant_id):
        """Create sample event."""
        return WebhookEvent(
            event_id="evt-001",
            event_type=WebhookEventType.CHECKOUT_CONFIRMED,
            merchant_id=merchant_id,
            timestamp=datetime.now(timezone.utc),
            data={"checkout_id": "checkout-001"},
        )

    @pytest.mark.asyncio
    async def test_store_and_get_event(self, event_log, sample_event, merchant_id):
        """Should store and retrieve events."""
        await event_log.store(
            event=sample_event,
            status=EventStatus.PROCESSED,
            correlation_id="req-001",
        )

        stored = await event_log.get("evt-001", merchant_id)
        assert stored is not None
        assert stored["event_id"] == "evt-001"
        assert stored["status"] == "processed"
        assert stored["correlation_id"] == "req-001"

    @pytest.mark.asyncio
    async def test_exists_returns_true_for_existing(self, event_log, sample_event, merchant_id):
        """exists() should return True for stored events."""
        await event_log.store(sample_event, EventStatus.PROCESSED)

        assert await event_log.exists("evt-001", merchant_id) is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_for_missing(self, event_log, merchant_id):
        """exists() should return False for missing events."""
        assert await event_log.exists("evt-unknown", merchant_id) is False

    @pytest.mark.asyncio
    async def test_update_status(self, event_log, sample_event, merchant_id):
        """Should update event status."""
        await event_log.store(sample_event, EventStatus.PROCESSING)

        await event_log.update_status(
            "evt-001",
            merchant_id,
            EventStatus.FAILED,
            error_message="Test error",
        )

        stored = await event_log.get("evt-001", merchant_id)
        assert stored["status"] == "failed"
        assert stored["error_message"] == "Test error"


# ============================================================================
# Webhook Service Tests
# ============================================================================


class TestWebhookService:
    """Tests for WebhookService."""

    @pytest.fixture
    def service(self, webhook_secret):
        """Create webhook service."""
        return WebhookService(
            event_log=InMemoryEventLog(),
            signature_verifier=WebhookSignatureVerifier(secret=webhook_secret),
        )

    @pytest.fixture
    def sample_event(self, merchant_id):
        """Create sample event."""
        return WebhookEvent(
            event_id="evt-001",
            event_type=WebhookEventType.CHECKOUT_CONFIRMED,
            merchant_id=merchant_id,
            timestamp=datetime.now(timezone.utc),
            data={"checkout_id": "checkout-001", "merchant_order_id": "order-001"},
        )

    @pytest.mark.asyncio
    async def test_process_event_success(self, service, sample_event):
        """Should process event successfully."""
        result = await service.process_event(sample_event, correlation_id="req-001")

        assert result.success is True
        assert result.event_id == "evt-001"
        assert result.status == EventStatus.PROCESSED
        assert result.duplicate is False

    @pytest.mark.asyncio
    async def test_process_duplicate_event(self, service, sample_event):
        """Should detect and handle duplicate events."""
        # Process first time
        result1 = await service.process_event(sample_event)
        assert result1.success is True
        assert result1.duplicate is False

        # Process second time (duplicate)
        result2 = await service.process_event(sample_event)
        assert result2.success is True
        assert result2.duplicate is True
        assert result2.status == EventStatus.DUPLICATE

    @pytest.mark.asyncio
    async def test_process_multiple_different_events(self, service, merchant_id):
        """Should process different events independently."""
        event1 = WebhookEvent(
            event_id="evt-001",
            event_type=WebhookEventType.CHECKOUT_CONFIRMED,
            merchant_id=merchant_id,
            timestamp=datetime.now(timezone.utc),
            data={"checkout_id": "checkout-001"},
        )
        event2 = WebhookEvent(
            event_id="evt-002",
            event_type=WebhookEventType.ORDER_SHIPPED,
            merchant_id=merchant_id,
            timestamp=datetime.now(timezone.utc),
            data={"merchant_order_id": "order-001"},
        )

        result1 = await service.process_event(event1)
        result2 = await service.process_event(event2)

        assert result1.success is True
        assert result2.success is True
        assert result1.event_id == "evt-001"
        assert result2.event_id == "evt-002"


# ============================================================================
# Webhook Endpoint Tests
# ============================================================================


class TestWebhookEndpoint:
    """Tests for POST /webhooks/merchant endpoint."""

    def test_receive_webhook_success(self, client, merchant_id):
        """Should accept valid webhook."""
        payload = create_webhook_payload(merchant_id=merchant_id)
        payload_json = json.dumps(payload)

        # Sign payload
        from app.infrastructure.config import settings

        signature = sign_payload(payload_json, settings.webhook_secret)

        response = client.post(
            "/webhooks/merchant",
            content=payload_json,
            headers={
                "Content-Type": "application/json",
                "X-Merchant-Signature": signature,
                "X-Merchant-Id": merchant_id,
                "X-Event-Id": payload["event_id"],
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["event_id"] == payload["event_id"]

    def test_receive_webhook_without_signature(self, client, merchant_id):
        """Should accept webhook without signature (for dev)."""
        payload = create_webhook_payload(merchant_id=merchant_id)

        response = client.post(
            "/webhooks/merchant",
            json=payload,
            headers={
                "X-Merchant-Id": merchant_id,
            },
        )

        # Should succeed but log warning
        assert response.status_code == status.HTTP_200_OK

    def test_receive_webhook_invalid_signature(self, client, merchant_id):
        """Should reject webhook with invalid signature."""
        payload = create_webhook_payload(merchant_id=merchant_id)
        payload_json = json.dumps(payload)

        response = client.post(
            "/webhooks/merchant",
            content=payload_json,
            headers={
                "Content-Type": "application/json",
                "X-Merchant-Signature": "sha256=invalid",
                "X-Merchant-Id": merchant_id,
            },
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        data = response.json()
        assert data["error_code"] == "INVALID_SIGNATURE"

    def test_receive_webhook_merchant_id_mismatch(self, client, merchant_id):
        """Should reject webhook with mismatched merchant ID."""
        payload = create_webhook_payload(merchant_id=merchant_id)

        response = client.post(
            "/webhooks/merchant",
            json=payload,
            headers={
                "X-Merchant-Id": "different-merchant",
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert data["error_code"] == "MERCHANT_ID_MISMATCH"

    def test_receive_webhook_unknown_event_type(self, client, merchant_id):
        """Should accept unknown event type gracefully."""
        payload = create_webhook_payload(
            event_type="unknown.event",
            merchant_id=merchant_id,
        )

        response = client.post(
            "/webhooks/merchant",
            json=payload,
            headers={
                "X-Merchant-Id": merchant_id,
            },
        )

        # Should accept but return ignored status
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "ignored"

    def test_duplicate_webhook_handled(self, client, merchant_id):
        """Should handle duplicate webhooks idempotently."""
        payload = create_webhook_payload(
            event_id="duplicate-test-evt",
            merchant_id=merchant_id,
        )

        # Send first time
        response1 = client.post(
            "/webhooks/merchant",
            json=payload,
            headers={"X-Merchant-Id": merchant_id},
        )
        assert response1.status_code == status.HTTP_200_OK
        assert response1.json()["status"] == "processed"

        # Send again (duplicate)
        response2 = client.post(
            "/webhooks/merchant",
            json=payload,
            headers={"X-Merchant-Id": merchant_id},
        )
        assert response2.status_code == status.HTTP_200_OK
        assert response2.json()["status"] == "duplicate"
