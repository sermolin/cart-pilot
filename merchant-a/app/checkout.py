"""Checkout session management for Merchant A.

Handles quote creation, checkout confirmation, and session lifecycle.
"""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from app.products import ProductStore, get_product_store
from app.schemas import (
    CheckoutItemRequest,
    CheckoutItemSchema,
    CheckoutSchema,
    CheckoutStatus,
    ConfirmResponse,
    Currency,
    PriceSchema,
)


# ============================================================================
# Checkout Session
# ============================================================================


@dataclass
class CheckoutItem:
    """Internal checkout item representation."""

    product_id: str
    variant_id: str | None
    sku: str
    title: str
    unit_price: int  # in cents
    quantity: int
    currency: str = "USD"

    @property
    def line_total(self) -> int:
        """Calculate line total in cents."""
        return self.unit_price * self.quantity


@dataclass
class CheckoutSession:
    """Internal checkout session representation."""

    id: str
    status: CheckoutStatus
    items: list[CheckoutItem]
    subtotal: int  # in cents
    tax: int  # in cents
    shipping: int  # in cents
    total: int  # in cents
    currency: str
    customer_email: str | None
    receipt_hash: str | None
    merchant_order_id: str | None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None
    failure_reason: str | None = None
    idempotency_key: str | None = None


# ============================================================================
# Checkout Store
# ============================================================================


