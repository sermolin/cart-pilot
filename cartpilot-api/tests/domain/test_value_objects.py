"""Tests for domain value objects."""

from decimal import Decimal

import pytest

from app.domain import (
    Address,
    CartId,
    CustomerInfo,
    MerchantId,
    Money,
    ProductId,
    ProductRef,
)
from app.domain.exceptions import CurrencyMismatchError, NegativeMoneyError


class TestMoney:
    """Tests for Money value object."""

    def test_create_from_cents(self) -> None:
        """Money can be created from cents."""
        money = Money(amount_cents=1999, currency="USD")
        assert money.amount_cents == 1999
        assert money.currency == "USD"

    def test_create_from_float(self) -> None:
        """Money can be created from float."""
        money = Money.from_float(19.99)
        assert money.amount_cents == 1999
        assert money.currency == "USD"

    def test_create_from_decimal(self) -> None:
        """Money can be created from Decimal."""
        money = Money.from_decimal(Decimal("19.99"))
        assert money.amount_cents == 1999

    def test_to_decimal(self) -> None:
        """Money can be converted to Decimal."""
        money = Money(amount_cents=1999)
        assert money.to_decimal() == Decimal("19.99")

    def test_zero(self) -> None:
        """Zero money can be created."""
        money = Money.zero()
        assert money.amount_cents == 0
        assert money.is_zero()

    def test_currency_normalized_to_uppercase(self) -> None:
        """Currency is normalized to uppercase."""
        money = Money(amount_cents=100, currency="eur")
        assert money.currency == "EUR"

    def test_negative_amount_raises_error(self) -> None:
        """Negative amounts raise NegativeMoneyError."""
        with pytest.raises(NegativeMoneyError):
            Money(amount_cents=-100)

    def test_addition(self) -> None:
        """Money can be added."""
        m1 = Money(amount_cents=1000)
        m2 = Money(amount_cents=500)
        result = m1 + m2
        assert result.amount_cents == 1500

    def test_addition_currency_mismatch(self) -> None:
        """Adding different currencies raises error."""
        m1 = Money(amount_cents=1000, currency="USD")
        m2 = Money(amount_cents=500, currency="EUR")
        with pytest.raises(CurrencyMismatchError):
            _ = m1 + m2

    def test_subtraction(self) -> None:
        """Money can be subtracted."""
        m1 = Money(amount_cents=1000)
        m2 = Money(amount_cents=300)
        result = m1 - m2
        assert result.amount_cents == 700

    def test_subtraction_negative_result_raises(self) -> None:
        """Subtraction resulting in negative raises error."""
        m1 = Money(amount_cents=100)
        m2 = Money(amount_cents=500)
        with pytest.raises(NegativeMoneyError):
            _ = m1 - m2

    def test_multiplication(self) -> None:
        """Money can be multiplied by quantity."""
        money = Money(amount_cents=1000)
        result = money * 3
        assert result.amount_cents == 3000

    def test_right_multiplication(self) -> None:
        """Money supports right multiplication."""
        money = Money(amount_cents=1000)
        result = 3 * money
        assert result.amount_cents == 3000

    def test_string_representation(self) -> None:
        """Money has readable string representation."""
        money = Money(amount_cents=1999, currency="USD")
        assert str(money) == "$19.99 USD"

    def test_immutability(self) -> None:
        """Money is immutable."""
        money = Money(amount_cents=1000)
        with pytest.raises(AttributeError):
            money.amount_cents = 2000  # type: ignore


