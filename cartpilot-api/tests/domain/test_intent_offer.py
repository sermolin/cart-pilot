"""Tests for Intent and Offer entities."""

from datetime import datetime, timedelta, timezone

import pytest

from app.domain import (
    Intent,
    IntentId,
    MerchantId,
    Money,
    Offer,
    OfferId,
)
from app.domain.entities import OfferItem


# ============================================================================
# Intent Tests
# ============================================================================


class TestIntent:
    """Tests for Intent entity."""

    def test_create_intent(self) -> None:
        """Should create intent with query."""
        intent = Intent.create(query="I need wireless headphones under $100")

        assert intent.query == "I need wireless headphones under $100"
        assert intent.session_id is None
        assert intent.offers_collected is False
        assert len(intent.offer_ids) == 0
        assert isinstance(intent.id, IntentId)

    def test_create_intent_with_session_id(self) -> None:
        """Should create intent with session ID."""
        intent = Intent.create(
            query="laptop for coding",
            session_id="session-123",
        )

        assert intent.session_id == "session-123"

    def test_create_intent_with_metadata(self) -> None:
        """Should create intent with metadata."""
        intent = Intent.create(
            query="gaming keyboard",
            metadata={"max_price": 15000, "category": "electronics"},
        )

        assert intent.metadata["max_price"] == 15000
        assert intent.metadata["category"] == "electronics"

    def test_add_offer_to_intent(self) -> None:
        """Should add offer ID to intent."""
        intent = Intent.create(query="test")
        offer_id = OfferId.generate()

        intent.add_offer(offer_id)

        assert offer_id in intent.offer_ids
        assert len(intent.offer_ids) == 1

    def test_add_duplicate_offer_ignored(self) -> None:
        """Should not add duplicate offer ID."""
        intent = Intent.create(query="test")
        offer_id = OfferId.generate()

        intent.add_offer(offer_id)
        intent.add_offer(offer_id)  # Duplicate

        assert len(intent.offer_ids) == 1

    def test_mark_offers_collected(self) -> None:
        """Should mark offers as collected."""
        intent = Intent.create(query="test")
        assert intent.offers_collected is False

        intent.mark_offers_collected(["merchant-a", "merchant-b"])

        assert intent.offers_collected is True

    def test_intent_records_created_event(self) -> None:
        """Should record IntentCreated event."""
        intent = Intent.create(query="test query")
        events = intent.collect_events()

        assert len(events) == 1
        assert events[0].event_type == "intent.created"
        assert events[0].intent_id == str(intent.id)
        assert events[0].query == "test query"


# ============================================================================
# OfferItem Tests
# ============================================================================


class TestOfferItem:
    """Tests for OfferItem."""

    def test_create_offer_item(self) -> None:
        """Should create offer item with required fields."""
        item = OfferItem(
            product_id="prod-123",
            title="Wireless Headphones",
            unit_price=Money(amount_cents=9999, currency="USD"),
            quantity_available=50,
        )

        assert item.product_id == "prod-123"
        assert item.title == "Wireless Headphones"
        assert item.unit_price.amount_cents == 9999
        assert item.quantity_available == 50

    def test_offer_item_optional_fields(self) -> None:
        """Should support optional fields."""
        item = OfferItem(
            product_id="prod-123",
            title="Test",
            unit_price=Money(amount_cents=1000),
            quantity_available=10,
            sku="SKU-001",
            description="A great product",
            brand="Acme",
            category_path="Electronics > Audio",
            image_url="https://example.com/image.jpg",
            rating=4.5,
            review_count=100,
        )

        assert item.sku == "SKU-001"
        assert item.description == "A great product"
        assert item.brand == "Acme"
        assert item.rating == 4.5


# ============================================================================
# Offer Tests
# ============================================================================


