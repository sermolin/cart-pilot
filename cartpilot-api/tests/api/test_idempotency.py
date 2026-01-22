"""Tests for idempotency middleware.

Tests:
- Idempotency key handling
- Response caching
- Request body conflict detection
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.application.idempotency_service import (
    CachedResponse,
    IdempotencyService,
    InMemoryIdempotencyStore,
)
from app.api.idempotency import _matches_pattern, _requires_idempotency


# ============================================================================
# Pattern Matching Tests
# ============================================================================


class TestPatternMatching:
    """Tests for endpoint pattern matching."""

    def test_matches_exact_path(self):
        """Should match exact paths."""
        assert _matches_pattern("/checkouts", "/checkouts") is True
        assert _matches_pattern("/intents", "/intents") is True

    def test_matches_path_with_parameters(self):
        """Should match paths with parameters."""
        assert _matches_pattern(
            "/checkouts/abc123/confirm",
            "/checkouts/{checkout_id}/confirm",
        ) is True

    def test_matches_path_with_multiple_parameters(self):
        """Should match paths with multiple parameters."""
        assert _matches_pattern(
            "/merchants/m1/products/p1",
            "/merchants/{merchant_id}/products/{product_id}",
        ) is True

    def test_no_match_different_length(self):
        """Should not match paths of different length."""
        assert _matches_pattern("/checkouts", "/checkouts/confirm") is False
        assert _matches_pattern("/checkouts/abc/def", "/checkouts/{id}") is False

    def test_no_match_different_segments(self):
        """Should not match paths with different segments."""
        assert _matches_pattern("/checkouts/abc", "/intents/{id}") is False


class TestRequiresIdempotency:
    """Tests for _requires_idempotency function."""

    def test_requires_for_post_checkouts(self):
        """POST /checkouts requires idempotency."""
        assert _requires_idempotency("/checkouts", "POST") is True

    def test_requires_for_post_confirm(self):
        """POST /checkouts/{id}/confirm requires idempotency."""
        assert _requires_idempotency("/checkouts/abc123/confirm", "POST") is True

    def test_not_required_for_get(self):
        """GET requests don't require idempotency."""
        assert _requires_idempotency("/checkouts", "GET") is False
        assert _requires_idempotency("/checkouts/abc123", "GET") is False

    def test_not_required_for_unknown_endpoint(self):
        """Unknown endpoints don't require idempotency."""
        assert _requires_idempotency("/unknown/endpoint", "POST") is False


# ============================================================================
# Idempotency Store Tests
# ============================================================================


class TestInMemoryIdempotencyStore:
    """Tests for InMemoryIdempotencyStore."""

    @pytest.fixture
    def store(self):
        """Create store instance."""
        return InMemoryIdempotencyStore(ttl_hours=24)

    @pytest.mark.asyncio
    async def test_store_and_get(self, store):
        """Should store and retrieve responses."""
        cached = await store.store(
            idempotency_key="key-001",
            endpoint="/checkouts",
            method="POST",
            response_status=201,
            response_body={"id": "checkout-001"},
            request_hash="abc123",
        )

        retrieved = await store.get("key-001", "/checkouts", "POST")

        assert retrieved is not None
        assert retrieved.idempotency_key == "key-001"
        assert retrieved.response_status == 201
        assert retrieved.response_body == {"id": "checkout-001"}
        assert retrieved.request_hash == "abc123"

    @pytest.mark.asyncio
    async def test_get_returns_none_for_missing(self, store):
        """Should return None for missing keys."""
        result = await store.get("nonexistent", "/checkouts", "POST")
        assert result is None

    @pytest.mark.asyncio
    async def test_expired_entries_not_returned(self, store):
        """Expired entries should not be returned."""
        # Store entry
        await store.store(
            idempotency_key="key-001",
            endpoint="/checkouts",
            method="POST",
            response_status=201,
            response_body={},
        )

        # Manually expire it
        key = "key-001:POST:/checkouts"
        store._responses[key].expires_at = datetime.now(timezone.utc) - timedelta(hours=1)

        # Should return None
        result = await store.get("key-001", "/checkouts", "POST")
        assert result is None

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, store):
        """Should cleanup expired entries."""
        # Store entries
        await store.store("key-001", "/a", "POST", 200, {})
        await store.store("key-002", "/b", "POST", 200, {})

        # Expire one
        key = "key-001:POST:/a"
        store._responses[key].expires_at = datetime.now(timezone.utc) - timedelta(hours=1)

        # Cleanup
        removed = await store.cleanup_expired()

        assert removed == 1
        assert await store.get("key-001", "/a", "POST") is None
        assert await store.get("key-002", "/b", "POST") is not None


