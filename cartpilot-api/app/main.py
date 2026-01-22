"""CartPilot API main application module.

This module initializes the FastAPI application and configures
core middleware, routers, and startup/shutdown events.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.checkouts import router as checkouts_router
from app.api.health import router as health_router
from app.api.idempotency import setup_idempotency_middleware
from app.api.intents import router as intents_router
from app.api.merchants import router as merchants_router
from app.api.middleware import setup_middleware
from app.api.offers import router as offers_router
from app.api.webhooks import router as webhooks_router
from app.infrastructure.config import settings
from app.infrastructure.merchant_client import get_merchant_registry

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Handle application startup and shutdown events.

    Args:
        app: The FastAPI application instance.

    Yields:
        None after startup, cleanup happens after yield.
    """
    # Startup
    logger.info(
        "Starting CartPilot API",
        version=settings.api_version,
        debug=settings.debug,
    )

    # Initialize merchant registry
    registry = get_merchant_registry()
    logger.info(
        "Merchant discovery complete",
        merchant_count=len(registry.list_merchants()),
        merchants=registry.get_enabled_merchant_ids(),
    )

    yield

    # Shutdown
    logger.info("Shutting down CartPilot API")


app = FastAPI(
    title="CartPilot API",
    description="Agent-first commerce orchestration backend",
    version=settings.api_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware (must be added before custom middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup custom middleware (request ID, API key auth, error handling)
setup_middleware(app)

# Setup idempotency middleware
setup_idempotency_middleware(app)

# Include routers
app.include_router(health_router, tags=["Health"])
app.include_router(intents_router)
app.include_router(offers_router)
app.include_router(checkouts_router)
app.include_router(merchants_router)
app.include_router(webhooks_router)


# ============================================================================
# Custom Exception Handlers
# ============================================================================


from fastapi import HTTPException


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """Handle HTTP exceptions with consistent format."""
    request_id = getattr(request.state, "request_id", None)

    # Extract error details from exception
    detail = exc.detail
    if isinstance(detail, dict):
        error_code = detail.get("error_code", "ERROR")
        message = detail.get("message", str(detail))
        details = detail.get("details", [])
    else:
        error_code = "ERROR"
        message = str(detail)
        details = []

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": error_code,
            "message": message,
            "details": details,
            "request_id": request_id,
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    """Handle uncaught exceptions with consistent format."""
    request_id = getattr(request.state, "request_id", None)

    logger.exception(
        "Unhandled exception in handler",
        path=request.url.path,
        method=request.method,
        error=str(exc),
    )

    return JSONResponse(
        status_code=500,
        content={
            "error_code": "INTERNAL_ERROR",
            "message": "An internal error occurred",
            "details": [],
            "request_id": request_id,
        },
    )
