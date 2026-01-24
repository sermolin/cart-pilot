"""Order API endpoints.

Provides endpoints for order lifecycle management:
- GET /orders - list orders (paginated)
- GET /orders/{id} - order details and status
- POST /orders/{id}/cancel - cancel an order
- POST /orders/{id}/refund - refund an order
- POST /orders/{id}/simulate-advance - advance order state (testing)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.schemas import (
    Currency,
    ErrorResponse,
    OrderAddressSchema,
    OrderCancelRequest,
    OrderCustomerSchema,
    OrderItemSchema,
    OrderRefundRequest,
    OrderResponse,
    OrdersListResponse,
    OrderStatusEnum,
    OrderStatusHistorySchema,
    OrderSummarySchema,
    PriceSchema,
    SimulateTimeRequest,
)
from app.application.order_service import (
    OrderDTO,
    OrderService,
    get_order_service,
)

router = APIRouter(prefix="/orders", tags=["Orders"])


# ============================================================================
# Dependencies
# ============================================================================


def get_service(request: Request) -> OrderService:
    """Get order service with request ID."""
    request_id = getattr(request.state, "request_id", None)
    return get_order_service(request_id=request_id)


# ============================================================================
# Converters
# ============================================================================


def order_to_response(order: OrderDTO) -> OrderResponse:
    """Convert OrderDTO to OrderResponse."""
    currency = Currency(order.currency)

    # Convert items
    items = [
        OrderItemSchema(
            product_id=item.product_id,
            variant_id=item.variant_id,
            sku=item.sku,
            title=item.title,
            quantity=item.quantity,
            unit_price=PriceSchema(amount=item.unit_price_cents, currency=currency),
            line_total=PriceSchema(amount=item.line_total_cents, currency=currency),
        )
        for item in order.items
    ]

    # Convert customer
    customer = OrderCustomerSchema(
        email=order.customer.email,
        name=order.customer.name,
        phone=order.customer.phone,
    )

    # Convert shipping address
    shipping_address = OrderAddressSchema(
        line1=order.shipping_address.line1,
        line2=order.shipping_address.line2,
        city=order.shipping_address.city,
        state=order.shipping_address.state,
        postal_code=order.shipping_address.postal_code,
        country=order.shipping_address.country,
    )

    # Convert billing address
    billing_address = None
    if order.billing_address:
        billing_address = OrderAddressSchema(
            line1=order.billing_address.line1,
            line2=order.billing_address.line2,
            city=order.billing_address.city,
            state=order.billing_address.state,
            postal_code=order.billing_address.postal_code,
            country=order.billing_address.country,
        )

    # Convert refund amount
    refund_amount = None
    if order.refund_amount_cents:
        refund_amount = PriceSchema(amount=order.refund_amount_cents, currency=currency)

    # Convert status history
    status_history = [
        OrderStatusHistorySchema(
            from_status=entry.get("from_status"),
            to_status=entry.get("to_status", ""),
            reason=entry.get("reason"),
            actor=entry.get("actor"),
            metadata=entry.get("metadata"),
            created_at=entry.get("created_at", ""),
        )
        for entry in order.status_history
    ]

    return OrderResponse(
        id=order.id,
        checkout_id=order.checkout_id,
        merchant_id=order.merchant_id,
        merchant_order_id=order.merchant_order_id,
        status=OrderStatusEnum(order.status.value),
        customer=customer,
        shipping_address=shipping_address,
        billing_address=billing_address,
        items=items,
        subtotal=PriceSchema(amount=order.subtotal_cents, currency=currency),
        tax=PriceSchema(amount=order.tax_cents, currency=currency),
        shipping=PriceSchema(amount=order.shipping_cents, currency=currency),
        total=PriceSchema(amount=order.total_cents, currency=currency),
        tracking_number=order.tracking_number,
        carrier=order.carrier,
        cancelled_reason=order.cancelled_reason,
        cancelled_by=order.cancelled_by,
        refund_amount=refund_amount,
        refund_reason=order.refund_reason,
        status_history=status_history,
        created_at=order.created_at,
        updated_at=order.updated_at,
        confirmed_at=order.confirmed_at,
        shipped_at=order.shipped_at,
        delivered_at=order.delivered_at,
        cancelled_at=order.cancelled_at,
        refunded_at=order.refunded_at,
    )


def order_to_summary(order: OrderDTO) -> OrderSummarySchema:
    """Convert OrderDTO to OrderSummarySchema."""
    currency = Currency(order.currency)
    item_count = sum(item.quantity for item in order.items)

    return OrderSummarySchema(
        id=order.id,
        merchant_id=order.merchant_id,
        merchant_order_id=order.merchant_order_id,
        status=OrderStatusEnum(order.status.value),
        total=PriceSchema(amount=order.total_cents, currency=currency),
        item_count=item_count,
        customer_email=order.customer.email,
        created_at=order.created_at,
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "",
    response_model=OrdersListResponse,
    responses={401: {"model": ErrorResponse}},
    summary="List orders",
    description="Get a paginated list of orders with optional filtering.",
)
async def list_orders(
    service: Annotated[OrderService, Depends(get_service)],
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status: str | None = Query(default=None, description="Filter by status"),
    merchant_id: str | None = Query(default=None, description="Filter by merchant"),
) -> OrdersListResponse:
    """List orders with pagination and filtering.

    Args:
        service: Order service.
        page: Page number (1-based).
        page_size: Items per page.
        status: Filter by order status.
        merchant_id: Filter by merchant ID.

    Returns:
        Paginated list of orders.
    """
    result = await service.list_orders(
        page=page,
        page_size=page_size,
        status=status,
        merchant_id=merchant_id,
    )

    items = [order_to_summary(order) for order in result.orders]

    return OrdersListResponse(
        items=items,
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        has_more=(result.page * result.page_size) < result.total,
    )


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    summary="Get order details",
    description="Get detailed information about a specific order.",
)
async def get_order(
    order_id: str,
    service: Annotated[OrderService, Depends(get_service)],
) -> OrderResponse:
    """Get an order by ID.

    Returns full order details including items, addresses,
    shipping info, and status history.

    Args:
        order_id: Order identifier.
        service: Order service.

    Returns:
        Order details.

    Raises:
        HTTPException: If order not found.
    """
    result = await service.get_order(order_id)

    if not result.success or not result.order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": result.error_code or "ORDER_NOT_FOUND",
                "message": result.error or f"Order not found: {order_id}",
            },
        )

    return order_to_response(result.order)


@router.post(
    "/{order_id}/cancel",
    response_model=OrderResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    summary="Cancel order",
    description="Cancel an order. Only pending, confirmed, or shipped orders can be cancelled.",
)
async def cancel_order(
    order_id: str,
    request: OrderCancelRequest,
    service: Annotated[OrderService, Depends(get_service)],
) -> OrderResponse:
    """Cancel an order.

    Orders can be cancelled in pending, confirmed, or shipped status.
    Delivered orders cannot be cancelled.

    Args:
        order_id: Order identifier.
        request: Cancellation request with reason.
        service: Order service.

    Returns:
        Updated order with cancelled status.

    Raises:
        HTTPException: If order not found or cannot be cancelled.
    """
    result = await service.cancel_order(
        order_id=order_id,
        reason=request.reason,
        cancelled_by=request.cancelled_by,
    )

    if not result.success or not result.order:
        status_code = (
            status.HTTP_404_NOT_FOUND
            if result.error_code == "ORDER_NOT_FOUND"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=status_code,
            detail={
                "error_code": result.error_code or "CANCEL_FAILED",
                "message": result.error or "Failed to cancel order",
            },
        )

    return order_to_response(result.order)


@router.post(
    "/{order_id}/refund",
    response_model=OrderResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    summary="Refund order",
    description="Refund a cancelled or delivered order.",
)
async def refund_order(
    order_id: str,
    request: OrderRefundRequest,
    service: Annotated[OrderService, Depends(get_service)],
) -> OrderResponse:
    """Refund an order.

    Refunds can be issued for delivered or cancelled orders.
    If no amount is specified, a full refund is issued.

    Args:
        order_id: Order identifier.
        request: Refund request with amount and reason.
        service: Order service.

    Returns:
        Updated order with refunded status.

    Raises:
        HTTPException: If order not found or cannot be refunded.
    """
    result = await service.refund_order(
        order_id=order_id,
        refund_amount_cents=request.refund_amount_cents,
        reason=request.reason,
    )

    if not result.success or not result.order:
        status_code = (
            status.HTTP_404_NOT_FOUND
            if result.error_code == "ORDER_NOT_FOUND"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=status_code,
            detail={
                "error_code": result.error_code or "REFUND_FAILED",
                "message": result.error or "Failed to refund order",
            },
        )

    return order_to_response(result.order)


@router.post(
    "/{order_id}/simulate-advance",
    response_model=OrderResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    summary="Simulate order advancement (testing)",
    description="Advance order through lifecycle states for testing. "
    "Moves order from pending → confirmed → shipped → delivered.",
)
async def simulate_advance_order(
    order_id: str,
    request: SimulateTimeRequest,
    service: Annotated[OrderService, Depends(get_service)],
) -> OrderResponse:
    """Simulate time advancement for an order.

    Useful for testing order lifecycle without waiting for
    real merchant webhooks. Advances order through:
    pending → confirmed → shipped → delivered

    Args:
        order_id: Order identifier.
        request: Number of steps to advance.
        service: Order service.

    Returns:
        Updated order after advancement.

    Raises:
        HTTPException: If order not found or advancement fails.
    """
    result = await service.simulate_advance_order(
        order_id=order_id,
        steps=request.steps,
    )

    if not result.success or not result.order:
        status_code = (
            status.HTTP_404_NOT_FOUND
            if result.error_code == "ORDER_NOT_FOUND"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=status_code,
            detail={
                "error_code": result.error_code or "SIMULATE_FAILED",
                "message": result.error or "Failed to advance order",
            },
        )

    return order_to_response(result.order)
