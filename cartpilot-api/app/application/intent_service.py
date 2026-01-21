"""Intent and Offer application service.

Handles creation of purchase intents and collection of offers from merchants.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from app.domain.entities import Intent, Offer, OfferItem
from app.domain.value_objects import IntentId, MerchantId, Money, OfferId
from app.infrastructure.merchant_client import (
    MerchantClient,
    MerchantClientError,
    MerchantClientFactory,
    MerchantProduct,
    get_merchant_registry,
)

logger = structlog.get_logger()


# ============================================================================
# In-Memory Repositories (to be replaced with DB in later modules)
# ============================================================================


class IntentRepository:
    """In-memory repository for intents."""

    def __init__(self) -> None:
        self._intents: dict[str, Intent] = {}

    def save(self, intent: Intent) -> None:
        """Save an intent."""
        self._intents[str(intent.id)] = intent

    def get(self, intent_id: str) -> Intent | None:
        """Get intent by ID."""
        return self._intents.get(intent_id)

    def list_all(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[list[Intent], int]:
        """List intents with pagination."""
        all_intents = list(self._intents.values())
        all_intents.sort(key=lambda i: i.created_at, reverse=True)
        total = len(all_intents)
        start = (page - 1) * page_size
        end = start + page_size
        return all_intents[start:end], total


class OfferRepository:
    """In-memory repository for offers."""

    def __init__(self) -> None:
        self._offers: dict[str, Offer] = {}
        self._by_intent: dict[str, list[str]] = {}

    def save(self, offer: Offer) -> None:
        """Save an offer."""
        offer_id = str(offer.id)
        intent_id = str(offer.intent_id)

        self._offers[offer_id] = offer

        if intent_id not in self._by_intent:
            self._by_intent[intent_id] = []
        if offer_id not in self._by_intent[intent_id]:
            self._by_intent[intent_id].append(offer_id)

    def get(self, offer_id: str) -> Offer | None:
        """Get offer by ID."""
        return self._offers.get(offer_id)

    def get_by_intent(
        self, intent_id: str, page: int = 1, page_size: int = 20
    ) -> tuple[list[Offer], int]:
        """Get offers for an intent with pagination."""
        offer_ids = self._by_intent.get(intent_id, [])
        offers = [self._offers[oid] for oid in offer_ids if oid in self._offers]
        offers.sort(key=lambda o: o.created_at, reverse=True)

        total = len(offers)
        start = (page - 1) * page_size
        end = start + page_size
        return offers[start:end], total


# Global repository instances
_intent_repo: IntentRepository | None = None
_offer_repo: OfferRepository | None = None


def get_intent_repository() -> IntentRepository:
    """Get intent repository singleton."""
    global _intent_repo
    if _intent_repo is None:
        _intent_repo = IntentRepository()
    return _intent_repo


def get_offer_repository() -> OfferRepository:
    """Get offer repository singleton."""
    global _offer_repo
    if _offer_repo is None:
        _offer_repo = OfferRepository()
    return _offer_repo


# ============================================================================
# Service Result Types
# ============================================================================


@dataclass
class CreateIntentResult:
    """Result of creating an intent."""

    intent: Intent
    success: bool = True
    error: str | None = None


@dataclass
class CollectOffersResult:
    """Result of collecting offers for an intent."""

    intent: Intent
    offers: list[Offer] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    success: bool = True


@dataclass
class GetIntentResult:
    """Result of getting an intent."""

    intent: Intent | None = None
    offers: list[Offer] = field(default_factory=list)
    success: bool = True
    error: str | None = None


@dataclass
class GetOfferResult:
    """Result of getting an offer."""

    offer: Offer | None = None
    success: bool = True
    error: str | None = None


# ============================================================================
# Intent Service
# ============================================================================


class IntentService:
    """Application service for managing purchase intents and offers.

    Orchestrates the flow of:
    1. Creating purchase intents from user queries
    2. Collecting offers from multiple merchants
    3. Normalizing and storing offers
    """

    def __init__(
        self,
        intent_repo: IntentRepository | None = None,
        offer_repo: OfferRepository | None = None,
        request_id: str | None = None,
    ) -> None:
        """Initialize service.

        Args:
            intent_repo: Intent repository.
            offer_repo: Offer repository.
            request_id: Request ID for correlation.
        """
        self.intent_repo = intent_repo or get_intent_repository()
        self.offer_repo = offer_repo or get_offer_repository()
        self.request_id = request_id

    async def create_intent(
        self,
        query: str,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CreateIntentResult:
        """Create a new purchase intent.

        Args:
            query: Natural language search query.
            session_id: Optional session identifier.
            metadata: Optional metadata.

        Returns:
            CreateIntentResult with the created intent.
        """
        try:
            intent = Intent.create(
                query=query,
                session_id=session_id,
                metadata=metadata,
            )

            self.intent_repo.save(intent)

            logger.info(
                "Intent created",
                intent_id=str(intent.id),
                query=query,
                session_id=session_id,
                request_id=self.request_id,
            )

            return CreateIntentResult(intent=intent)

        except Exception as e:
            logger.error(
                "Failed to create intent",
                query=query,
                error=str(e),
                request_id=self.request_id,
            )
            return CreateIntentResult(
                intent=None,  # type: ignore
                success=False,
                error=str(e),
            )

    async def get_intent(self, intent_id: str) -> GetIntentResult:
        """Get an intent by ID.

        Args:
            intent_id: Intent identifier.

        Returns:
            GetIntentResult with intent and its offers.
        """
        intent = self.intent_repo.get(intent_id)
        if not intent:
            return GetIntentResult(
                success=False,
                error=f"Intent not found: {intent_id}",
            )

        offers, _ = self.offer_repo.get_by_intent(intent_id)
        return GetIntentResult(intent=intent, offers=offers)

    async def collect_offers(
        self,
        intent_id: str,
        merchant_ids: list[str] | None = None,
        limit_per_merchant: int = 10,
    ) -> CollectOffersResult:
        """Collect offers from merchants for an intent.

        Queries all enabled merchants (or specified ones) in parallel
        and normalizes the results into offers.

        Args:
            intent_id: Intent to collect offers for.
            merchant_ids: Optional list of specific merchants to query.
            limit_per_merchant: Max products per merchant.

        Returns:
            CollectOffersResult with collected offers.
        """
        intent = self.intent_repo.get(intent_id)
        if not intent:
            return CollectOffersResult(
                intent=None,  # type: ignore
                success=False,
                errors=[{"error": f"Intent not found: {intent_id}"}],
            )

        registry = get_merchant_registry()

        # Determine which merchants to query
        if merchant_ids:
            target_merchants = [
                m for m in registry.list_merchants() if m.id in merchant_ids
            ]
        else:
            target_merchants = registry.list_merchants()

        if not target_merchants:
            return CollectOffersResult(
                intent=intent,
                errors=[{"error": "No merchants available"}],
            )

        logger.info(
            "Collecting offers",
            intent_id=intent_id,
            query=intent.query,
            merchant_count=len(target_merchants),
            request_id=self.request_id,
        )

        # Query merchants in parallel
        async with MerchantClientFactory(request_id=self.request_id) as factory:
            tasks = []
            for merchant in target_merchants:
                client = factory.get_client(merchant.id)
                if client:
                    tasks.append(
                        self._collect_from_merchant(
                            client, intent, limit_per_merchant
                        )
                    )

            results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        offers: list[Offer] = []
        errors: list[dict[str, str]] = []
        collected_merchant_ids: list[str] = []

        for i, result in enumerate(results):
            merchant_id = target_merchants[i].id

            if isinstance(result, Exception):
                logger.warning(
                    "Failed to collect from merchant",
                    merchant_id=merchant_id,
                    error=str(result),
                    request_id=self.request_id,
                )
                errors.append({
                    "merchant_id": merchant_id,
                    "error": str(result),
                })
            elif isinstance(result, Offer):
                offers.append(result)
                collected_merchant_ids.append(merchant_id)

                # Save offer and link to intent
                self.offer_repo.save(result)
                intent.add_offer(result.id)

        # Mark intent as having collected offers
        intent.mark_offers_collected(collected_merchant_ids)
        self.intent_repo.save(intent)

        logger.info(
            "Offers collected",
            intent_id=intent_id,
            offer_count=len(offers),
            error_count=len(errors),
            request_id=self.request_id,
        )

        return CollectOffersResult(
            intent=intent,
            offers=offers,
            errors=errors,
            success=len(offers) > 0,
        )

    async def _collect_from_merchant(
        self,
        client: MerchantClient,
        intent: Intent,
        limit: int,
    ) -> Offer:
        """Collect products from a single merchant and create an offer.

        Args:
            client: Merchant client.
            intent: Purchase intent.
            limit: Maximum products to fetch.

        Returns:
            Offer with merchant products.

        Raises:
            MerchantClientError: On API error.
        """
        # Search products using intent query
        products = await client.search_products(intent.query, limit=limit)

        # Convert to offer items
        items = [self._product_to_offer_item(p) for p in products]

        # Create offer with 1 hour expiration
        offer = Offer.create(
            intent_id=intent.id,
            merchant_id=MerchantId(client.merchant.id),
            items=items,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            metadata={
                "merchant_name": client.merchant.display_name,
                "query": intent.query,
            },
        )

        logger.debug(
            "Collected from merchant",
            merchant_id=client.merchant.id,
            item_count=len(items),
            intent_id=str(intent.id),
        )

        return offer

    def _product_to_offer_item(self, product: MerchantProduct) -> OfferItem:
        """Convert merchant product to offer item.

        Args:
            product: Merchant product.

        Returns:
            Normalized offer item.
        """
        return OfferItem(
            product_id=product.id,
            title=product.title,
            unit_price=Money(
                amount_cents=product.price_cents,
                currency=product.currency,
            ),
            quantity_available=product.stock_quantity,
            sku=product.sku,
            description=product.description,
            brand=product.brand,
            category_path=product.category_path,
            image_url=product.image_url,
            rating=product.rating,
            review_count=product.review_count,
        )

    async def get_offer(self, offer_id: str) -> GetOfferResult:
        """Get an offer by ID.

        Args:
            offer_id: Offer identifier.

        Returns:
            GetOfferResult with the offer.
        """
        offer = self.offer_repo.get(offer_id)
        if not offer:
            return GetOfferResult(
                success=False,
                error=f"Offer not found: {offer_id}",
            )
        return GetOfferResult(offer=offer)

    async def list_offers_for_intent(
        self,
        intent_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Offer], int]:
        """List offers for an intent.

        Args:
            intent_id: Intent identifier.
            page: Page number.
            page_size: Items per page.

        Returns:
            Tuple of (offers, total_count).
        """
        return self.offer_repo.get_by_intent(intent_id, page, page_size)


# ============================================================================
# Service Factory
# ============================================================================


def get_intent_service(request_id: str | None = None) -> IntentService:
    """Get intent service instance.

    Args:
        request_id: Request ID for correlation.

    Returns:
        IntentService instance.
    """
    return IntentService(request_id=request_id)


# Re-export for use by checkout service
__all__ = [
    "IntentService",
    "IntentRepository",
    "OfferRepository",
    "CreateIntentResult",
    "CollectOffersResult",
    "GetIntentResult",
    "GetOfferResult",
    "get_intent_service",
    "get_intent_repository",
    "get_offer_repository",
]
