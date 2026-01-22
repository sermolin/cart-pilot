"""Merchant B Simulator main application (Chaos Mode).

A chaos-mode merchant simulator for testing edge cases and error handling.
Implements the same UCP contract as Merchant A but with configurable
chaos behaviors for resilience testing.

Chaos Scenarios:
- PRICE_CHANGE: Price changes between quote and confirm
- OUT_OF_STOCK: Items become unavailable after checkout created
- DUPLICATE_WEBHOOK: Same webhook sent multiple times
- DELAYED_WEBHOOK: Webhooks delivered after a delay
- OUT_OF_ORDER_WEBHOOK: Webhooks sent in wrong sequence
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic_settings import BaseSettings
import structlog

from app.chaos import ChaosController, get_chaos_controller
from app.checkout import CheckoutStore, get_checkout_store
from app.products import ProductStore, get_product_store
from app.schemas import (
    ChaosConfigRequest,
    ChaosConfigResponse,
    ChaosEventsResponse,
    ChaosScenario,
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
    """Merchant B settings."""

    merchant_id: str = "merchant-b"
    webhook_url: str = "http://cartpilot-api:8000/webhooks/merchant"
    webhook_secret: str = "dev-webhook-secret-change-in-production"
    chaos_enabled: bool = False
    log_level: str = "INFO"
    products_per_category: int = 5
    random_seed: int = 43  # Different from merchant-a

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
        "Starting Merchant B Simulator (Chaos Mode)",
        merchant_id=settings.merchant_id,
        webhook_url=settings.webhook_url,
        chaos_enabled=settings.chaos_enabled,
    )

    # Initialize stores and controllers
    product_store = get_product_store(
        merchant_id=settings.merchant_id,
        seed=settings.random_seed,
        products_per_category=settings.products_per_category,
    )
    
    chaos_controller = get_chaos_controller()
    
    checkout_store = get_checkout_store()
    checkout_store.set_chaos_controller(chaos_controller)
    
    webhook_sender = get_webhook_sender(
        webhook_url=settings.webhook_url,
        webhook_secret=settings.webhook_secret,
        merchant_id=settings.merchant_id,
    )
    webhook_sender.set_chaos_controller(chaos_controller)

    # Auto-enable chaos if configured
    if settings.chaos_enabled:
        chaos_controller.enable_all()

    yield

    # Shutdown
    await webhook_sender.close()
    logger.info("Merchant B Simulator shutdown complete")


app = FastAPI(
    title="Merchant B Simulator (Chaos Mode)",
    description="""
Chaos mode merchant simulator for resilience testing.

## Chaos Scenarios

- **PRICE_CHANGE**: Prices change between quote and confirm
- **OUT_OF_STOCK**: Items become unavailable after checkout created
- **DUPLICATE_WEBHOOK**: Same webhook sent multiple times
- **DELAYED_WEBHOOK**: Webhooks delivered after a delay
- **OUT_OF_ORDER_WEBHOOK**: Webhooks sent in wrong sequence

## Usage

