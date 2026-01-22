"""Idempotency middleware for mutating endpoints.

Provides:
- Idempotency-Key header handling
- Response caching for duplicate requests
- Request body conflict detection
"""

import json
from typing import Callable

import structlog
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.application.idempotency_service import (
    IdempotencyService,
    get_idempotency_service,
)

logger = structlog.get_logger()


# Endpoints that require idempotency keys
IDEMPOTENT_ENDPOINTS = {
    # POST endpoints that modify state
    "/checkouts": ["POST"],
    "/checkouts/{checkout_id}/quote": ["POST"],
    "/checkouts/{checkout_id}/request-approval": ["POST"],
    "/checkouts/{checkout_id}/approve": ["POST"],
    "/checkouts/{checkout_id}/confirm": ["POST"],
    "/intents": ["POST"],
}


def _matches_pattern(path: str, pattern: str) -> bool:
    """Check if path matches a pattern with path parameters.

    Args:
        path: Actual request path (e.g., /checkouts/abc123/confirm)
        pattern: Pattern with placeholders (e.g., /checkouts/{checkout_id}/confirm)

    Returns:
        True if path matches pattern.
    """
    path_parts = path.rstrip("/").split("/")
    pattern_parts = pattern.rstrip("/").split("/")

    if len(path_parts) != len(pattern_parts):
        return False

    for path_part, pattern_part in zip(path_parts, pattern_parts):
        if pattern_part.startswith("{") and pattern_part.endswith("}"):
            # This is a path parameter, matches anything
            continue
        if path_part != pattern_part:
            return False

    return True


def _requires_idempotency(path: str, method: str) -> bool:
    """Check if endpoint requires idempotency key.

    Args:
        path: Request path.
        method: HTTP method.

    Returns:
        True if idempotency key is required.
    """
    for pattern, methods in IDEMPOTENT_ENDPOINTS.items():
        if method in methods and _matches_pattern(path, pattern):
            return True
    return False


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Middleware for idempotency key handling.

    For mutating endpoints:
    - Checks for Idempotency-Key header
    - Returns cached response if key was seen before
    - Caches response for new keys
    - Detects request body conflicts
    """

    HEADER_NAME = "Idempotency-Key"

    def __init__(self, app, service: IdempotencyService | None = None) -> None:
        """Initialize middleware.

        Args:
            app: The ASGI application.
            service: Idempotency service (uses global if not provided).
        """
        super().__init__(app)
        self._service = service

    @property
    def service(self) -> IdempotencyService:
        """Get idempotency service."""
        if self._service is None:
            self._service = get_idempotency_service()
        return self._service

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """Handle idempotency for mutating requests.

        Args:
            request: Incoming request.
            call_next: Next middleware/handler.

        Returns:
            Response (cached or fresh).
        """
        path = request.url.path.rstrip("/")
        method = request.method

        # Only handle idempotent endpoints
        if not _requires_idempotency(path, method):
            return await call_next(request)

        # Get idempotency key
        idempotency_key = request.headers.get(self.HEADER_NAME)

        if not idempotency_key:
            # For now, warn but don't require
            # In production, you might want to return 400
            logger.debug(
                "Request without idempotency key",
                path=path,
                method=method,
            )
            return await call_next(request)

        # Parse request body for conflict detection
        request_body = None
        try:
            body = await request.body()
            if body:
                request_body = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        # Check for cached response
        result = await self.service.check(
            idempotency_key=idempotency_key,
            endpoint=path,
            method=method,
            request_body=request_body,
        )

        if result.is_conflict:
            logger.warning(
                "Idempotency key conflict",
                idempotency_key=idempotency_key,
                path=path,
            )
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "error_code": "IDEMPOTENCY_CONFLICT",
                    "message": result.conflict_message or "Idempotency key already used with different request",
                    "details": [],
                },
            )

        if result.is_cached and result.cached_response:
            cached = result.cached_response
            logger.info(
                "Returning cached idempotent response",
                idempotency_key=idempotency_key,
                path=path,
                original_status=cached.response_status,
            )
            response = JSONResponse(
                status_code=cached.response_status,
                content=cached.response_body,
            )
            response.headers["X-Idempotent-Replayed"] = "true"
            return response

        # Process request normally
        response = await call_next(request)

        # Cache successful responses (2xx and 4xx for validation errors)
        if response.status_code < 500:
            # Read response body
            response_body = b""
            async for chunk in response.body_iterator:
                response_body += chunk

            try:
                response_dict = json.loads(response_body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                response_dict = {}

            # Store response
            await self.service.store(
                idempotency_key=idempotency_key,
                endpoint=path,
                method=method,
                response_status=response.status_code,
                response_body=response_dict,
                request_body=request_body,
            )

            # Return new response with body
            new_response = JSONResponse(
                status_code=response.status_code,
                content=response_dict,
            )
            # Copy headers
            for key, value in response.headers.items():
                if key.lower() not in ("content-length", "content-type"):
                    new_response.headers[key] = value

            return new_response

        return response


def setup_idempotency_middleware(app) -> None:
    """Add idempotency middleware to the application.

    Args:
        app: FastAPI application instance.
    """
    app.add_middleware(IdempotencyMiddleware)
