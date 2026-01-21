"""Offer API endpoints.

Provides endpoints for retrieving offer details.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.schemas import (
    ErrorResponse,
    OfferItemSchema,
    OfferResponse,
    PriceSchema,
)
from app.application.intent_service import IntentService, get_intent_service
from app.domain.entities import Offer

router = APIRouter(prefix="/offers", tags=["Offers"])


# ============================================================================
# Dependencies
# ============================================================================


def get_service(request: Request) -> IntentService:
    """Get intent service with request ID."""
    request_id = getattr(request.state, "request_id", None)
    return get_intent_service(request_id=request_id)


# ============================================================================
# Converters
# ============================================================================


def offer_to_response(offer: Offer) -> OfferResponse:
    """Convert Offer entity to response schema."""
    items = [
        OfferItemSchema(
            product_id=item.product_id,
            variant_id=item.variant_id,
            sku=item.sku,
            title=item.title,
            description=item.description,
            brand=item.brand,
            category_path=item.category_path,
            price=PriceSchema(
                amount=item.unit_price.amount_cents,
                currency=item.unit_price.currency,  # type: ignore
            ),
            quantity_available=item.quantity_available,
            image_url=item.image_url,
            rating=item.rating,
            review_count=item.review_count,
        )
        for item in offer.items
    ]

    lowest = offer.lowest_price
    highest = offer.highest_price

    return OfferResponse(
        id=str(offer.id),
        intent_id=str(offer.intent_id),
        merchant_id=str(offer.merchant_id),
        items=items,
        item_count=offer.item_count,
        lowest_price=(
            PriceSchema(amount=lowest.amount_cents, currency=lowest.currency)  # type: ignore
            if lowest
            else None
        ),
        highest_price=(
            PriceSchema(amount=highest.amount_cents, currency=highest.currency)  # type: ignore
            if highest
            else None
        ),
        expires_at=offer.expires_at,
        is_expired=offer.is_expired,
        metadata=dict(offer.metadata),
        created_at=offer.created_at,
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "/{offer_id}",
    response_model=OfferResponse,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    summary="Get offer details",
    description="Get detailed information about a specific offer.",
)
async def get_offer(
    offer_id: str,
    service: Annotated[IntentService, Depends(get_service)],
) -> OfferResponse:
    """Get an offer by ID.

    Returns full offer details including all product items,
    pricing information, and merchant details.

    Args:
        offer_id: Offer identifier.
        service: Intent service.

    Returns:
        Offer details.

    Raises:
        HTTPException: If offer not found.
    """
    result = await service.get_offer(offer_id)

    if not result.success or not result.offer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "OFFER_NOT_FOUND",
                "message": result.error or f"Offer not found: {offer_id}",
            },
        )

    return offer_to_response(result.offer)