class TestOffer:
    """Tests for Offer entity."""

    def make_offer_item(
        self,
        product_id: str = "prod-1",
        title: str = "Test Product",
        price_cents: int = 5000,
    ) -> OfferItem:
        """Create a test offer item."""
        return OfferItem(
            product_id=product_id,
            title=title,
            unit_price=Money(amount_cents=price_cents, currency="USD"),
            quantity_available=10,
        )

    def test_create_offer(self) -> None:
        """Should create offer with items."""
        intent_id = IntentId.generate()
        items = [self.make_offer_item()]

        offer = Offer.create(
            intent_id=intent_id,
            merchant_id=MerchantId("merchant-a"),
            items=items,
        )

        assert offer.intent_id == intent_id
        assert str(offer.merchant_id) == "merchant-a"
        assert offer.item_count == 1
        assert isinstance(offer.id, OfferId)

    def test_offer_item_count(self) -> None:
        """Should return correct item count."""
        items = [
            self.make_offer_item("prod-1"),
            self.make_offer_item("prod-2"),
            self.make_offer_item("prod-3"),
        ]

        offer = Offer.create(
            intent_id=IntentId.generate(),
            merchant_id=MerchantId("merchant-a"),
            items=items,
        )

        assert offer.item_count == 3

    def test_offer_lowest_price(self) -> None:
        """Should return lowest price item."""
        items = [
            self.make_offer_item("prod-1", price_cents=9999),
            self.make_offer_item("prod-2", price_cents=2999),
            self.make_offer_item("prod-3", price_cents=5999),
        ]

        offer = Offer.create(
            intent_id=IntentId.generate(),
            merchant_id=MerchantId("merchant-a"),
            items=items,
        )

        assert offer.lowest_price is not None
        assert offer.lowest_price.amount_cents == 2999

    def test_offer_highest_price(self) -> None:
        """Should return highest price item."""
        items = [
            self.make_offer_item("prod-1", price_cents=9999),
            self.make_offer_item("prod-2", price_cents=2999),
            self.make_offer_item("prod-3", price_cents=5999),
        ]

        offer = Offer.create(
            intent_id=IntentId.generate(),
            merchant_id=MerchantId("merchant-a"),
            items=items,
        )

        assert offer.highest_price is not None
        assert offer.highest_price.amount_cents == 9999

    def test_offer_empty_prices(self) -> None:
        """Should return None for prices when no items."""
        offer = Offer.create(
            intent_id=IntentId.generate(),
            merchant_id=MerchantId("merchant-a"),
            items=[],
        )

        assert offer.lowest_price is None
        assert offer.highest_price is None

    def test_offer_expiration(self) -> None:
        """Should check expiration correctly."""
        # Non-expired offer
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        offer = Offer.create(
            intent_id=IntentId.generate(),
            merchant_id=MerchantId("merchant-a"),
            items=[self.make_offer_item()],
            expires_at=future,
        )
        assert offer.is_expired is False

        # Expired offer
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        expired_offer = Offer.create(
            intent_id=IntentId.generate(),
            merchant_id=MerchantId("merchant-a"),
            items=[self.make_offer_item()],
            expires_at=past,
        )
        assert expired_offer.is_expired is True

    def test_offer_no_expiration(self) -> None:
        """Should not be expired if no expiration set."""
        offer = Offer.create(
            intent_id=IntentId.generate(),
            merchant_id=MerchantId("merchant-a"),
            items=[self.make_offer_item()],
            expires_at=None,
        )

        assert offer.is_expired is False

    def test_get_item_by_product_id(self) -> None:
        """Should get item by product ID."""
        items = [
            self.make_offer_item("prod-1", "Product 1"),
            self.make_offer_item("prod-2", "Product 2"),
        ]

        offer = Offer.create(
            intent_id=IntentId.generate(),
            merchant_id=MerchantId("merchant-a"),
            items=items,
        )

        item = offer.get_item("prod-1")
        assert item is not None
        assert item.title == "Product 1"

        not_found = offer.get_item("prod-999")
        assert not_found is None

    def test_offer_with_metadata(self) -> None:
        """Should store metadata."""
        offer = Offer.create(
            intent_id=IntentId.generate(),
            merchant_id=MerchantId("merchant-a"),
            items=[self.make_offer_item()],
            metadata={"source": "search", "query": "headphones"},
        )

        assert offer.metadata["source"] == "search"
        assert offer.metadata["query"] == "headphones"
