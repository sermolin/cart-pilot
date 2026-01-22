"""Checkout session management for Merchant B (Chaos Mode).

Handles quote creation, checkout confirmation, and session lifecycle
with chaos mode behaviors: price changes and out-of-stock scenarios.
"""

import hashlib
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Callable

from app.products import ProductStore, get_product_store
from app.schemas import (
    ChaosScenario,
    CheckoutItemRequest,
    CheckoutItemSchema,
    CheckoutSchema,
    CheckoutStatus,
    ConfirmResponse,
    Currency,
    PriceSchema,
)

if TYPE_CHECKING:
    from app.chaos import ChaosController


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
    unit_price: int  # in cents - price at quote time
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
    # Chaos tracking
    original_prices: dict[str, int] = field(default_factory=dict)  # product_id -> price
    chaos_triggered: list[str] = field(default_factory=list)


# ============================================================================
# Checkout Store
# ============================================================================


class CheckoutStore:
    """In-memory checkout session store with chaos mode support.

    Manages checkout sessions with support for chaos scenarios:
    - Price changes between quote and confirm
    - Items going out of stock
    """

    TAX_RATE = 0.08  # 8% tax
    SHIPPING_FLAT = 999  # $9.99 flat shipping
    FREE_SHIPPING_THRESHOLD = 5000  # Free shipping over $50
    CHECKOUT_TTL_HOURS = 24

    def __init__(
        self,
        product_store: ProductStore | None = None,
        chaos_controller: "ChaosController | None" = None,
    ) -> None:
        """Initialize checkout store.

        Args:
            product_store: Product store instance.
            chaos_controller: Chaos controller for triggering scenarios.
        """
        self.product_store = product_store or get_product_store()
        self.chaos_controller = chaos_controller
        self._sessions: dict[str, CheckoutSession] = {}
        self._idempotency_cache: dict[str, str] = {}  # key -> checkout_id

    def set_chaos_controller(self, controller: "ChaosController") -> None:
        """Set the chaos controller.

        Args:
            controller: Chaos controller instance.
        """
        self.chaos_controller = controller

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
        original_prices: dict[str, int] = {}

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

            # Store original price for chaos detection
            original_prices[item_req.product_id] = unit_price

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
            original_prices=original_prices,
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

    def _check_for_price_changes(self, session: CheckoutSession) -> list[dict]:
        """Check if any prices have changed since quote.

        Args:
            session: Checkout session.

        Returns:
            List of price change details.
        """
        changes = []

        for item in session.items:
            current_price = self.product_store.get_effective_price(
                item.product_id, item.variant_id
            )
            if current_price is None:
                continue

            quoted_price = item.unit_price
            if current_price != quoted_price:
                changes.append(
                    {
                        "product_id": item.product_id,
                        "variant_id": item.variant_id,
                        "quoted_price": quoted_price,
                        "current_price": current_price,
                        "difference": current_price - quoted_price,
                    }
                )

        return changes

    def _check_for_stock_issues(self, session: CheckoutSession) -> list[dict]:
        """Check if any items are now out of stock.

        Args:
            session: Checkout session.

        Returns:
            List of stock issue details.
        """
        issues = []

        for item in session.items:
            if not self.product_store.check_stock(
                item.product_id, item.variant_id, item.quantity
            ):
                issues.append(
                    {
                        "product_id": item.product_id,
                        "variant_id": item.variant_id,
                        "requested_quantity": item.quantity,
                    }
                )

        return issues

    def confirm_checkout(
        self,
        checkout_id: str,
        payment_method: str = "test_card",
        idempotency_key: str | None = None,
    ) -> CheckoutSession:
        """Confirm a checkout session.

        This is where chaos mode triggers:
        - Price changes are detected and cause failure
        - Out-of-stock items cause failure

        Args:
            checkout_id: Checkout ID.
            payment_method: Payment method identifier.
            idempotency_key: Idempotency key.

        Returns:
            Updated checkout session.

        Raises:
            ValueError: If checkout not found, expired, or chaos triggered.
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

        # CHAOS MODE: Trigger scenarios before confirmation
        if self.chaos_controller:
            self._trigger_chaos_before_confirm(session)

        # Check for stock issues (chaos may have triggered out-of-stock)
        stock_issues = self._check_for_stock_issues(session)
        if stock_issues:
            session.status = CheckoutStatus.FAILED
            session.failure_reason = "OUT_OF_STOCK"
            session.updated_at = datetime.now(timezone.utc)
            session.chaos_triggered.append("out_of_stock")
            products = ", ".join(i["product_id"][:8] for i in stock_issues)
            raise ValueError(f"Items out of stock: {products}")

        # Check for price changes (chaos may have triggered price change)
        price_changes = self._check_for_price_changes(session)
        if price_changes:
            session.status = CheckoutStatus.FAILED
            session.failure_reason = "PRICE_CHANGED"
            session.updated_at = datetime.now(timezone.utc)
            session.chaos_triggered.append("price_change")
            # Build detailed error message
            details = []
            for change in price_changes:
                old_price = change["quoted_price"] / 100
                new_price = change["current_price"] / 100
                details.append(f"${old_price:.2f} -> ${new_price:.2f}")
            raise ValueError(f"Price changed: {', '.join(details)}, re-quote required")

        # Verify receipt hash
        current_hash = self._calculate_receipt_hash(session)
        if current_hash != session.receipt_hash:
            session.status = CheckoutStatus.FAILED
            session.failure_reason = "RECEIPT_MISMATCH"
            session.updated_at = datetime.now(timezone.utc)
            raise ValueError("Receipt mismatch, re-quote required")

        # Success - confirm checkout
        session.status = CheckoutStatus.CONFIRMED
        session.merchant_order_id = self._generate_order_id()
        session.updated_at = datetime.now(timezone.utc)

        return session

    def _trigger_chaos_before_confirm(self, session: CheckoutSession) -> None:
        """Trigger chaos scenarios before confirmation.

        Args:
            session: Checkout session to potentially disrupt.
        """
        if not self.chaos_controller:
            return

        # Check each item for potential chaos
        for item in session.items:
            # Price change chaos
            if self.chaos_controller.should_trigger(ChaosScenario.PRICE_CHANGE):
                result = self.product_store.trigger_price_change(
                    item.product_id, increase=True
                )
                if result:
                    old_price, new_price = result
                    self.chaos_controller.log_event(
                        ChaosScenario.PRICE_CHANGE,
                        session.id,
                        {
                            "product_id": item.product_id,
                            "old_price": old_price,
                            "new_price": new_price,
                        },
                    )

            # Out of stock chaos
            if self.chaos_controller.should_trigger(ChaosScenario.OUT_OF_STOCK):
                success = self.product_store.trigger_out_of_stock(
                    item.product_id, item.variant_id
                )
                if success:
                    self.chaos_controller.log_event(
                        ChaosScenario.OUT_OF_STOCK,
                        session.id,
                        {
                            "product_id": item.product_id,
                            "variant_id": item.variant_id,
                        },
                    )

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

    def reset_all(self) -> None:
        """Reset all checkout sessions (for testing)."""
        self._sessions.clear()
        self._idempotency_cache.clear()


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


def reset_checkout_store() -> None:
    """Reset checkout store instance (for testing)."""
    global _checkout_store
    _checkout_store = None
