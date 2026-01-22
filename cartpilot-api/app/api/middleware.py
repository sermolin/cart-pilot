"""API middleware for CartPilot.

Provides:
- API key authentication
- Request ID correlation
- Error handling
"""

import time
from typing import Callable
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.infrastructure.config import settings

logger = structlog.get_logger()


# ============================================================================
# Request ID Middleware
# ============================================================================


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware to add request ID for correlation.

    Generates or extracts a request ID and adds it to:
    - Request state for access in handlers
    - Response headers for client correlation
    - Log context for tracing
    """

    HEADER_NAME = "X-Request-ID"

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """Process request with correlation ID.

        Args:
            request: Incoming request.
            call_next: Next middleware/handler.

        Returns:
            Response with request ID header.
        """
        # Get or generate request ID
        request_id = request.headers.get(self.HEADER_NAME) or str(uuid4())

        # Store in request state for handlers
        request.state.request_id = request_id

        # Add to log context
        structlog.contextvars.bind_contextvars(request_id=request_id)

        # Time the request
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        finally:
            # Calculate duration
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Log request completion
            logger.info(
                "Request completed",
                method=request.method,
                path=request.url.path,
                status_code=getattr(response, "status_code", 500),
                duration_ms=round(duration_ms, 2),
            )

            # Clear log context
            structlog.contextvars.unbind_contextvars("request_id")

        # Add request ID to response headers
        response.headers[self.HEADER_NAME] = request_id

        return response


# ============================================================================
# API Key Authentication Middleware
# ============================================================================


# Paths that don't require authentication
PUBLIC_PATHS = {
    "/health",
    "/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/webhooks/merchant",  # Webhooks use HMAC signature instead of API key
}


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Middleware for API key authentication.

    Validates the Authorization header contains a valid API key.
    Supports Bearer token format: "Authorization: Bearer <api_key>"
    """

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """Validate API key for protected endpoints.

        Args:
            request: Incoming request.
            call_next: Next middleware/handler.

        Returns:
            Response or 401 error.
        """
        # Skip auth for public paths
        path = request.url.path.rstrip("/")
        if path in PUBLIC_PATHS or path.startswith("/docs") or path.startswith("/redoc"):
            return await call_next(request)

        # Get Authorization header
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            logger.warning(
                "Missing authorization header",
                path=path,
                method=request.method,
            )
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error_code": "UNAUTHORIZED",
                    "message": "Missing Authorization header",
                    "details": [],
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Validate Bearer token format
        parts = auth_header.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            logger.warning(
                "Invalid authorization format",
                path=path,
                method=request.method,
            )
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error_code": "UNAUTHORIZED",
                    "message": "Invalid Authorization header format. Use 'Bearer <api_key>'",
                    "details": [],
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        api_key = parts[1]

        # Validate API key
        if api_key != settings.cartpilot_api_key:
            logger.warning(
                "Invalid API key",
                path=path,
                method=request.method,
            )
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error_code": "INVALID_API_KEY",
                    "message": "Invalid API key",
                    "details": [],
                },
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Store authenticated status
        request.state.authenticated = True

        return await call_next(request)


# ============================================================================
# Error Handling Middleware
# ============================================================================


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Middleware for consistent error handling.

    Catches unhandled exceptions and returns standardized error responses.
    """

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """Handle errors uniformly.

        Args:
            request: Incoming request.
            call_next: Next middleware/handler.

        Returns:
            Response or error response.
        """
        try:
            return await call_next(request)
        except Exception as e:
            request_id = getattr(request.state, "request_id", None)

            logger.exception(
                "Unhandled exception",
                path=request.url.path,
                method=request.method,
                error=str(e),
            )

            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error_code": "INTERNAL_ERROR",
                    "message": "An internal error occurred",
                    "details": [],
                    "request_id": request_id,
                },
            )


# ============================================================================
# Middleware Setup
# ============================================================================


def setup_middleware(app: FastAPI) -> None:
    """Configure all middleware for the application.

    Middleware is added in reverse order (last added = first executed).

    Args:
        app: FastAPI application instance.
    """
    # Error handling (outermost - catches all errors)
    app.add_middleware(ErrorHandlerMiddleware)

    # API key authentication
    app.add_middleware(ApiKeyMiddleware)

    # Request ID correlation (innermost for handlers)
    app.add_middleware(RequestIdMiddleware)