# ============================================================================
# Idempotency Service Tests
# ============================================================================


class TestIdempotencyService:
    """Tests for IdempotencyService."""

    @pytest.fixture
    def service(self):
        """Create service instance."""
        return IdempotencyService()

    @pytest.mark.asyncio
    async def test_check_returns_not_cached_for_new_key(self, service):
        """Should return not cached for new keys."""
        result = await service.check(
            idempotency_key="new-key",
            endpoint="/checkouts",
            method="POST",
        )

        assert result.is_cached is False
        assert result.cached_response is None
        assert result.is_conflict is False

    @pytest.mark.asyncio
    async def test_check_returns_cached_response(self, service):
        """Should return cached response for known key."""
        # Store response
        await service.store(
            idempotency_key="key-001",
            endpoint="/checkouts",
            method="POST",
            response_status=201,
            response_body={"id": "checkout-001"},
        )

        # Check same key
        result = await service.check(
            idempotency_key="key-001",
            endpoint="/checkouts",
            method="POST",
        )

        assert result.is_cached is True
        assert result.cached_response is not None
        assert result.cached_response.response_status == 201

    @pytest.mark.asyncio
    async def test_detects_request_body_conflict(self, service):
        """Should detect request body conflicts."""
        original_body = {"offer_id": "offer-001", "quantity": 1}

        # Store with original request body
        await service.store(
            idempotency_key="key-001",
            endpoint="/checkouts",
            method="POST",
            response_status=201,
            response_body={"id": "checkout-001"},
            request_body=original_body,
        )

        # Check with different body
        different_body = {"offer_id": "offer-002", "quantity": 2}
        result = await service.check(
            idempotency_key="key-001",
            endpoint="/checkouts",
            method="POST",
            request_body=different_body,
        )

        assert result.is_cached is False
        assert result.is_conflict is True
        assert "different request body" in result.conflict_message.lower()

    @pytest.mark.asyncio
    async def test_same_request_body_not_conflict(self, service):
        """Same request body should not be a conflict."""
        body = {"offer_id": "offer-001", "quantity": 1}

        # Store
        await service.store(
            idempotency_key="key-001",
            endpoint="/checkouts",
            method="POST",
            response_status=201,
            response_body={"id": "checkout-001"},
            request_body=body,
        )

        # Check with same body
        result = await service.check(
            idempotency_key="key-001",
            endpoint="/checkouts",
            method="POST",
            request_body=body,
        )

        assert result.is_cached is True
        assert result.is_conflict is False


class TestComputeRequestHash:
    """Tests for request hash computation."""

    def test_hash_is_deterministic(self):
        """Same body should produce same hash."""
        body = {"a": 1, "b": 2}
        hash1 = IdempotencyService.compute_request_hash(body)
        hash2 = IdempotencyService.compute_request_hash(body)

        assert hash1 == hash2

    def test_different_body_different_hash(self):
        """Different bodies should produce different hashes."""
        body1 = {"a": 1}
        body2 = {"a": 2}

        hash1 = IdempotencyService.compute_request_hash(body1)
        hash2 = IdempotencyService.compute_request_hash(body2)

        assert hash1 != hash2

    def test_none_body_returns_none(self):
        """None body should return None hash."""
        assert IdempotencyService.compute_request_hash(None) is None

    def test_key_order_independent(self):
        """Key order should not affect hash."""
        body1 = {"a": 1, "b": 2}
        body2 = {"b": 2, "a": 1}

        hash1 = IdempotencyService.compute_request_hash(body1)
        hash2 = IdempotencyService.compute_request_hash(body2)

        assert hash1 == hash2
