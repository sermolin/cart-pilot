"""Idempotency service for safe request retries.

Provides:
- Idempotency key handling
- Response caching
- Request deduplication
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class CachedResponse:
    """A cached response for an idempotent request.

    Attributes:
        idempotency_key: The idempotency key.
        endpoint: API endpoint.
        method: HTTP method.
        response_status: HTTP status code.
        response_body: Response body as dict.
        response_headers: Response headers.
        created_at: When the response was cached.
        expires_at: When the cached response expires.
        request_hash: Hash of the original request body.
    """

    idempotency_key: str
    endpoint: str
    method: str
    response_status: int
    response_body: dict[str, Any]
    response_headers: dict[str, str] | None
    created_at: datetime
    expires_at: datetime
    request_hash: str | None = None


@dataclass
class IdempotencyResult:
    """Result of an idempotency check.

    Attributes:
        is_cached: Whether a cached response was found.
        cached_response: The cached response if found.
        is_conflict: Whether request body conflicts with original.
    """

    is_cached: bool
    cached_response: CachedResponse | None = None
    is_conflict: bool = False
    conflict_message: str | None = None


class InMemoryIdempotencyStore:
    """In-memory store for idempotency responses.

    Used as a simple implementation before database integration.
    In production, this would use the idempotency_responses database table.
    """

    def __init__(self, ttl_hours: int = 24) -> None:
        """Initialize store.

        Args:
            ttl_hours: Time-to-live for cached responses in hours.
        """
        self._responses: dict[str, CachedResponse] = {}
        self.ttl_hours = ttl_hours

    def _make_key(self, idempotency_key: str, endpoint: str, method: str) -> str:
        """Create composite key."""
        return f"{idempotency_key}:{method}:{endpoint}"

    async def get(
        self, idempotency_key: str, endpoint: str, method: str
    ) -> CachedResponse | None:
        """Get a cached response.

        Args:
            idempotency_key: The idempotency key.
            endpoint: API endpoint.
            method: HTTP method.

        Returns:
            Cached response if found and not expired.
        """
        key = self._make_key(idempotency_key, endpoint, method)
        cached = self._responses.get(key)

        if cached is None:
            return None

        # Check expiration
        if datetime.now(timezone.utc) > cached.expires_at:
            del self._responses[key]
            return None

        return cached

    async def store(
        self,
        idempotency_key: str,
        endpoint: str,
        method: str,
        response_status: int,
        response_body: dict[str, Any],
        response_headers: dict[str, str] | None = None,
        request_hash: str | None = None,
    ) -> CachedResponse:
        """Store a response.

        Args:
            idempotency_key: The idempotency key.
            endpoint: API endpoint.
            method: HTTP method.
            response_status: HTTP status code.
            response_body: Response body.
            response_headers: Response headers.
            request_hash: Hash of request body.

        Returns:
            The cached response.
        """
        now = datetime.now(timezone.utc)
        cached = CachedResponse(
            idempotency_key=idempotency_key,
            endpoint=endpoint,
            method=method,
            response_status=response_status,
            response_body=response_body,
            response_headers=response_headers,
            created_at=now,
            expires_at=now + timedelta(hours=self.ttl_hours),
            request_hash=request_hash,
        )

        key = self._make_key(idempotency_key, endpoint, method)
        self._responses[key] = cached

        logger.debug(
            "Stored idempotent response",
            idempotency_key=idempotency_key,
            endpoint=endpoint,
            method=method,
            status=response_status,
        )

        return cached

    async def cleanup_expired(self) -> int:
        """Remove expired entries.

        Returns:
            Number of entries removed.
        """
        now = datetime.now(timezone.utc)
        expired_keys = [
            key
            for key, cached in self._responses.items()
            if now > cached.expires_at
        ]
        for key in expired_keys:
            del self._responses[key]
        return len(expired_keys)


class IdempotencyService:
    """Service for handling idempotent requests.

    Provides:
    - Check if request was already processed
    - Store response for idempotency key
    - Detect request body conflicts
    """

    def __init__(self, storage: InMemoryIdempotencyStore | None = None) -> None:
        """Initialize service.

        Args:
            storage: Storage backend for responses.
        """
        self._storage = storage or InMemoryIdempotencyStore()

    @staticmethod
    def compute_request_hash(body: dict[str, Any] | None) -> str | None:
        """Compute hash of request body for conflict detection.

        Args:
            body: Request body.

        Returns:
            SHA-256 hash or None if no body.
        """
        if body is None:
            return None
        payload = json.dumps(body, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()

    async def check(
        self,
        idempotency_key: str,
        endpoint: str,
        method: str,
        request_body: dict[str, Any] | None = None,
    ) -> IdempotencyResult:
        """Check if request was already processed.

        Args:
            idempotency_key: The idempotency key from header.
            endpoint: API endpoint path.
            method: HTTP method.
            request_body: Current request body for conflict detection.

        Returns:
            IdempotencyResult with cached response if found.
        """
        cached = await self._storage.get(idempotency_key, endpoint, method)

        if cached is None:
            return IdempotencyResult(is_cached=False)

        # Check for request body conflict
        if cached.request_hash and request_body:
            current_hash = self.compute_request_hash(request_body)
            if current_hash != cached.request_hash:
                logger.warning(
                    "Idempotency key reused with different request body",
                    idempotency_key=idempotency_key,
                    endpoint=endpoint,
                )
                return IdempotencyResult(
                    is_cached=False,
                    is_conflict=True,
                    conflict_message=(
                        "Idempotency key already used with different request body"
                    ),
                )

        logger.info(
            "Returning cached idempotent response",
            idempotency_key=idempotency_key,
            endpoint=endpoint,
            original_status=cached.response_status,
        )

        return IdempotencyResult(
            is_cached=True,
            cached_response=cached,
        )

    async def store(
        self,
        idempotency_key: str,
        endpoint: str,
        method: str,
        response_status: int,
        response_body: dict[str, Any],
        response_headers: dict[str, str] | None = None,
        request_body: dict[str, Any] | None = None,
    ) -> CachedResponse:
        """Store response for idempotency key.

        Args:
            idempotency_key: The idempotency key.
            endpoint: API endpoint.
            method: HTTP method.
            response_status: HTTP status code.
            response_body: Response body.
            response_headers: Response headers.
            request_body: Request body for conflict detection.

        Returns:
            The cached response.
        """
        request_hash = self.compute_request_hash(request_body)

        return await self._storage.store(
            idempotency_key=idempotency_key,
            endpoint=endpoint,
            method=method,
            response_status=response_status,
            response_body=response_body,
            response_headers=response_headers,
            request_hash=request_hash,
        )


# Global service instance
_idempotency_service: IdempotencyService | None = None


def get_idempotency_service() -> IdempotencyService:
    """Get or create the idempotency service instance.

    Returns:
        IdempotencyService instance.
    """
    global _idempotency_service
    if _idempotency_service is None:
        _idempotency_service = IdempotencyService()
    return _idempotency_service