1. Enable chaos scenarios via `POST /chaos/configure`
2. Perform normal checkout operations
3. Observe chaos behaviors
4. Check chaos event log via `GET /chaos/events`
    """,
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


def get_chaos() -> ChaosController:
    """Get chaos controller dependency."""
    return get_chaos_controller()


# ============================================================================
# Response Models
# ============================================================================


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str
    merchant_id: str
    ucp_version: str
    chaos_enabled: bool


class StatsResponse(BaseModel):
    """Store statistics response."""

    merchant_id: str
    product_count: int
    checkout_count: int
    chaos_event_count: int
    ucp_version: str


class ResetResponse(BaseModel):
    """Reset response."""

    message: str
    reset_products: bool
    reset_checkouts: bool
    reset_chaos: bool


# ============================================================================
# Health Endpoints
# ============================================================================


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check(
    chaos: Annotated[ChaosController, Depends(get_chaos)],
) -> HealthResponse:
    """Check service health.

    Returns:
        Health status with merchant info and chaos mode status.
    """
    return HealthResponse(
        status="healthy",
        service="merchant-b",
        merchant_id=settings.merchant_id,
        ucp_version="1.0.0",
        chaos_enabled=chaos.config.enabled,
    )


@app.get("/stats", response_model=StatsResponse, tags=["Health"])
async def get_stats(
    products: Annotated[ProductStore, Depends(get_products)],
    checkouts: Annotated[CheckoutStore, Depends(get_checkouts)],
    chaos: Annotated[ChaosController, Depends(get_chaos)],
) -> StatsResponse:
    """Get store statistics.

    Returns:
        Store statistics including chaos event count.
    """
    return StatsResponse(
        merchant_id=settings.merchant_id,
        product_count=len(products._products),
        checkout_count=len(checkouts._sessions),
        chaos_event_count=len(chaos._event_log),
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

    Note: With chaos mode enabled, prices or stock may change before confirm.

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

    CHAOS MODE: This is where chaos scenarios trigger:
    - Price changes will cause PRICE_CHANGED error
    - Out-of-stock will cause OUT_OF_STOCK error

    Args:
        checkout_id: Checkout session ID.
        request: Confirmation request.

    Returns:
        Confirmation response with order details.

    Raises:
        HTTPException: If checkout not found, expired, or chaos triggered.
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

        # Determine appropriate status code and error code
        if "not found" in error_message.lower():
            status_code = status.HTTP_404_NOT_FOUND
            error_code = "CHECKOUT_NOT_FOUND"
        elif "expired" in error_message.lower():
            status_code = status.HTTP_400_BAD_REQUEST
            error_code = "CHECKOUT_EXPIRED"
        elif "price" in error_message.lower():
            status_code = status.HTTP_409_CONFLICT
            error_code = "PRICE_CHANGED"
            # Send price changed webhook
            background_tasks.add_task(
                webhooks.send_checkout_failed,
                checkout_id=checkout_id,
                reason=error_message,
                error_code="PRICE_CHANGED",
            )
        elif "stock" in error_message.lower():
            status_code = status.HTTP_409_CONFLICT
            error_code = "OUT_OF_STOCK"
            # Send failed webhook
            background_tasks.add_task(
                webhooks.send_checkout_failed,
                checkout_id=checkout_id,
                reason=error_message,
                error_code="OUT_OF_STOCK",
            )
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
# Chaos Mode Endpoints
# ============================================================================


@app.post(
    "/chaos/configure",
    response_model=ChaosConfigResponse,
    tags=["Chaos Mode"],
)
async def configure_chaos(
    request: ChaosConfigRequest,
    chaos: Annotated[ChaosController, Depends(get_chaos)],
) -> ChaosConfigResponse:
    """Configure chaos mode scenarios.

    Enable or disable specific chaos scenarios and configure parameters.

    Args:
        request: Chaos configuration request.

    Returns:
        Updated chaos configuration.
    """
    return chaos.configure(request)


@app.get(
    "/chaos/config",
    response_model=ChaosConfigResponse,
    tags=["Chaos Mode"],
)
async def get_chaos_config(
    chaos: Annotated[ChaosController, Depends(get_chaos)],
) -> ChaosConfigResponse:
    """Get current chaos mode configuration.

    Returns:
        Current chaos configuration.
    """
    return chaos.get_config()


@app.post(
    "/chaos/enable",
    response_model=ChaosConfigResponse,
    tags=["Chaos Mode"],
)
async def enable_all_chaos(
    chaos: Annotated[ChaosController, Depends(get_chaos)],
) -> ChaosConfigResponse:
    """Enable all chaos scenarios.

    Returns:
        Updated chaos configuration.
    """
    return chaos.enable_all()


@app.post(
    "/chaos/disable",
    response_model=ChaosConfigResponse,
    tags=["Chaos Mode"],
)
async def disable_all_chaos(
    chaos: Annotated[ChaosController, Depends(get_chaos)],
) -> ChaosConfigResponse:
    """Disable all chaos scenarios.

    Returns:
        Updated chaos configuration.
    """
    return chaos.disable_all()


@app.post(
    "/chaos/scenarios/{scenario}/enable",
    response_model=ChaosConfigResponse,
    tags=["Chaos Mode"],
)
async def enable_chaos_scenario(
    scenario: ChaosScenario,
    chaos: Annotated[ChaosController, Depends(get_chaos)],
) -> ChaosConfigResponse:
    """Enable a specific chaos scenario.

    Args:
        scenario: Chaos scenario to enable.

    Returns:
        Updated chaos configuration.
    """
    return chaos.enable_scenario(scenario)


@app.post(
    "/chaos/scenarios/{scenario}/disable",
    response_model=ChaosConfigResponse,
    tags=["Chaos Mode"],
)
async def disable_chaos_scenario(
    scenario: ChaosScenario,
    chaos: Annotated[ChaosController, Depends(get_chaos)],
) -> ChaosConfigResponse:
    """Disable a specific chaos scenario.

    Args:
        scenario: Chaos scenario to disable.

    Returns:
        Updated chaos configuration.
    """
    return chaos.disable_scenario(scenario)


@app.get(
    "/chaos/events",
    response_model=ChaosEventsResponse,
    tags=["Chaos Mode"],
)
async def get_chaos_events(
    chaos: Annotated[ChaosController, Depends(get_chaos)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    scenario: Annotated[ChaosScenario | None, Query()] = None,
    checkout_id: Annotated[str | None, Query()] = None,
) -> ChaosEventsResponse:
    """Get chaos event log.

    Returns log of triggered chaos events for debugging.

    Args:
        limit: Maximum events to return.
        scenario: Filter by specific scenario.
        checkout_id: Filter by checkout ID.

    Returns:
        Chaos event log.
    """
    return chaos.get_events(
        limit=limit,
        scenario=scenario,
        checkout_id=checkout_id,
    )


@app.delete(
    "/chaos/events",
    tags=["Chaos Mode"],
)
async def clear_chaos_events(
    chaos: Annotated[ChaosController, Depends(get_chaos)],
) -> dict[str, Any]:
    """Clear chaos event log.

    Returns:
        Number of events cleared.
    """
    count = chaos.clear_events()
    return {"cleared": count}


@app.post(
    "/chaos/reset",
    response_model=ChaosConfigResponse,
    tags=["Chaos Mode"],
)
async def reset_chaos(
    chaos: Annotated[ChaosController, Depends(get_chaos)],
) -> ChaosConfigResponse:
    """Reset chaos controller to default state.

    Disables all scenarios and clears event log.

    Returns:
        Reset chaos configuration.
    """
    return chaos.reset()


@app.post(
    "/chaos/flush-webhooks",
    tags=["Chaos Mode"],
)
async def flush_pending_webhooks(
    webhooks: Annotated[WebhookSender, Depends(get_webhooks)],
) -> dict[str, Any]:
    """Flush pending webhooks (for out-of-order chaos).

    Sends all queued webhooks in random order.

    Returns:
        Number of webhooks flushed.
    """
    count = await webhooks.flush_pending_webhooks()
    return {"flushed": count}


# ============================================================================
# Admin/Test Endpoints
# ============================================================================


@app.post(
    "/admin/reset",
    response_model=ResetResponse,
    tags=["Admin"],
)
async def reset_all(
    products: Annotated[ProductStore, Depends(get_products)],
    checkouts: Annotated[CheckoutStore, Depends(get_checkouts)],
    chaos: Annotated[ChaosController, Depends(get_chaos)],
) -> ResetResponse:
    """Reset all state for testing.

    Resets products, checkouts, and chaos configuration.

    Returns:
        Reset confirmation.
    """
    products.reset_all_products()
    checkouts.reset_all()
    chaos.reset()

    logger.info("All state reset")

    return ResetResponse(
        message="All state reset successfully",
        reset_products=True,
        reset_checkouts=True,
        reset_chaos=True,
    )


@app.post(
    "/admin/trigger-price-change/{product_id}",
    tags=["Admin"],
)
async def trigger_price_change(
    product_id: str,
    products: Annotated[ProductStore, Depends(get_products)],
    increase: Annotated[bool, Query()] = True,
) -> dict[str, Any]:
    """Manually trigger a price change for a product.

    Args:
        product_id: Product ID.
        increase: Whether to increase (True) or decrease (False) price.

    Returns:
        Price change details.
    """
    result = products.trigger_price_change(product_id, increase=increase)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "PRODUCT_NOT_FOUND",
                "message": f"Product not found: {product_id}",
            },
        )

    old_price, new_price = result
    return {
        "product_id": product_id,
        "old_price": old_price,
        "new_price": new_price,
        "change": new_price - old_price,
        "change_percent": round((new_price - old_price) / old_price * 100, 1),
    }


@app.post(
    "/admin/trigger-out-of-stock/{product_id}",
    tags=["Admin"],
)
async def trigger_out_of_stock(
    product_id: str,
    products: Annotated[ProductStore, Depends(get_products)],
    variant_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    """Manually mark a product or variant as out of stock.

    Args:
        product_id: Product ID.
        variant_id: Optional variant ID.

    Returns:
        Confirmation.
    """
    success = products.trigger_out_of_stock(product_id, variant_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "PRODUCT_NOT_FOUND",
                "message": f"Product or variant not found",
            },
        )

    return {
        "product_id": product_id,
        "variant_id": variant_id,
        "in_stock": False,
    }


@app.post(
    "/admin/reset-product/{product_id}",
    tags=["Admin"],
)
async def reset_product(
    product_id: str,
    products: Annotated[ProductStore, Depends(get_products)],
) -> dict[str, Any]:
    """Reset a product to its original state.

    Args:
        product_id: Product ID.

    Returns:
        Confirmation.
    """
    success = products.reset_product(product_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "PRODUCT_NOT_FOUND",
                "message": f"Product not found: {product_id}",
            },
        )

    return {
        "product_id": product_id,
        "reset": True,
    }


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