class TestAddress:
    """Tests for Address value object."""

    def test_create_address(self) -> None:
        """Address can be created with required fields."""
        addr = Address(
            line1="123 Main St",
            city="Austin",
            state="TX",
            postal_code="78701",
        )
        assert addr.line1 == "123 Main St"
        assert addr.city == "Austin"
        assert addr.country == "US"

    def test_address_with_line2(self) -> None:
        """Address can have optional line2."""
        addr = Address(
            line1="123 Main St",
            line2="Apt 4B",
            city="Austin",
            state="TX",
            postal_code="78701",
        )
        assert addr.line2 == "Apt 4B"

    def test_country_normalized(self) -> None:
        """Country is normalized to uppercase."""
        addr = Address(
            line1="123 Main St",
            city="Austin",
            state="TX",
            postal_code="78701",
            country="us",
        )
        assert addr.country == "US"

    def test_empty_line1_raises(self) -> None:
        """Empty line1 raises error."""
        with pytest.raises(ValueError, match="line1"):
            Address(line1="", city="Austin", state="TX", postal_code="78701")

    def test_format_single_line(self) -> None:
        """Address can be formatted as single line."""
        addr = Address(
            line1="123 Main St",
            city="Austin",
            state="TX",
            postal_code="78701",
        )
        formatted = addr.format_single_line()
        assert "123 Main St" in formatted
        assert "Austin" in formatted
        assert "TX" in formatted


class TestCustomerInfo:
    """Tests for CustomerInfo value object."""

    def test_create_customer(self) -> None:
        """CustomerInfo can be created."""
        customer = CustomerInfo(email="test@example.com", name="John Doe")
        assert customer.email == "test@example.com"
        assert customer.name == "John Doe"
        assert customer.phone is None

    def test_customer_with_phone(self) -> None:
        """CustomerInfo can have phone."""
        customer = CustomerInfo(
            email="test@example.com",
            name="John Doe",
            phone="+1-555-1234",
        )
        assert customer.phone == "+1-555-1234"

    def test_invalid_email_raises(self) -> None:
        """Invalid email raises error."""
        with pytest.raises(ValueError, match="email"):
            CustomerInfo(email="invalid", name="John")

    def test_empty_name_raises(self) -> None:
        """Empty name raises error."""
        with pytest.raises(ValueError, match="name"):
            CustomerInfo(email="test@example.com", name="")


class TestTypedIds:
    """Tests for typed ID value objects."""

    def test_cart_id_generate(self) -> None:
        """CartId can be generated."""
        cart_id = CartId.generate()
        assert cart_id.value is not None

    def test_cart_id_from_string(self) -> None:
        """CartId can be created from string."""
        cart_id = CartId.from_string("123e4567-e89b-12d3-a456-426614174000")
        assert str(cart_id) == "123e4567-e89b-12d3-a456-426614174000"

    def test_cart_id_equality(self) -> None:
        """CartIds with same value are equal."""
        id1 = CartId.from_string("123e4567-e89b-12d3-a456-426614174000")
        id2 = CartId.from_string("123e4567-e89b-12d3-a456-426614174000")
        assert id1 == id2

    def test_merchant_id(self) -> None:
        """MerchantId works with string values."""
        merchant_id = MerchantId("merchant-a")
        assert str(merchant_id) == "merchant-a"

    def test_empty_merchant_id_raises(self) -> None:
        """Empty MerchantId raises error."""
        with pytest.raises(ValueError):
            MerchantId("")

    def test_product_id(self) -> None:
        """ProductId works with string values."""
        product_id = ProductId("SKU-001")
        assert str(product_id) == "SKU-001"


class TestProductRef:
    """Tests for ProductRef value object."""

    def test_create_product_ref(self) -> None:
        """ProductRef can be created."""
        product = ProductRef(
            product_id=ProductId("SKU-001"),
            merchant_id=MerchantId("merchant-a"),
            name="Widget",
            unit_price=Money.from_float(29.99),
        )
        assert product.name == "Widget"
        assert product.unit_price.amount_cents == 2999

    def test_product_ref_with_sku(self) -> None:
        """ProductRef can have optional SKU."""
        product = ProductRef(
            product_id=ProductId("SKU-001"),
            merchant_id=MerchantId("merchant-a"),
            name="Widget",
            unit_price=Money.from_float(29.99),
            sku="WDG-001-BLU",
        )
        assert product.sku == "WDG-001-BLU"
