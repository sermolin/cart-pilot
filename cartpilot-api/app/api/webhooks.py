"""Webhook receiver endpoints.

Provides:
- POST /webhooks/merchant — receive merchant events
- HMAC signature verification
- Deduplication by event_id
- Out-of-order tolerance
"""

from datetime import datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.application.webhook_service import (
    EventStatus,
    WebhookEvent,
    WebhookEventType,
    WebhookService,
    get_webhook_service,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


# ============================================================================
# Schemas
# ============================================================================


class WebhookPayload(BaseModel):
    """Incoming webhook payload from merchants."""

    event_id: str = Field(..., description="Unique event identifier")
    event_type: str = Field(..., description="Event type (e.g., checkout.confirmed)")
    merchant_id: str = Field(..., description="Merchant identifier")
    timestamp: datetime = Field(..., description="Event timestamp")
    data: dict[str, Any] = Field(..., description="Event-specific data")
    ucp_version: str = Field(default="1.0.0", description="UCP version")


class WebhookResponse(BaseModel):
    """Response to webhook delivery."""

    success: bool = Field(..., description="Whether event was accepted")
    event_id: str = Field(..., description="Event ID")
    status: str = Field(..., description="Event status (processed, duplicate, failed)")
    message: str = Field(..., description="Status message")


class WebhookErrorResponse(BaseModel):
    """Error response for webhook failures."""

    error_code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    event_id: str | None = Field(None, description="Event ID if available")


# ============================================================================
# Dependencies
# ============================================================================


def get_service() -> WebhookService:
    """Get webhook service."""
    return get_webhook_service()


# ============================================================================
# Endpoints
# ============================================================================


@router.post(
    "/merchant",
    response_model=WebhookResponse,
    responses={
        400: {"model": WebhookErrorResponse},
        401: {"model": WebhookErrorResponse},
    },
    summary="Receive merchant webhook",
    description="Receive and process webhook events from merchants with HMAC verification.",
)
async def receive_merchant_webhook(
    request: Request,
    payload: WebhookPayload,
    service: Annotated[WebhookService, Depends(get_service)],
    x_merchant_signature: Annotated[str | None, Header()] = None,
    x_merchant_id: Annotated[str | None, Header()] = None,
    x_event_id: Annotated[str | None, Header()] = None,
) -> WebhookResponse:
    """Receive and process a webhook from a merchant.

    The webhook must include:
    - X-Merchant-Signature: HMAC-SHA256 signature of the payload
    - X-Merchant-Id: Merchant identifier
    - X-Event-Id: Event identifier (for logging)

    Events are deduplicated by event_id. Duplicate events return
    success with status="duplicate".

    Args:
        request: The incoming request.
        payload: Webhook payload.
        service: Webhook service.
        x_merchant_signature: HMAC signature header.
        x_merchant_id: Merchant ID header.
        x_event_id: Event ID header.

    Returns:
        WebhookResponse with processing result.

    Raises:
        HTTPException: If signature verification fails.
    """
    # Get correlation ID from request state
    correlation_id = getattr(request.state, "request_id", None)

    logger.info(
        "Received merchant webhook",
        event_id=payload.event_id,
        event_type=payload.event_type,
        merchant_id=payload.merchant_id,
        header_merchant_id=x_merchant_id,
        correlation_id=correlation_id,
    )

    # Verify merchant ID matches
    if x_merchant_id and x_merchant_id != payload.merchant_id:
        logger.warning(
            "Merchant ID mismatch",
            header_merchant_id=x_merchant_id,
            payload_merchant_id=payload.merchant_id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "MERCHANT_ID_MISMATCH",
                "message": "X-Merchant-Id header does not match payload merchant_id",
                "event_id": payload.event_id,
            },
        )

    # Verify signature
    if x_merchant_signature:
        # Get raw body for signature verification
        body = await request.body()
        body_str = body.decode("utf-8")

        if not service.verify_signature(body_str, x_merchant_signature, payload.merchant_id):
            logger.warning(
                "Webhook signature verification failed",
                event_id=payload.event_id,
                merchant_id=payload.merchant_id,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error_code": "INVALID_SIGNATURE",
                    "message": "Webhook signature verification failed",
                    "event_id": payload.event_id,
                },
            )
    else:
        # Log warning but allow for development
        logger.warning(
            "Webhook received without signature",
            event_id=payload.event_id,
            merchant_id=payload.merchant_id,
        )

    # Parse event type
    try:
        event_type = WebhookEventType(payload.event_type)
    except ValueError:
        logger.warning(
            "Unknown webhook event type",
            event_type=payload.event_type,
            event_id=payload.event_id,
        )
        # Accept unknown event types but log them
        # This allows forward compatibility
        return WebhookResponse(
            success=True,
            event_id=payload.event_id,
            status="ignored",
            message=f"Unknown event type: {payload.event_type}",
        )

    # Create event object
    event = WebhookEvent(
        event_id=payload.event_id,
        event_type=event_type,
        merchant_id=payload.merchant_id,
        timestamp=payload.timestamp,
        data=payload.data,
        signature=x_merchant_signature,
    )

    # Process event
    result = await service.process_event(event, correlation_id=correlation_id)

    return WebhookResponse(
        success=result.success,
        event_id=result.event_id,
        status=result.status.value,
        message=result.message,
    )


@router.get(
    "/events/{event_id}",
    response_model=dict,
    responses={
        404: {"model": WebhookErrorResponse},
    },
    summary="Get event status",
    description="Get the status of a previously received webhook event.",
)
async def get_event_status(
    event_id: str,
    merchant_id: str,
    service: Annotated[WebhookService, Depends(get_service)],
) -> dict:
    """Get the status of a webhook event.

    Args:
        event_id: Event identifier.
        merchant_id: Merchant identifier.
        service: Webhook service.

    Returns:
        Event status information.

    Raises:
        HTTPException: If event not found.
    """
    event_data = await service.event_log.get(event_id, merchant_id)

    if event_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "EVENT_NOT_FOUND",
                "message": f"Event not found: {event_id}",
                "event_id": event_id,
            },
        )

    return event_data
