"""Checkout API endpoints.

Provides endpoints for the checkout approval flow:
- POST /checkouts - create checkout from offer
- POST /checkouts/{id}/quote - get quote from merchant
- POST /checkouts/{id}/request-approval - freeze receipt, request approval
- POST /checkouts/{id}/approve - approve purchase
- POST /checkouts/{id}/confirm - execute purchase
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.schemas import (
    AuditEntrySchema,
    CheckoutApproveRequest,
    CheckoutConfirmRequest,
    CheckoutConfirmResponse,
    CheckoutCreateRequest,
    CheckoutItemSchema,
    CheckoutQuoteRequest,
    CheckoutResponse,
    CheckoutStatusEnum,
    Currency,
    ErrorResponse,
    FrozenReceiptItemSchema,
    FrozenReceiptSchema,
    PriceSchema,
    ReapprovalRequiredResponse,
)
from app.application.checkout_service import CheckoutService, get_checkout_service
from app.application.intent_service import get_offer_repository
from app.domain.entities import Checkout

router = APIRouter(prefix="/checkouts", tags=["Checkouts"])


# ============================================================================
# Dependencies
# ============================================================================


def get_service(request: Request) -> CheckoutService:
    """Get checkout service with request ID."""
    request_id = getattr(request.state, "request_id", None)
    offer_repo = get_offer_repository()
    return get_checkout_service(request_id=request_id, offer_repo=offer_repo)


# ============================================================================
# Converters
# ============================================================================


def checkout_to_response(checkout: Checkout) -> CheckoutResponse:
    """Convert Checkout entity to response schema."""
    # Convert items
    items = [
        CheckoutItemSchema(
            product_id=item.product_id,
            variant_id=item.variant_id,
            sku=item.sku,
            title=item.title,
            unit_price=PriceSchema(
                amount=item.unit_price_cents,
                currency=Currency(item.currency),
            ),
            quantity=item.quantity,
            line_total=PriceSchema(
                amount=item.line_total_cents,
                currency=Currency(item.currency),
            ),
        )
        for item in checkout.items
    ]

    # Convert frozen receipt if present
    frozen_receipt = None
    if checkout.frozen_receipt:
        fr = checkout.frozen_receipt
        frozen_receipt = FrozenReceiptSchema(
            hash=fr.hash,
            items=[
                FrozenReceiptItemSchema(
                    product_id=fi.product_id,
                    variant_id=fi.variant_id,
                    sku=fi.sku,
                    title=fi.title,
                    unit_price_cents=fi.unit_price_cents,
                    quantity=fi.quantity,
                    currency=fi.currency,
                )
                for fi in fr.items
            ],
            subtotal_cents=fr.subtotal_cents,
            tax_cents=fr.tax_cents,
            shipping_cents=fr.shipping_cents,
            total_cents=fr.total_cents,
            currency=fr.currency,
            frozen_at=fr.frozen_at,
        )

    # Convert audit trail
    audit_trail = [
        AuditEntrySchema(
            timestamp=entry.timestamp,
            action=entry.action,
            from_status=entry.from_status,
            to_status=entry.to_status,
            actor=entry.actor,
            details=dict(entry.details) if entry.details else None,
        )
        for entry in checkout.audit_trail
    ]

    # Build pricing schemas
    subtotal = None
    tax = None
    shipping = None
    total = None

    if checkout.total_cents > 0:
        currency = Currency(checkout.currency)
        subtotal = PriceSchema(amount=checkout.subtotal_cents, currency=currency)
        tax = PriceSchema(amount=checkout.tax_cents, currency=currency)
        shipping = PriceSchema(amount=checkout.shipping_cents, currency=currency)
        total = PriceSchema(amount=checkout.total_cents, currency=currency)

    return CheckoutResponse(
        id=str(checkout.id),
        offer_id=str(checkout.offer_id),
        merchant_id=str(checkout.merchant_id),
        status=CheckoutStatusEnum(checkout.status.value),
        items=items,
        subtotal=subtotal,
        tax=tax,
        shipping=shipping,
        total=total,
        merchant_checkout_id=checkout.merchant_checkout_id,
        receipt_hash=checkout.receipt_hash,
        frozen_receipt=frozen_receipt,
        merchant_order_id=checkout.merchant_order_id,
        approved_by=checkout.approved_by,
        approved_at=checkout.approved_at,
        confirmed_at=checkout.confirmed_at,
        expires_at=checkout.expires_at,
        failure_reason=checkout.failure_reason,
        audit_trail=audit_trail,
        created_at=checkout.created_at,
        updated_at=checkout.updated_at,
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.post(
    "",
    response_model=CheckoutResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    summary="Create checkout from offer",
    description="Create a new checkout session from an offer. State: created",
)
async def create_checkout(
    request: CheckoutCreateRequest,
    service: Annotated[CheckoutService, Depends(get_service)],
) -> CheckoutResponse:
    """Create a checkout from an offer.

    Creates a new checkout session in 'created' state.
    Use the idempotency_key to safely retry requests.

    Args:
        request: Checkout creation request.
        service: Checkout service.

    Returns:
        Created checkout.

    Raises:
        HTTPException: If offer not found or creation fails.
    """
    items = [
        {"product_id": i.product_id, "variant_id": i.variant_id, "quantity": i.quantity}
        for i in request.items
    ]

    result = await service.create_checkout(
        offer_id=request.offer_id,
        items=items,
        idempotency_key=request.idempotency_key,
    )

    if not result.success or not result.checkout:
        status_code = status.HTTP_404_NOT_FOUND if result.error_code == "OFFER_NOT_FOUND" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(
            status_code=status_code,
            detail={
                "error_code": result.error_code or "CREATE_FAILED",
                "message": result.error or "Failed to create checkout",
            },
        )

    return checkout_to_response(result.checkout)


@router.get(
    "/{checkout_id}",
    response_model=CheckoutResponse,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    summary="Get checkout details",
    description="Get detailed information about a checkout session.",
)
async def get_checkout(
    checkout_id: str,
    service: Annotated[CheckoutService, Depends(get_service)],
) -> CheckoutResponse:
    """Get a checkout by ID.

    Returns full checkout details including pricing, items,
    frozen receipt, and audit trail.

    Args:
        checkout_id: Checkout identifier.
        service: Checkout service.

    Returns:
        Checkout details.

    Raises:
        HTTPException: If checkout not found.
    """
    checkout = await service.get_checkout(checkout_id)

    if not checkout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "CHECKOUT_NOT_FOUND",
                "message": f"Checkout not found: {checkout_id}",
            },
        )

    return checkout_to_response(checkout)


@router.post(
    "/{checkout_id}/quote",
    response_model=CheckoutResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ReapprovalRequiredResponse},
    },
    summary="Get quote from merchant",
    description="Get a quote from the merchant for the checkout items. State: quoted",
)
async def quote_checkout(
    checkout_id: str,
    request: CheckoutQuoteRequest,
    service: Annotated[CheckoutService, Depends(get_service)],
) -> CheckoutResponse:
    """Get a quote from the merchant.

    Contacts the merchant to get current pricing for the items.
    Transitions checkout to 'quoted' state.

    If called on an approved checkout with price changes,
    returns 409 with reapproval required.

    Args:
        checkout_id: Checkout identifier.
        request: Quote request with items.
        service: Checkout service.

    Returns:
        Updated checkout with quote.

    Raises:
        HTTPException: If checkout not found or quote fails.
    """
    items = [
        {"product_id": i.product_id, "variant_id": i.variant_id, "quantity": i.quantity}
        for i in request.items
    ]

    result = await service.get_quote(
        checkout_id=checkout_id,
        items=items,
        customer_email=request.customer_email,
    )

    if not result.success or not result.checkout:
        status_code = (
            status.HTTP_404_NOT_FOUND
            if result.error_code == "CHECKOUT_NOT_FOUND"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=status_code,
            detail={
                "error_code": result.error_code or "QUOTE_FAILED",
                "message": result.error or "Failed to get quote",
            },
        )

    # Note: reapproval_required is included in response via status change
    return checkout_to_response(result.checkout)


@router.post(
    "/{checkout_id}/request-approval",
    response_model=CheckoutResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    summary="Request approval",
    description="Request approval for the checkout. Freezes the receipt for price change detection. State: awaiting_approval",
)
async def request_approval(
    checkout_id: str,
    service: Annotated[CheckoutService, Depends(get_service)],
) -> CheckoutResponse:
    """Request approval and freeze the receipt.

    Transitions checkout to 'awaiting_approval' state and creates
    a frozen receipt snapshot for detecting price changes.

    Args:
        checkout_id: Checkout identifier.
        service: Checkout service.

    Returns:
        Updated checkout with frozen receipt.

    Raises:
        HTTPException: If checkout not found or not in valid state.
    """
    result = await service.request_approval(checkout_id=checkout_id)

    if not result.success or not result.checkout:
        status_code = (
            status.HTTP_404_NOT_FOUND
            if result.error_code == "CHECKOUT_NOT_FOUND"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=status_code,
            detail={
                "error_code": result.error_code or "APPROVAL_REQUEST_FAILED",
                "message": result.error or "Failed to request approval",
            },
        )

    return checkout_to_response(result.checkout)


@router.post(
    "/{checkout_id}/approve",
    response_model=CheckoutResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ReapprovalRequiredResponse},
    },
    summary="Approve checkout",
    description="Approve the checkout for purchase. State: approved",
)
async def approve_checkout(
    checkout_id: str,
    request: CheckoutApproveRequest,
    service: Annotated[CheckoutService, Depends(get_service)],
) -> CheckoutResponse:
    """Approve the checkout.

    Transitions checkout to 'approved' state.
    If price has changed since approval was requested,
    returns 409 with REAPPROVAL_REQUIRED.

    Args:
        checkout_id: Checkout identifier.
        request: Approval request.
        service: Checkout service.

    Returns:
        Updated checkout.

    Raises:
        HTTPException: If checkout not found, expired, or price changed.
    """
    result = await service.approve(
        checkout_id=checkout_id,
        approved_by=request.approved_by,
    )

    if not result.success or not result.checkout:
        if result.error_code == "REAPPROVAL_REQUIRED":
            # Get checkout to include price info
            checkout = await service.get_checkout(checkout_id)
            if checkout and checkout.frozen_receipt:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error_code": "REAPPROVAL_REQUIRED",
                        "message": "Price has changed, re-approval required",
                        "checkout_id": checkout_id,
                        "original_total": {
                            "amount": checkout.frozen_receipt.total_cents,
                            "currency": checkout.frozen_receipt.currency,
                        },
                        "new_total": {
                            "amount": checkout.total_cents,
                            "currency": checkout.currency,
                        },
                    },
                )

        status_code = (
            status.HTTP_404_NOT_FOUND
            if result.error_code == "CHECKOUT_NOT_FOUND"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=status_code,
            detail={
                "error_code": result.error_code or "APPROVAL_FAILED",
                "message": result.error or "Failed to approve checkout",
            },
        )

    return checkout_to_response(result.checkout)


@router.post(
    "/{checkout_id}/confirm",
    response_model=CheckoutConfirmResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ReapprovalRequiredResponse},
    },
    summary="Confirm checkout (execute purchase)",
    description="Execute the purchase with the merchant. State: confirmed",
)
async def confirm_checkout(
    checkout_id: str,
    request: CheckoutConfirmRequest,
    service: Annotated[CheckoutService, Depends(get_service)],
) -> CheckoutConfirmResponse:
    """Confirm the checkout and execute the purchase.

    Calls the merchant to confirm the checkout and create an order.
    Requires checkout to be in 'approved' state.

    If price has changed, returns 409 with REAPPROVAL_REQUIRED.

    Args:
        checkout_id: Checkout identifier.
        request: Confirmation request.
        service: Checkout service.

    Returns:
        Confirmation response with merchant order ID.

    Raises:
        HTTPException: If checkout not found, not approved, or price changed.
    """
    result = await service.confirm(
        checkout_id=checkout_id,
        payment_method=request.payment_method,
        idempotency_key=request.idempotency_key,
    )

    if not result.success or not result.checkout:
        if result.reapproval_required:
            checkout = await service.get_checkout(checkout_id)
            if checkout and checkout.frozen_receipt:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error_code": "REAPPROVAL_REQUIRED",
                        "message": result.error or "Price has changed, re-approval required",
                        "checkout_id": checkout_id,
                        "original_total": {
                            "amount": checkout.frozen_receipt.total_cents,
                            "currency": checkout.frozen_receipt.currency,
                        },
                        "new_total": {
                            "amount": checkout.total_cents,
                            "currency": checkout.currency,
                        },
                    },
                )

        status_code = (
            status.HTTP_404_NOT_FOUND
            if result.error_code == "CHECKOUT_NOT_FOUND"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=status_code,
            detail={
                "error_code": result.error_code or "CONFIRM_FAILED",
                "message": result.error or "Failed to confirm checkout",
            },
        )

    checkout = result.checkout
    return CheckoutConfirmResponse(
        checkout_id=str(checkout.id),
        merchant_order_id=result.merchant_order_id or "",
        order_id=result.order_id,
        status=CheckoutStatusEnum(checkout.status.value),
        total=PriceSchema(
            amount=checkout.total_cents,
            currency=Currency(checkout.currency),
        ),
        confirmed_at=checkout.confirmed_at or checkout.updated_at,
    )
