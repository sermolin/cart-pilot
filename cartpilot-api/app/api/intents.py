"""Intent API endpoints.

Provides endpoints for creating and managing purchase intents.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.schemas import (
    ErrorResponse,
    IntentCreateRequest,
    IntentResponse,
    IntentsListResponse,
    OfferItemSchema,
    OfferResponse,
    OffersListResponse,
    PriceSchema,
)
from app.application.intent_service import IntentService, get_intent_service
from app.domain.entities import Intent, Offer

router = APIRouter(prefix="/intents", tags=["Intents"])


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


def intent_to_response(intent: Intent, offer_count: int = 0) -> IntentResponse:
    """Convert Intent entity to response schema."""
    return IntentResponse(
        id=str(intent.id),
        query=intent.query,
        session_id=intent.session_id,
        metadata=dict(intent.metadata),
        offers_collected=intent.offers_collected,
        offer_count=offer_count or len(intent.offer_ids),
        created_at=intent.created_at,
        updated_at=intent.updated_at,
    )


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


@router.post(
    "",
    response_model=IntentResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    summary="Create purchase intent",
    description="Create a new purchase intent from a natural language query.",
)
async def create_intent(
    request: IntentCreateRequest,
    service: Annotated[IntentService, Depends(get_service)],
) -> IntentResponse:
    """Create a new purchase intent.

    The intent captures the user's purchase intention from their query.
    After creating an intent, use the offers endpoint to collect offers
    from merchants.

    Args:
        request: Intent creation request.
        service: Intent service.

    Returns:
        Created intent.

    Raises:
        HTTPException: On validation or creation error.
    """
    result = await service.create_intent(
        query=request.query,
        session_id=request.session_id,
        metadata=request.metadata,
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "INTENT_CREATION_FAILED",
                "message": result.error or "Failed to create intent",
            },
        )

    return intent_to_response(result.intent)


@router.get(
    "/{intent_id}",
    response_model=IntentResponse,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    summary="Get intent",
    description="Get an intent by ID.",
)
async def get_intent(
    intent_id: str,
    service: Annotated[IntentService, Depends(get_service)],
) -> IntentResponse:
    """Get an intent by ID.

    Args:
        intent_id: Intent identifier.
        service: Intent service.

    Returns:
        Intent details.

    Raises:
        HTTPException: If intent not found.
    """
    result = await service.get_intent(intent_id)

    if not result.success or not result.intent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "INTENT_NOT_FOUND",
                "message": result.error or f"Intent not found: {intent_id}",
            },
        )

    return intent_to_response(result.intent, len(result.offers))


@router.get(
    "/{intent_id}/offers",
    response_model=OffersListResponse,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
    summary="Get offers for intent",
    description="Get offers from merchants for this intent. If offers haven't been collected yet, this will trigger collection from all enabled merchants.",
)
async def get_intent_offers(
    intent_id: str,
    service: Annotated[IntentService, Depends(get_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> OffersListResponse:
    """Get offers for an intent.

    If offers haven't been collected yet, this endpoint will automatically
    collect offers from all enabled merchants. Subsequent calls will return
    cached offers.

    Args:
        intent_id: Intent identifier.
        service: Intent service.
        page: Page number.
        page_size: Items per page.

    Returns:
        Paginated list of offers.

    Raises:
        HTTPException: If intent not found.
    """
    # First, get the intent
    intent_result = await service.get_intent(intent_id)

    if not intent_result.success or not intent_result.intent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "INTENT_NOT_FOUND",
                "message": intent_result.error or f"Intent not found: {intent_id}",
            },
        )

    intent = intent_result.intent

    # If offers haven't been collected, collect them now
    if not intent.offers_collected:
        collect_result = await service.collect_offers(intent_id)

        if not collect_result.success and not collect_result.offers:
            # Log errors but continue - we might have partial results
            pass

    # Get paginated offers
    offers, total = await service.list_offers_for_intent(
        intent_id, page=page, page_size=page_size
    )

    has_more = (page * page_size) < total

    return OffersListResponse(
        items=[offer_to_response(o) for o in offers],
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more,
        intent_id=intent_id,
    )