class CheckoutStore:
    """In-memory checkout session store.

    Manages checkout sessions for happy-path scenarios with stable
    pricing and high availability.
    """

    TAX_RATE = 0.08  # 8% tax
    SHIPPING_FLAT = 999  # $9.99 flat shipping
    FREE_SHIPPING_THRESHOLD = 5000  # Free shipping over $50
    CHECKOUT_TTL_HOURS = 24

    def __init__(self, product_store: ProductStore | None = None) -> None:
        """Initialize checkout store.

        Args:
            product_store: Product store instance.
        """
        self.product_store = product_store or get_product_store()
        self._sessions: dict[str, CheckoutSession] = {}
        self._idempotency_cache: dict[str, str] = {}  # key -> checkout_id

    def _generate_checkout_id(self) -> str:
        """Generate unique checkout ID."""
        return str(uuid.uuid4())

    def _generate_order_id(self) -> str:
        """Generate merchant order ID."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        random_part = uuid.uuid4().hex[:8].upper()
        return f"ORD-{timestamp}-{random_part}"

    def _calculate_receipt_hash(self, session: CheckoutSession) -> str:
        """Calculate receipt hash for price verification.

        Args:
            session: Checkout session.

        Returns:
            Hash of receipt data.
        """
        data = "|".join(
            [
                session.id,
                str(session.total),
                session.currency,
                ",".join(
                    f"{item.product_id}:{item.variant_id or ''}:{item.quantity}:{item.unit_price}"
                    for item in session.items
                ),
            ]
        )
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def create_quote(
        self,
        items: list[CheckoutItemRequest],
        customer_email: str | None = None,
        idempotency_key: str | None = None,
    ) -> CheckoutSession:
        """Create a quote for items.

        Args:
            items: Items to quote.
            customer_email: Customer email.
            idempotency_key: Idempotency key.

        Returns:
            Created checkout session.

        Raises:
            ValueError: If product not found or insufficient stock.
        """
        # Check idempotency
        if idempotency_key and idempotency_key in self._idempotency_cache:
            existing_id = self._idempotency_cache[idempotency_key]
            existing = self._sessions.get(existing_id)
            if existing:
                return existing

        # Build checkout items
        checkout_items: list[CheckoutItem] = []

        for item_req in items:
            product = self.product_store.get_product(item_req.product_id)
            if not product:
                raise ValueError(f"Product not found: {item_req.product_id}")

            # Check stock
            if not self.product_store.check_stock(
                item_req.product_id, item_req.variant_id, item_req.quantity
            ):
                raise ValueError(
                    f"Insufficient stock for product: {item_req.product_id}"
                )

            # Get effective price
            unit_price = self.product_store.get_effective_price(
                item_req.product_id, item_req.variant_id
            )
            if unit_price is None:
                raise ValueError(f"Could not determine price for: {item_req.product_id}")

            # Get SKU
            sku = product.sku
            if item_req.variant_id:
                variant = self.product_store.get_variant(item_req.variant_id)
                if variant:
                    sku = f"{product.sku}{variant['sku_suffix']}"

            checkout_items.append(
                CheckoutItem(
                    product_id=item_req.product_id,
                    variant_id=item_req.variant_id,
                    sku=sku,
                    title=product.title,
                    unit_price=unit_price,
                    quantity=item_req.quantity,
                    currency=product.price.currency.value,
                )
            )

        # Calculate totals
        subtotal = sum(item.line_total for item in checkout_items)
        tax = int(subtotal * self.TAX_RATE)
        shipping = 0 if subtotal >= self.FREE_SHIPPING_THRESHOLD else self.SHIPPING_FLAT
        total = subtotal + tax + shipping

        # Create session
        now = datetime.now(timezone.utc)
        session = CheckoutSession(
            id=self._generate_checkout_id(),
            status=CheckoutStatus.QUOTED,
            items=checkout_items,
            subtotal=subtotal,
            tax=tax,
            shipping=shipping,
            total=total,
            currency="USD",
            customer_email=customer_email,
            receipt_hash=None,
            merchant_order_id=None,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(hours=self.CHECKOUT_TTL_HOURS),
            idempotency_key=idempotency_key,
        )

        # Calculate receipt hash
        session.receipt_hash = self._calculate_receipt_hash(session)

        # Store session
        self._sessions[session.id] = session

        # Cache idempotency key
        if idempotency_key:
            self._idempotency_cache[idempotency_key] = session.id

        return session

    def get_checkout(self, checkout_id: str) -> CheckoutSession | None:
        """Get checkout session by ID.

        Args:
            checkout_id: Checkout ID.

        Returns:
            Checkout session or None.
        """
        session = self._sessions.get(checkout_id)
        if session:
            # Check expiration
            if session.expires_at and datetime.now(timezone.utc) > session.expires_at:
                session.status = CheckoutStatus.EXPIRED
                session.updated_at = datetime.now(timezone.utc)
        return session

    def confirm_checkout(
        self,
        checkout_id: str,
        payment_method: str = "test_card",
        idempotency_key: str | None = None,
    ) -> CheckoutSession:
        """Confirm a checkout session.

        Args:
            checkout_id: Checkout ID.
            payment_method: Payment method identifier.
            idempotency_key: Idempotency key.

        Returns:
            Updated checkout session.

        Raises:
            ValueError: If checkout not found or not in valid state.
        """
        session = self.get_checkout(checkout_id)
        if not session:
            raise ValueError(f"Checkout not found: {checkout_id}")

        # Check if already confirmed (idempotent)
        if session.status == CheckoutStatus.CONFIRMED:
            return session

        # Validate state
        if session.status != CheckoutStatus.QUOTED:
            raise ValueError(
                f"Cannot confirm checkout in state: {session.status.value}"
            )

        # Check expiration
        if session.expires_at and datetime.now(timezone.utc) > session.expires_at:
            session.status = CheckoutStatus.EXPIRED
            session.updated_at = datetime.now(timezone.utc)
            raise ValueError("Checkout has expired")

        # Verify prices haven't changed (happy path - they won't)
        current_hash = self._calculate_receipt_hash(session)
        if current_hash != session.receipt_hash:
            session.status = CheckoutStatus.FAILED
            session.failure_reason = "PRICE_CHANGED"
            session.updated_at = datetime.now(timezone.utc)
            raise ValueError("Price has changed, re-quote required")

        # Simulate payment success (happy path)
        session.status = CheckoutStatus.CONFIRMED
        session.merchant_order_id = self._generate_order_id()
        session.updated_at = datetime.now(timezone.utc)

        return session

    def fail_checkout(self, checkout_id: str, reason: str) -> CheckoutSession:
        """Mark checkout as failed.

        Args:
            checkout_id: Checkout ID.
            reason: Failure reason.

        Returns:
            Updated checkout session.

        Raises:
            ValueError: If checkout not found.
        """
        session = self._sessions.get(checkout_id)
        if not session:
            raise ValueError(f"Checkout not found: {checkout_id}")

        session.status = CheckoutStatus.FAILED
        session.failure_reason = reason
        session.updated_at = datetime.now(timezone.utc)

        return session

    def to_schema(self, session: CheckoutSession) -> CheckoutSchema:
        """Convert internal session to schema.

        Args:
            session: Internal checkout session.

        Returns:
            Checkout schema.
        """
        return CheckoutSchema(
            id=session.id,
            status=session.status,
            items=[
                CheckoutItemSchema(
                    product_id=item.product_id,
                    variant_id=item.variant_id,
                    sku=item.sku,
                    title=item.title,
                    unit_price=PriceSchema(
                        amount=item.unit_price, currency=Currency(item.currency)
                    ),
                    quantity=item.quantity,
                    line_total=PriceSchema(
                        amount=item.line_total, currency=Currency(item.currency)
                    ),
                )
                for item in session.items
            ],
            subtotal=PriceSchema(amount=session.subtotal, currency=Currency.USD),
            tax=PriceSchema(amount=session.tax, currency=Currency.USD),
            shipping=PriceSchema(amount=session.shipping, currency=Currency.USD),
            total=PriceSchema(amount=session.total, currency=Currency.USD),
            customer_email=session.customer_email,
            receipt_hash=session.receipt_hash,
            merchant_order_id=session.merchant_order_id,
            created_at=session.created_at,
            updated_at=session.updated_at,
            expires_at=session.expires_at,
            failure_reason=session.failure_reason,
        )


# Global checkout store instance
_checkout_store: CheckoutStore | None = None


def get_checkout_store() -> CheckoutStore:
    """Get or create checkout store instance.

    Returns:
        CheckoutStore instance.
    """
    global _checkout_store
    if _checkout_store is None:
        _checkout_store = CheckoutStore()
    return _checkout_store
