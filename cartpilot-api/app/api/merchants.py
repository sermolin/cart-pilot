"""Merchant API endpoints.

Provides endpoints for discovering available merchants.
"""

from fastapi import APIRouter, status

from app.api.schemas import MerchantListResponse, MerchantSchema
from app.infrastructure.merchant_client import get_merchant_registry

router = APIRouter(prefix="/merchants", tags=["Merchants"])


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "",
    response_model=MerchantListResponse,
    status_code=status.HTTP_200_OK,
    summary="List merchants",
    description="Get a list of all enabled merchants.",
)
async def list_merchants() -> MerchantListResponse:
    """List all enabled merchants.

    Returns information about all merchants that are currently
    available for collecting offers.

    Returns:
        List of merchants.
    """
    registry = get_merchant_registry()
    merchants = registry.list_merchants()

    return MerchantListResponse(
        merchants=[
            MerchantSchema(
                id=m.id,
                name=m.display_name,
                url=m.url,
                enabled=m.enabled,
            )
            for m in merchants
        ],
        total=len(merchants),
    )
