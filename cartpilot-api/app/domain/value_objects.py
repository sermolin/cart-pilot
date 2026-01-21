"""Value Objects for the domain layer.

Value objects are immutable objects that are defined by their attributes
rather than identity. They are interchangeable when their values are equal.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Self
from uuid import UUID, uuid4

from app.domain.base import ValueObject
from app.domain.exceptions import CurrencyMismatchError, NegativeMoneyError


# ============================================================================
# Typed Identifiers
# ============================================================================


@dataclass(frozen=True)
class CartId(ValueObject):
    """Strongly-typed cart identifier.

    Using typed IDs prevents accidentally mixing up different entity IDs
    and provides compile-time safety.
    """

    value: UUID

    @classmethod
    def generate(cls) -> Self:
        """Generate a new cart ID.

        Returns:
            New CartId with random UUID.
        """
        return cls(value=uuid4())

    @classmethod
    def from_string(cls, value: str) -> Self:
        """Create CartId from string representation.

        Args:
            value: String UUID representation.

        Returns:
            CartId instance.
        """
        return cls(value=UUID(value))

    def __str__(self) -> str:
        """Return string representation.

        Returns:
            UUID as string.
        """
        return str(self.value)


@dataclass(frozen=True)
class CartItemId(ValueObject):
    """Strongly-typed cart item identifier."""

    value: UUID

    @classmethod
    def generate(cls) -> Self:
        """Generate a new cart item ID.

        Returns:
            New CartItemId with random UUID.
        """
        return cls(value=uuid4())

    @classmethod
    def from_string(cls, value: str) -> Self:
        """Create CartItemId from string representation.

        Args:
            value: String UUID representation.

        Returns:
            CartItemId instance.
        """
        return cls(value=UUID(value))

    def __str__(self) -> str:
        """Return string representation.

        Returns:
            UUID as string.
        """
        return str(self.value)


@dataclass(frozen=True)
class OrderId(ValueObject):
    """Strongly-typed order identifier."""

    value: UUID

    @classmethod
    def generate(cls) -> Self:
        """Generate a new order ID.

        Returns:
            New OrderId with random UUID.
        """
        return cls(value=uuid4())

    @classmethod
    def from_string(cls, value: str) -> Self:
        """Create OrderId from string representation.

        Args:
            value: String UUID representation.

        Returns:
            OrderId instance.
        """
        return cls(value=UUID(value))

    def __str__(self) -> str:
        """Return string representation.

        Returns:
            UUID as string.
        """
        return str(self.value)


@dataclass(frozen=True)
class ApprovalId(ValueObject):
    """Strongly-typed approval identifier."""

    value: UUID

    @classmethod
    def generate(cls) -> Self:
        """Generate a new approval ID.

        Returns:
            New ApprovalId with random UUID.
        """
        return cls(value=uuid4())

    @classmethod
    def from_string(cls, value: str) -> Self:
        """Create ApprovalId from string representation.

        Args:
            value: String UUID representation.

        Returns:
            ApprovalId instance.
        """
        return cls(value=UUID(value))

    def __str__(self) -> str:
        """Return string representation.

        Returns:
            UUID as string.
        """
        return str(self.value)


@dataclass(frozen=True)
class IntentId(ValueObject):
    """Strongly-typed intent identifier.

    Intents represent a user's purchase intention from a text query.
    """

    value: UUID

    @classmethod
    def generate(cls) -> Self:
        """Generate a new intent ID.

        Returns:
            New IntentId with random UUID.
        """
        return cls(value=uuid4())

    @classmethod
    def from_string(cls, value: str) -> Self:
        """Create IntentId from string representation.

        Args:
            value: String UUID representation.

        Returns:
            IntentId instance.
        """
        return cls(value=UUID(value))

    def __str__(self) -> str:
        """Return string representation.

        Returns:
            UUID as string.
        """
        return str(self.value)


@dataclass(frozen=True)
class OfferId(ValueObject):
    """Strongly-typed offer identifier.

    Offers represent a merchant's response with price and availability.
    """

    value: UUID

    @classmethod
    def generate(cls) -> Self:
        """Generate a new offer ID.

        Returns:
            New OfferId with random UUID.
        """
        return cls(value=uuid4())

    @classmethod
    def from_string(cls, value: str) -> Self:
        """Create OfferId from string representation.

        Args:
            value: String UUID representation.

        Returns:
            OfferId instance.
        """
        return cls(value=UUID(value))

    def __str__(self) -> str:
        """Return string representation.

        Returns:
            UUID as string.
        """
        return str(self.value)


@dataclass(frozen=True)
class MerchantId(ValueObject):
    """Strongly-typed merchant identifier.

    Merchant IDs are string-based (e.g., 'merchant-a', 'merchant-b').
    """

    value: str

    def __str__(self) -> str:
        """Return string representation.

        Returns:
            Merchant ID value.
        """
        return self.value

    def __post_init__(self) -> None:
        """Validate merchant ID format."""
        if not self.value or not self.value.strip():
            raise ValueError("Merchant ID cannot be empty")


@dataclass(frozen=True)
class CheckoutId(ValueObject):
    """Strongly-typed checkout session identifier."""

    value: UUID

    @classmethod
    def generate(cls) -> Self:
        """Generate a new checkout ID.

        Returns:
            New CheckoutId with random UUID.
        """
        return cls(value=uuid4())

    @classmethod
    def from_string(cls, value: str) -> Self:
        """Create CheckoutId from string representation.

        Args:
            value: String UUID representation.

        Returns:
            CheckoutId instance.
        """
        return cls(value=UUID(value))

    def __str__(self) -> str:
        """Return string representation.

        Returns:
            UUID as string.
        """
        return str(self.value)


@dataclass(frozen=True)
class ProductId(ValueObject):
    """Strongly-typed product identifier.

    Product IDs are string-based and come from merchant catalogs.
    """

    value: str

    def __str__(self) -> str:
        """Return string representation.

        Returns:
            Product ID value.
        """
        return self.value

    def __post_init__(self) -> None:
        """Validate product ID format."""
        if not self.value or not self.value.strip():
            raise ValueError("Product ID cannot be empty")


# ============================================================================
# Money Value Object
# ============================================================================


@dataclass(frozen=True)
class Money(ValueObject):
    """Represents monetary value with currency.

    Money is stored in the smallest currency unit (cents for USD/EUR)
    to avoid floating-point precision issues.

    Attributes:
        amount_cents: Amount in smallest currency unit (e.g., cents).
        currency: ISO 4217 currency code (e.g., 'USD', 'EUR').
    """

    amount_cents: int
    currency: str = "USD"

    def __post_init__(self) -> None:
        """Validate money constraints."""
        if self.amount_cents < 0:
            raise NegativeMoneyError(self.amount_cents)
        # Normalize currency to uppercase
        object.__setattr__(self, "currency", self.currency.upper())

    @classmethod
    def zero(cls, currency: str = "USD") -> Self:
        """Create zero amount money.

        Args:
            currency: Currency code.

        Returns:
            Money with zero amount.
        """
        return cls(amount_cents=0, currency=currency)

    @classmethod
    def from_decimal(cls, amount: Decimal, currency: str = "USD") -> Self:
        """Create money from decimal amount.

        Args:
            amount: Decimal amount in major units (e.g., dollars).
            currency: Currency code.

        Returns:
            Money instance.
        """
        cents = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        return cls(amount_cents=cents, currency=currency)

    @classmethod
    def from_float(cls, amount: float, currency: str = "USD") -> Self:
        """Create money from float amount.

        Note: Prefer from_decimal for precision. This method is
        provided for convenience but may have precision issues.

        Args:
            amount: Float amount in major units.
            currency: Currency code.

        Returns:
            Money instance.
        """
        return cls.from_decimal(Decimal(str(amount)), currency)

    def to_decimal(self) -> Decimal:
        """Convert to decimal amount in major units.

        Returns:
            Decimal amount (e.g., dollars from cents).
        """
        return Decimal(self.amount_cents) / 100

    def __add__(self, other: "Money") -> "Money":
        """Add two money amounts.

        Args:
            other: Money to add.

        Returns:
            New Money with sum.

        Raises:
            CurrencyMismatchError: If currencies don't match.
        """
        if self.currency != other.currency:
            raise CurrencyMismatchError(self.currency, other.currency)
        return Money(
            amount_cents=self.amount_cents + other.amount_cents,
            currency=self.currency,
        )

    def __sub__(self, other: "Money") -> "Money":
        """Subtract money amounts.

        Args:
            other: Money to subtract.

        Returns:
            New Money with difference.

        Raises:
            CurrencyMismatchError: If currencies don't match.
            NegativeMoneyError: If result would be negative.
        """
        if self.currency != other.currency:
            raise CurrencyMismatchError(self.currency, other.currency)
        return Money(
            amount_cents=self.amount_cents - other.amount_cents,
            currency=self.currency,
        )

    def __mul__(self, quantity: int) -> "Money":
        """Multiply money by quantity.

        Args:
            quantity: Multiplier.

        Returns:
            New Money with product.
        """
        return Money(
            amount_cents=self.amount_cents * quantity,
            currency=self.currency,
        )

    def __rmul__(self, quantity: int) -> "Money":
        """Right multiply money by quantity.

        Args:
            quantity: Multiplier.

        Returns:
            New Money with product.
        """
        return self.__mul__(quantity)

    def __str__(self) -> str:
        """Return formatted string representation.

        Returns:
            Formatted money string (e.g., '$12.99 USD').
        """
        symbol = {"USD": "$", "EUR": "€", "GBP": "£"}.get(self.currency, "")
        return f"{symbol}{self.to_decimal():.2f} {self.currency}"

    def is_zero(self) -> bool:
        """Check if amount is zero.

        Returns:
            True if amount is zero.
        """
        return self.amount_cents == 0


# ============================================================================
# Product Reference
# ============================================================================


@dataclass(frozen=True)
class ProductRef(ValueObject):
    """Reference to a product in a merchant's catalog.

    Contains minimal product information needed for cart operations.
    Full product details are fetched from the merchant when needed.

    Attributes:
        product_id: Merchant's product identifier.
        merchant_id: Merchant that sells this product.
        sku: Stock Keeping Unit (optional).
        name: Product name for display.
        unit_price: Price per unit.
    """

    product_id: ProductId
    merchant_id: MerchantId
    name: str
    unit_price: Money
    sku: str | None = None

    def __str__(self) -> str:
        """Return string representation.

        Returns:
            Product name with price.
        """
        return f"{self.name} ({self.unit_price})"


# ============================================================================
# Address Value Object
# ============================================================================


@dataclass(frozen=True)
class Address(ValueObject):
    """Shipping or billing address.

    Attributes:
        line1: Primary address line.
        line2: Secondary address line (optional).
        city: City name.
        state: State/province/region.
        postal_code: Postal/ZIP code.
        country: ISO 3166-1 alpha-2 country code.
    """

    line1: str
    city: str
    state: str
    postal_code: str
    country: str = "US"
    line2: str | None = None

    def __post_init__(self) -> None:
        """Validate address fields."""
        if not self.line1 or not self.line1.strip():
            raise ValueError("Address line1 cannot be empty")
        if not self.city or not self.city.strip():
            raise ValueError("City cannot be empty")
        if not self.postal_code or not self.postal_code.strip():
            raise ValueError("Postal code cannot be empty")
        # Normalize country to uppercase
        object.__setattr__(self, "country", self.country.upper())

    def format_single_line(self) -> str:
        """Format address as single line.

        Returns:
            Formatted address string.
        """
        parts = [self.line1]
        if self.line2:
            parts.append(self.line2)
        parts.extend([self.city, self.state, self.postal_code, self.country])
        return ", ".join(parts)


# ============================================================================
# Customer Information
# ============================================================================


@dataclass(frozen=True)
class CustomerInfo(ValueObject):
    """Customer information for an order.

    Attributes:
        email: Customer email address.
        name: Customer full name.
        phone: Phone number (optional).
    """

    email: str
    name: str
    phone: str | None = None

    def __post_init__(self) -> None:
        """Validate customer info."""
        if not self.email or "@" not in self.email:
            raise ValueError("Invalid email address")
        if not self.name or not self.name.strip():
            raise ValueError("Customer name cannot be empty")


# ============================================================================
# Webhook Payload
# ============================================================================


@dataclass(frozen=True)
class WebhookPayload(ValueObject):
    """Represents an incoming webhook payload.

    Used for idempotency and deduplication of webhook events.

    Attributes:
        idempotency_key: Unique key for deduplication.
        event_type: Type of webhook event.
        merchant_id: Source merchant.
        payload_hash: Hash of the payload content.
        raw_payload: Original payload data.
    """

    idempotency_key: str
    event_type: str
    merchant_id: MerchantId
    payload_hash: str
    raw_payload: dict[str, object]

    def __post_init__(self) -> None:
        """Validate webhook payload."""
        if not self.idempotency_key:
            raise ValueError("Idempotency key cannot be empty")
        if not self.event_type:
            raise ValueError("Event type cannot be empty")


# ============================================================================
# Frozen Receipt
# ============================================================================


@dataclass(frozen=True)
class FrozenReceiptItem(ValueObject):
    """An item in a frozen receipt snapshot.

    Attributes:
        product_id: Product identifier.
        variant_id: Variant identifier if applicable.
        sku: Stock keeping unit.
        title: Product title at time of freeze.
        unit_price_cents: Unit price at time of freeze.
        quantity: Ordered quantity.
        currency: Currency code.
    """

    product_id: str
    sku: str
    title: str
    unit_price_cents: int
    quantity: int
    currency: str = "USD"
    variant_id: str | None = None

    @property
    def line_total_cents(self) -> int:
        """Calculate line total in cents."""
        return self.unit_price_cents * self.quantity


@dataclass(frozen=True)
class FrozenReceipt(ValueObject):
    """Frozen receipt for approval flow.

    A FrozenReceipt captures the exact state of a checkout at the time
    approval was requested. It's used to detect price changes that would
    require re-approval.

    Attributes:
        hash: SHA-256 hash of the receipt contents.
        items: Frozen snapshot of checkout items.
        subtotal_cents: Subtotal at time of freeze.
        tax_cents: Tax at time of freeze.
        shipping_cents: Shipping at time of freeze.
        total_cents: Total at time of freeze.
        currency: Currency code.
        frozen_at: When the receipt was frozen.
    """

    hash: str
    items: tuple[FrozenReceiptItem, ...]
    subtotal_cents: int
    tax_cents: int
    shipping_cents: int
    total_cents: int
    currency: str
    frozen_at: str  # ISO format datetime string

    @classmethod
    def create(
        cls,
        items: list[FrozenReceiptItem],
        subtotal_cents: int,
        tax_cents: int,
        shipping_cents: int,
        total_cents: int,
        currency: str = "USD",
    ) -> "FrozenReceipt":
        """Create a frozen receipt with computed hash.

        Args:
            items: List of receipt items.
            subtotal_cents: Subtotal amount.
            tax_cents: Tax amount.
            shipping_cents: Shipping amount.
            total_cents: Total amount.
            currency: Currency code.

        Returns:
            FrozenReceipt with computed hash.
        """
        import hashlib
        from datetime import datetime, timezone

        # Build hash data
        items_data = "|".join(
            f"{i.product_id}:{i.variant_id or ''}:{i.quantity}:{i.unit_price_cents}"
            for i in items
        )
        hash_input = f"{total_cents}|{currency}|{items_data}"
        receipt_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:16]

        frozen_at = datetime.now(timezone.utc).isoformat()

        return cls(
            hash=receipt_hash,
            items=tuple(items),
            subtotal_cents=subtotal_cents,
            tax_cents=tax_cents,
            shipping_cents=shipping_cents,
            total_cents=total_cents,
            currency=currency,
            frozen_at=frozen_at,
        )

    def matches_total(self, current_total_cents: int) -> bool:
        """Check if current total matches frozen total.

        Args:
            current_total_cents: Current checkout total.

        Returns:
            True if totals match.
        """
        return self.total_cents == current_total_cents

    def get_price_difference(self, current_total_cents: int) -> int:
        """Get difference between frozen and current total.

        Args:
            current_total_cents: Current checkout total.

        Returns:
            Difference in cents (positive if current is higher).
        """
        return current_total_cents - self.total_cents
