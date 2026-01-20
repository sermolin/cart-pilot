"""Merchant A Simulator main application.

A stable, happy-path merchant simulator implementing UCP-like contract.
Provides high inventory, stable pricing, and reliable checkout flow.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic_settings import BaseSettings
import structlog

from app.checkout import CheckoutStore, get_checkout_store
from app.products import ProductStore, get_product_store
from app.schemas import (
    CheckoutSchema,
    CheckoutStatus,
    ConfirmRequest,
    ConfirmResponse,
    Currency,
    ErrorResponse,
    PriceSchema,
    ProductListResponse,
    ProductSchema,
    QuoteRequest,
    WebhookEventType,
)
from app.webhooks import WebhookSender, get_webhook_sender


# ============================================================================
# Configuration
# ============================================================================


class Settings(BaseSettings):
    """Merchant A settings."""

    merchant_id: str = "merchant-a"
    webhook_url: str = "http://cartpilot-api:8000/webhooks/merchant"
    webhook_secret: str = "dev-webhook-secret-change-in-production"
    log_level: str = "INFO"
    products_per_category: int = 5
    random_seed: int = 42

    model_config = {
        "env_file": ".env",
        "extra": "ignore",
    }


settings = Settings()
logger = structlog.get_logger()


# ============================================================================
# Application Lifecycle
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info(
        "Starting Merchant A Simulator",
        merchant_id=settings.merchant_id,
        webhook_url=settings.webhook_url,
    )

    # Initialize stores
    get_product_store(
        merchant_id=settings.merchant_id,
        seed=settings.random_seed,
        products_per_category=settings.products_per_category,
    )
    get_checkout_store()

    yield

    # Shutdown
    webhook_sender = get_webhook_sender()
    await webhook_sender.close()
    logger.info("Merchant A Simulator shutdown complete")


app = FastAPI(
    title="Merchant A Simulator",
    description="Happy path merchant simulator (stable pricing, high inventory)",
    version="1.0.0",
    lifespan=lifespan,
)


# ============================================================================
# Dependencies
# ============================================================================


def get_products() -> ProductStore:
    """Get product store dependency."""
    return get_product_store()


def get_checkouts() -> CheckoutStore:
    """Get checkout store dependency."""
    return get_checkout_store()


def get_webhooks() -> WebhookSender:
    """Get webhook sender dependency."""
    return get_webhook_sender(
        webhook_url=settings.webhook_url,
        webhook_secret=settings.webhook_secret,
        merchant_id=settings.merchant_id,
    )


# ============================================================================
# Response Models
# ============================================================================


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str
    merchant_id: str
    ucp_version: str


class StatsResponse(BaseModel):
    """Store statistics response."""

    merchant_id: str
    product_count: int
    checkout_count: int
    ucp_version: str


# ============================================================================
# Health Endpoints
# ============================================================================


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check() -> HealthResponse:
    """Check service health.

    Returns:
        Health status with merchant info.
    """
    return HealthResponse(
        status="healthy",
        service="merchant-a",
        merchant_id=settings.merchant_id,
        ucp_version="1.0.0",
    )


@app.get("/stats", response_model=StatsResponse, tags=["Health"])
async def get_stats(
    products: Annotated[ProductStore, Depends(get_products)],
    checkouts: Annotated[CheckoutStore, Depends(get_checkouts)],
) -> StatsResponse:
    """Get store statistics.

    Returns:
        Store statistics.
    """
    return StatsResponse(
        merchant_id=settings.merchant_id,
        product_count=len(products._products),
        checkout_count=len(checkouts._sessions),
        ucp_version="1.0.0",
    )


# ============================================================================
# Product Endpoints
# ============================================================================


@app.get("/products", response_model=ProductListResponse, tags=["Products"])
async def list_products(
    products: Annotated[ProductStore, Depends(get_products)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    category_id: Annotated[int | None, Query()] = None,
    brand: Annotated[str | None, Query()] = None,
    min_price: Annotated[int | None, Query(ge=0)] = None,
    max_price: Annotated[int | None, Query(ge=0)] = None,
    in_stock: Annotated[bool | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    sort_by: Annotated[str | None, Query(pattern="^(price|rating)$")] = None,
    sort_order: Annotated[str, Query(pattern="^(asc|desc)$")] = "asc",
) -> ProductListResponse:
    """List products with filtering and pagination.

    Args:
        page: Page number (1-based).
        page_size: Items per page.
        category_id: Filter by category ID.
        brand: Filter by brand name.
        min_price: Minimum price in cents.
        max_price: Maximum price in cents.
        in_stock: Filter by availability.
        search: Search in title/description.
        sort_by: Sort field (price, rating).
        sort_order: Sort order (asc, desc).

    Returns:
        Paginated product list.
    """
    items, total = products.list_products(
        page=page,
        page_size=page_size,
        category_id=category_id,
        brand=brand,
        min_price=min_price,
        max_price=max_price,
        in_stock=in_stock,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    has_more = (page * page_size) < total

    return ProductListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more,
    )


@app.get(
    "/products/{product_id}",
    response_model=ProductSchema,
    responses={404: {"model": ErrorResponse}},
    tags=["Products"],
)
async def get_product(
    product_id: str,
    products: Annotated[ProductStore, Depends(get_products)],
) -> ProductSchema:
    """Get product details by ID.

    Args:
        product_id: Product ID.

    Returns:
        Product details.

    Raises:
        HTTPException: If product not found.
    """
    product = products.get_product(product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "PRODUCT_NOT_FOUND",
                "message": f"Product not found: {product_id}",
            },
        )
    return product


# ============================================================================
# Checkout Endpoints
# ============================================================================


@app.post(
    "/checkout/quote",
    response_model=CheckoutSchema,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    tags=["Checkout"],
)
async def create_quote(
    request: QuoteRequest,
    background_tasks: BackgroundTasks,
    checkouts: Annotated[CheckoutStore, Depends(get_checkouts)],
    webhooks: Annotated[WebhookSender, Depends(get_webhooks)],
) -> CheckoutSchema:
    """Create a quote for items.

    Creates a checkout session with quoted prices for the requested items.
    The quote includes subtotal, tax, shipping, and total.

    Args:
        request: Quote request with items.

    Returns:
        Created checkout session with quote.

    Raises:
        HTTPException: If product not found or insufficient stock.
    """
    try:
        session = checkouts.create_quote(
            items=request.items,
            customer_email=request.customer_email,
            idempotency_key=request.idempotency_key,
        )

        # Send webhook in background
        background_tasks.add_task(
            webhooks.send_checkout_quoted,
            checkout_id=session.id,
            total=session.total,
            currency=session.currency,
            receipt_hash=session.receipt_hash or "",
        )

        logger.info(
            "Quote created",
            checkout_id=session.id,
            total=session.total,
            items_count=len(session.items),
        )

        return checkouts.to_schema(session)

    except ValueError as e:
        logger.warning("Quote creation failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "QUOTE_FAILED",
                "message": str(e),
            },
        )


@app.get(
    "/checkout/{checkout_id}",
    response_model=CheckoutSchema,
    responses={404: {"model": ErrorResponse}},
    tags=["Checkout"],
)
async def get_checkout(
    checkout_id: str,
    checkouts: Annotated[CheckoutStore, Depends(get_checkouts)],
) -> CheckoutSchema:
    """Get checkout session status.

    Args:
        checkout_id: Checkout session ID.

    Returns:
        Checkout session details.

    Raises:
        HTTPException: If checkout not found.
    """
    session = checkouts.get_checkout(checkout_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "CHECKOUT_NOT_FOUND",
                "message": f"Checkout not found: {checkout_id}",
            },
        )
    return checkouts.to_schema(session)


@app.post(
    "/checkout/{checkout_id}/confirm",
    response_model=ConfirmResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
    tags=["Checkout"],
)
async def confirm_checkout(
    checkout_id: str,
    request: ConfirmRequest,
    background_tasks: BackgroundTasks,
    checkouts: Annotated[CheckoutStore, Depends(get_checkouts)],
    webhooks: Annotated[WebhookSender, Depends(get_webhooks)],
) -> ConfirmResponse:
    """Confirm a checkout session.

    Finalizes the checkout and creates an order. This endpoint is
    idempotent if the same idempotency key is provided.

    Args:
        checkout_id: Checkout session ID.
        request: Confirmation request.

    Returns:
        Confirmation response with order details.

    Raises:
        HTTPException: If checkout not found, expired, or already processed.
    """
    try:
        session = checkouts.confirm_checkout(
            checkout_id=checkout_id,
            payment_method=request.payment_method,
            idempotency_key=request.idempotency_key,
        )

        # Send webhooks in background
        background_tasks.add_task(
            webhooks.send_checkout_confirmed,
            checkout_id=session.id,
            merchant_order_id=session.merchant_order_id or "",
            total=session.total,
            currency=session.currency,
        )

        background_tasks.add_task(
            webhooks.send_order_created,
            checkout_id=session.id,
            merchant_order_id=session.merchant_order_id or "",
            total=session.total,
            currency=session.currency,
            items=[
                {
                    "product_id": item.product_id,
                    "variant_id": item.variant_id,
                    "sku": item.sku,
                    "title": item.title,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                }
                for item in session.items
            ],
        )

        logger.info(
            "Checkout confirmed",
            checkout_id=session.id,
            merchant_order_id=session.merchant_order_id,
            total=session.total,
        )

        return ConfirmResponse(
            checkout_id=session.id,
            merchant_order_id=session.merchant_order_id or "",
            status=session.status,
            total=PriceSchema(amount=session.total, currency=Currency.USD),
            confirmed_at=session.updated_at,
        )

    except ValueError as e:
        error_message = str(e)
        logger.warning(
            "Checkout confirmation failed",
            checkout_id=checkout_id,
            error=error_message,
        )

        # Determine appropriate status code
        if "not found" in error_message.lower():
            status_code = status.HTTP_404_NOT_FOUND
            error_code = "CHECKOUT_NOT_FOUND"
        elif "expired" in error_message.lower():
            status_code = status.HTTP_400_BAD_REQUEST
            error_code = "CHECKOUT_EXPIRED"
        elif "price" in error_message.lower():
            status_code = status.HTTP_409_CONFLICT
            error_code = "PRICE_CHANGED"
        elif "state" in error_message.lower():
            status_code = status.HTTP_409_CONFLICT
            error_code = "INVALID_STATE"
        else:
            status_code = status.HTTP_400_BAD_REQUEST
            error_code = "CONFIRMATION_FAILED"

        raise HTTPException(
            status_code=status_code,
            detail={
                "error_code": error_code,
                "message": error_message,
            },
        )


# ============================================================================
# Error Handlers
# ============================================================================


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """Handle HTTP exceptions with consistent format."""
    detail = exc.detail
    if isinstance(detail, dict):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error_code": detail.get("error_code", "ERROR"),
                "message": detail.get("message", str(detail)),
                "details": detail.get("details", []),
            },
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": "ERROR",
            "message": str(detail),
            "details": [],
        },
    )
