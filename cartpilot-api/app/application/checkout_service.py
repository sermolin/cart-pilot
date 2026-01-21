"""Checkout application service.

Orchestrates the checkout approval flow including:
- Creating checkouts from offers
- Getting quotes from merchants
- Requesting and granting approvals
- Confirming purchases with price change detection
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog

from app.domain.entities import Checkout, CheckoutItem, Offer
from app.domain.exceptions import (
    CheckoutExpiredError,
    CheckoutNotApprovedError,
    CheckoutNotFoundError,
    ReapprovalRequiredError,
)
from app.domain.state_machines import CheckoutStatus
from app.domain.value_objects import CheckoutId, FrozenReceipt, MerchantId, OfferId
from app.infrastructure.merchant_client import (
    MerchantClient,
    MerchantClientError,
    MerchantClientFactory,
    MerchantQuoteResponse,
    get_merchant_registry,
)

logger = structlog.get_logger()


# ============================================================================
# In-Memory Repository (to be replaced with DB in later modules)
# ============================================================================


class CheckoutRepository:
    """In-memory repository for checkouts."""

    def __init__(self) -> None:
        self._checkouts: dict[str, Checkout] = {}
        self._by_idempotency_key: dict[str, str] = {}

    def save(self, checkout: Checkout) -> None:
        """Save a checkout."""
        self._checkouts[str(checkout.id)] = checkout
        if checkout.idempotency_key:
            self._by_idempotency_key[checkout.idempotency_key] = str(checkout.id)

    def get(self, checkout_id: str) -> Checkout | None:
        """Get checkout by ID."""
        return self._checkouts.get(checkout_id)

    def get_by_idempotency_key(self, key: str) -> Checkout | None:
        """Get checkout by idempotency key."""
        checkout_id = self._by_idempotency_key.get(key)
        if checkout_id:
            return self._checkouts.get(checkout_id)
        return None

    def list_all(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[list[Checkout], int]:
        """List checkouts with pagination."""
        all_checkouts = list(self._checkouts.values())
        all_checkouts.sort(key=lambda c: c.created_at, reverse=True)
        total = len(all_checkouts)
        start = (page - 1) * page_size
        end = start + page_size
        return all_checkouts[start:end], total


# Global repository instance
_checkout_repo: CheckoutRepository | None = None


def get_checkout_repository() -> CheckoutRepository:
    """Get checkout repository singleton."""
    global _checkout_repo
    if _checkout_repo is None:
        _checkout_repo = CheckoutRepository()
    return _checkout_repo


# ============================================================================
# Service Result Types
# ============================================================================


@dataclass
class CreateCheckoutResult:
    """Result of creating a checkout."""

    checkout: Checkout | None = None
    success: bool = True
    error: str | None = None
    error_code: str | None = None


@dataclass
class QuoteCheckoutResult:
    """Result of getting a quote for a checkout."""

    checkout: Checkout | None = None
    success: bool = True
    error: str | None = None
    error_code: str | None = None
    reapproval_required: bool = False


@dataclass
class RequestApprovalResult:
    """Result of requesting approval."""

    checkout: Checkout | None = None
    frozen_receipt: FrozenReceipt | None = None
    success: bool = True
    error: str | None = None
    error_code: str | None = None


@dataclass
class ApproveCheckoutResult:
    """Result of approving a checkout."""

    checkout: Checkout | None = None
    success: bool = True
    error: str | None = None
    error_code: str | None = None


@dataclass
class ConfirmCheckoutResult:
    """Result of confirming a checkout."""

    checkout: Checkout | None = None
    merchant_order_id: str | None = None
    success: bool = True
    error: str | None = None
    error_code: str | None = None
    reapproval_required: bool = False


# ============================================================================
# Checkout Service
# ============================================================================


class CheckoutService:
    """Application service for managing checkout approval flow.

    Orchestrates the flow:
    1. Create checkout from offer
    2. Get quote from merchant
    3. Request approval (freeze receipt)
    4. Approve checkout
    5. Confirm checkout (execute purchase)
    """

    def __init__(
        self,
        checkout_repo: CheckoutRepository | None = None,
        offer_repo: Any | None = None,  # OfferRepository from intent_service
        request_id: str | None = None,
    ) -> None:
        """Initialize service.

        Args:
            checkout_repo: Checkout repository.
            offer_repo: Offer repository for looking up offers.
            request_id: Request ID for correlation.
        """
        self.checkout_repo = checkout_repo or get_checkout_repository()
        self.offer_repo = offer_repo
        self.request_id = request_id

    async def create_checkout(
        self,
        offer_id: str,
        items: list[dict[str, Any]],
        idempotency_key: str | None = None,
    ) -> CreateCheckoutResult:
        """Create a checkout from an offer.

        Args:
            offer_id: Offer to create checkout from.
            items: Items with product_id, variant_id, quantity.
            idempotency_key: Optional idempotency key.

        Returns:
            CreateCheckoutResult with the created checkout.
        """
        try:
            # Check idempotency
            if idempotency_key:
                existing = self.checkout_repo.get_by_idempotency_key(idempotency_key)
                if existing:
                    logger.info(
                        "Returning existing checkout for idempotency key",
                        idempotency_key=idempotency_key,
                        checkout_id=str(existing.id),
                    )
                    return CreateCheckoutResult(checkout=existing)

            # Get offer to determine merchant
            if self.offer_repo:
                offer = self.offer_repo.get(offer_id)
                if not offer:
                    return CreateCheckoutResult(
                        success=False,
                        error=f"Offer not found: {offer_id}",
                        error_code="OFFER_NOT_FOUND",
                    )
                merchant_id = offer.merchant_id
            else:
                # Fallback - try to parse merchant from items or use default
                # In production, always require offer lookup
                merchant_id = MerchantId("merchant-a")

            checkout = Checkout.create(
                offer_id=OfferId.from_string(offer_id),
                merchant_id=merchant_id,
                idempotency_key=idempotency_key,
            )

            self.checkout_repo.save(checkout)

            logger.info(
                "Checkout created",
                checkout_id=str(checkout.id),
                offer_id=offer_id,
                merchant_id=str(merchant_id),
                request_id=self.request_id,
            )

            return CreateCheckoutResult(checkout=checkout)

        except Exception as e:
            logger.error(
                "Failed to create checkout",
                offer_id=offer_id,
                error=str(e),
                request_id=self.request_id,
            )
            return CreateCheckoutResult(
                success=False,
                error=str(e),
                error_code="CREATE_FAILED",
            )

    async def get_quote(
        self,
        checkout_id: str,
        items: list[dict[str, Any]],
        customer_email: str | None = None,
    ) -> QuoteCheckoutResult:
        """Get a quote from the merchant for the checkout.

        Args:
            checkout_id: Checkout to quote.
            items: Items with product_id, variant_id, quantity.
            customer_email: Optional customer email.

        Returns:
            QuoteCheckoutResult with updated checkout.
        """
        try:
            checkout = self.checkout_repo.get(checkout_id)
            if not checkout:
                return QuoteCheckoutResult(
                    success=False,
                    error=f"Checkout not found: {checkout_id}",
                    error_code="CHECKOUT_NOT_FOUND",
                )

            # Check if quote is allowed in current state
            if not checkout.status.is_quotable() and not checkout.status.requires_reapproval():
                return QuoteCheckoutResult(
                    success=False,
                    error=f"Cannot quote checkout in state: {checkout.status.value}",
                    error_code="INVALID_STATE",
                )

            # Get quote from merchant
            async with MerchantClientFactory(request_id=self.request_id) as factory:
                client = factory.get_client(str(checkout.merchant_id))
                if not client:
                    return QuoteCheckoutResult(
                        success=False,
                        error=f"Merchant not found: {checkout.merchant_id}",
                        error_code="MERCHANT_NOT_FOUND",
                    )

                quote = await client.create_quote(
                    items=items,
                    customer_email=customer_email,
                )

            # Convert quote items to checkout items
            checkout_items = [
                CheckoutItem(
                    product_id=qi.product_id,
                    variant_id=qi.variant_id,
                    sku=qi.sku,
                    title=qi.title,
                    unit_price_cents=qi.unit_price_cents,
                    quantity=qi.quantity,
                    currency=qi.currency,
                )
                for qi in quote.items
            ]

            # Check if this will trigger re-approval
            reapproval_triggered = (
                checkout.status.requires_reapproval()
                and checkout.frozen_receipt
                and not checkout.frozen_receipt.matches_total(quote.total_cents)
            )

            # Set quote on checkout
            checkout.set_quote(
                items=checkout_items,
                subtotal_cents=quote.subtotal_cents,
                tax_cents=quote.tax_cents,
                shipping_cents=quote.shipping_cents,
                total_cents=quote.total_cents,
                currency=quote.currency,
                merchant_checkout_id=quote.checkout_id,
                receipt_hash=quote.receipt_hash or "",
            )

            self.checkout_repo.save(checkout)

            logger.info(
                "Quote received",
                checkout_id=checkout_id,
                merchant_checkout_id=quote.checkout_id,
                total_cents=quote.total_cents,
                reapproval_required=reapproval_triggered,
                request_id=self.request_id,
            )

            return QuoteCheckoutResult(
                checkout=checkout,
                reapproval_required=reapproval_triggered,
            )

        except MerchantClientError as e:
            logger.error(
                "Merchant quote failed",
                checkout_id=checkout_id,
                error=str(e),
                request_id=self.request_id,
            )
            return QuoteCheckoutResult(
                success=False,
                error=str(e),
                error_code="MERCHANT_ERROR",
            )
        except Exception as e:
            logger.error(
                "Failed to get quote",
                checkout_id=checkout_id,
                error=str(e),
                request_id=self.request_id,
            )
            return QuoteCheckoutResult(
                success=False,
                error=str(e),
                error_code="QUOTE_FAILED",
            )

    async def request_approval(
        self,
        checkout_id: str,
    ) -> RequestApprovalResult:
        """Request approval for a checkout.

        Freezes the current receipt for price change detection.

        Args:
            checkout_id: Checkout to request approval for.

        Returns:
            RequestApprovalResult with frozen receipt.
        """
        try:
            checkout = self.checkout_repo.get(checkout_id)
            if not checkout:
                return RequestApprovalResult(
                    success=False,
                    error=f"Checkout not found: {checkout_id}",
                    error_code="CHECKOUT_NOT_FOUND",
                )

            frozen_receipt = checkout.request_approval()
            self.checkout_repo.save(checkout)

            logger.info(
                "Approval requested",
                checkout_id=checkout_id,
                frozen_receipt_hash=frozen_receipt.hash,
                total_cents=checkout.total_cents,
                request_id=self.request_id,
            )

            return RequestApprovalResult(
                checkout=checkout,
                frozen_receipt=frozen_receipt,
            )

        except CheckoutExpiredError as e:
            return RequestApprovalResult(
                success=False,
                error=str(e),
                error_code="CHECKOUT_EXPIRED",
            )
        except Exception as e:
            logger.error(
                "Failed to request approval",
                checkout_id=checkout_id,
                error=str(e),
                request_id=self.request_id,
            )
            return RequestApprovalResult(
                success=False,
                error=str(e),
                error_code="APPROVAL_REQUEST_FAILED",
            )

    async def approve(
        self,
        checkout_id: str,
        approved_by: str,
    ) -> ApproveCheckoutResult:
        """Approve a checkout.

        Args:
            checkout_id: Checkout to approve.
            approved_by: Identifier of who is approving.

        Returns:
            ApproveCheckoutResult with approved checkout.
        """
        try:
            checkout = self.checkout_repo.get(checkout_id)
            if not checkout:
                return ApproveCheckoutResult(
                    success=False,
                    error=f"Checkout not found: {checkout_id}",
                    error_code="CHECKOUT_NOT_FOUND",
                )

            checkout.approve(approved_by=approved_by)
            self.checkout_repo.save(checkout)

            logger.info(
                "Checkout approved",
                checkout_id=checkout_id,
                approved_by=approved_by,
                request_id=self.request_id,
            )

            return ApproveCheckoutResult(checkout=checkout)

        except CheckoutExpiredError as e:
            return ApproveCheckoutResult(
                success=False,
                error=str(e),
                error_code="CHECKOUT_EXPIRED",
            )
        except ReapprovalRequiredError as e:
            return ApproveCheckoutResult(
                success=False,
                error=str(e),
                error_code="REAPPROVAL_REQUIRED",
            )
        except Exception as e:
            logger.error(
                "Failed to approve checkout",
                checkout_id=checkout_id,
                error=str(e),
                request_id=self.request_id,
            )
            return ApproveCheckoutResult(
                success=False,
                error=str(e),
                error_code="APPROVAL_FAILED",
            )

    async def confirm(
        self,
        checkout_id: str,
        payment_method: str = "test_card",
        idempotency_key: str | None = None,
    ) -> ConfirmCheckoutResult:
        """Confirm a checkout (execute purchase).

        Args:
            checkout_id: Checkout to confirm.
            payment_method: Payment method identifier.
            idempotency_key: Idempotency key.

        Returns:
            ConfirmCheckoutResult with merchant order ID.
        """
        try:
            checkout = self.checkout_repo.get(checkout_id)
            if not checkout:
                return ConfirmCheckoutResult(
                    success=False,
                    error=f"Checkout not found: {checkout_id}",
                    error_code="CHECKOUT_NOT_FOUND",
                )

            # Check if already confirmed (idempotent)
            if checkout.status == CheckoutStatus.CONFIRMED:
                return ConfirmCheckoutResult(
                    checkout=checkout,
                    merchant_order_id=checkout.merchant_order_id,
                )

            # Check if approved
            if checkout.status != CheckoutStatus.APPROVED:
                return ConfirmCheckoutResult(
                    success=False,
                    error=f"Checkout must be approved before confirmation (current: {checkout.status.value})",
                    error_code="NOT_APPROVED",
                )

            # Check for price changes before confirming with merchant
            if checkout.requires_reapproval:
                return ConfirmCheckoutResult(
                    success=False,
                    error="Price has changed, re-approval required",
                    error_code="REAPPROVAL_REQUIRED",
                    reapproval_required=True,
                )

            # Confirm with merchant
            async with MerchantClientFactory(request_id=self.request_id) as factory:
                client = factory.get_client(str(checkout.merchant_id))
                if not client:
                    return ConfirmCheckoutResult(
                        success=False,
                        error=f"Merchant not found: {checkout.merchant_id}",
                        error_code="MERCHANT_NOT_FOUND",
                    )

                if not checkout.merchant_checkout_id:
                    return ConfirmCheckoutResult(
                        success=False,
                        error="No merchant checkout ID - quote required first",
                        error_code="QUOTE_REQUIRED",
                    )

                confirm_response = await client.confirm_checkout(
                    checkout_id=checkout.merchant_checkout_id,
                    payment_method=payment_method,
                    idempotency_key=idempotency_key,
                )

            # Update checkout with confirmation
            checkout.confirm(merchant_order_id=confirm_response.merchant_order_id)
            self.checkout_repo.save(checkout)

            logger.info(
                "Checkout confirmed",
                checkout_id=checkout_id,
                merchant_order_id=confirm_response.merchant_order_id,
                total_cents=checkout.total_cents,
                request_id=self.request_id,
            )

            return ConfirmCheckoutResult(
                checkout=checkout,
                merchant_order_id=confirm_response.merchant_order_id,
            )

        except MerchantClientError as e:
            # Handle price changed from merchant
            if e.status_code == 409 and "PRICE_CHANGED" in str(e):
                return ConfirmCheckoutResult(
                    success=False,
                    error=str(e),
                    error_code="REAPPROVAL_REQUIRED",
                    reapproval_required=True,
                )
            logger.error(
                "Merchant confirm failed",
                checkout_id=checkout_id,
                error=str(e),
                request_id=self.request_id,
            )
            return ConfirmCheckoutResult(
                success=False,
                error=str(e),
                error_code="MERCHANT_ERROR",
            )
        except CheckoutExpiredError as e:
            return ConfirmCheckoutResult(
                success=False,
                error=str(e),
                error_code="CHECKOUT_EXPIRED",
            )
        except ReapprovalRequiredError as e:
            return ConfirmCheckoutResult(
                success=False,
                error=str(e),
                error_code="REAPPROVAL_REQUIRED",
                reapproval_required=True,
            )
        except Exception as e:
            logger.error(
                "Failed to confirm checkout",
                checkout_id=checkout_id,
                error=str(e),
                request_id=self.request_id,
            )
            return ConfirmCheckoutResult(
                success=False,
                error=str(e),
                error_code="CONFIRM_FAILED",
            )

    async def get_checkout(self, checkout_id: str) -> Checkout | None:
        """Get a checkout by ID.

        Args:
            checkout_id: Checkout identifier.

        Returns:
            Checkout if found, None otherwise.
        """
        return self.checkout_repo.get(checkout_id)


# ============================================================================
# Service Factory
# ============================================================================


def get_checkout_service(
    request_id: str | None = None,
    offer_repo: Any | None = None,
) -> CheckoutService:
    """Get checkout service instance.

    Args:
        request_id: Request ID for correlation.
        offer_repo: Offer repository for looking up offers.

    Returns:
        CheckoutService instance.
    """
    return CheckoutService(request_id=request_id, offer_repo=offer_repo)
