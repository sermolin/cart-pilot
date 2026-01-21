"""Tests for Checkout entity and state machine.

Tests the checkout approval flow domain logic including:
- State transitions
- Frozen receipt creation
- Price change detection
- Re-approval requirements
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.entities import Checkout, CheckoutItem
from app.domain.exceptions import (
    CheckoutAlreadyConfirmedError,
    CheckoutExpiredError,
    InvalidStateTransitionError,
    ReapprovalRequiredError,
)
from app.domain.state_machines import CheckoutStatus
from app.domain.value_objects import CheckoutId, MerchantId, OfferId


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def checkout() -> Checkout:
    """Create a basic checkout for testing."""
    return Checkout.create(
        offer_id=OfferId.generate(),
        merchant_id=MerchantId("merchant-a"),
    )


@pytest.fixture
def sample_items() -> list[CheckoutItem]:
    """Create sample checkout items."""
    return [
        CheckoutItem(
            product_id="prod-001",
            sku="SKU-001",
            title="Test Product 1",
            unit_price_cents=2999,
            quantity=1,
            currency="USD",
        ),
        CheckoutItem(
            product_id="prod-002",
            sku="SKU-002",
            title="Test Product 2",
            unit_price_cents=1499,
            quantity=2,
            currency="USD",
        ),
    ]


# ============================================================================
# Test: Checkout Creation
# ============================================================================


class TestCheckoutCreation:
    """Tests for checkout creation."""

    def test_create_checkout_defaults(self):
        """Test checkout is created with correct defaults."""
        checkout = Checkout.create(
            offer_id=OfferId.generate(),
            merchant_id=MerchantId("merchant-a"),
        )

        assert checkout.status == CheckoutStatus.CREATED
        assert checkout.items == []
        assert checkout.total_cents == 0
        assert checkout.frozen_receipt is None
        assert checkout.merchant_order_id is None
        assert checkout.expires_at is not None
        assert len(checkout.audit_trail) == 1

    def test_create_checkout_with_idempotency_key(self):
        """Test checkout stores idempotency key."""
        checkout = Checkout.create(
            offer_id=OfferId.generate(),
            merchant_id=MerchantId("merchant-a"),
            idempotency_key="test-key-123",
        )

        assert checkout.idempotency_key == "test-key-123"

    def test_create_checkout_records_event(self):
        """Test checkout creation records domain event."""
        checkout = Checkout.create(
            offer_id=OfferId.generate(),
            merchant_id=MerchantId("merchant-a"),
        )

        events = checkout.collect_events()
        assert len(events) == 1
        assert events[0].event_type == "checkout.created"


# ============================================================================
# Test: Quote State Transition
# ============================================================================


class TestSetQuote:
    """Tests for setting quote on checkout."""

    def test_set_quote_from_created(self, checkout, sample_items):
        """Test transitioning from created to quoted."""
        checkout.set_quote(
            items=sample_items,
            subtotal_cents=5997,
            tax_cents=480,
            shipping_cents=999,
            total_cents=7476,
            currency="USD",
            merchant_checkout_id="merchant-123",
            receipt_hash="abc123",
        )

        assert checkout.status == CheckoutStatus.QUOTED
        assert len(checkout.items) == 2
        assert checkout.total_cents == 7476
        assert checkout.merchant_checkout_id == "merchant-123"
        assert checkout.receipt_hash == "abc123"

    def test_set_quote_records_audit(self, checkout, sample_items):
        """Test that setting quote adds audit entry."""
        initial_audit_count = len(checkout.audit_trail)

        checkout.set_quote(
            items=sample_items,
            subtotal_cents=5997,
            tax_cents=480,
            shipping_cents=999,
            total_cents=7476,
            currency="USD",
            merchant_checkout_id="merchant-123",
            receipt_hash="abc123",
        )

        assert len(checkout.audit_trail) == initial_audit_count + 1
        assert checkout.audit_trail[-1].action == "quote_received"


# ============================================================================
# Test: Request Approval
# ============================================================================


class TestRequestApproval:
    """Tests for requesting approval."""

    def test_request_approval_creates_frozen_receipt(self, checkout, sample_items):
        """Test that requesting approval freezes the receipt."""
        checkout.set_quote(
            items=sample_items,
            subtotal_cents=5997,
            tax_cents=480,
            shipping_cents=999,
            total_cents=7476,
            currency="USD",
            merchant_checkout_id="merchant-123",
            receipt_hash="abc123",
        )

        frozen = checkout.request_approval()

        assert checkout.status == CheckoutStatus.AWAITING_APPROVAL
        assert checkout.frozen_receipt is not None
        assert checkout.frozen_receipt.total_cents == 7476
        assert checkout.frozen_receipt.hash is not None
        assert frozen == checkout.frozen_receipt

    def test_request_approval_from_invalid_state(self, checkout):
        """Test that approval can only be requested from quoted state."""
        with pytest.raises(InvalidStateTransitionError):
            checkout.request_approval()

    def test_frozen_receipt_captures_all_items(self, checkout, sample_items):
        """Test that frozen receipt captures all item details."""
        checkout.set_quote(
            items=sample_items,
            subtotal_cents=5997,
            tax_cents=480,
            shipping_cents=999,
            total_cents=7476,
            currency="USD",
            merchant_checkout_id="merchant-123",
            receipt_hash="abc123",
        )

        frozen = checkout.request_approval()

        assert len(frozen.items) == 2
        assert frozen.items[0].product_id == "prod-001"
        assert frozen.items[0].unit_price_cents == 2999
        assert frozen.items[1].product_id == "prod-002"


# ============================================================================
# Test: Approve
# ============================================================================


class TestApprove:
    """Tests for approving checkout."""

    def test_approve_from_awaiting_approval(self, checkout, sample_items):
        """Test successful approval."""
        checkout.set_quote(
            items=sample_items,
            subtotal_cents=5997,
            tax_cents=480,
            shipping_cents=999,
            total_cents=7476,
            currency="USD",
            merchant_checkout_id="merchant-123",
            receipt_hash="abc123",
        )
        checkout.request_approval()

        checkout.approve(approved_by="test-user")

        assert checkout.status == CheckoutStatus.APPROVED
        assert checkout.approved_by == "test-user"
        assert checkout.approved_at is not None

    def test_approve_records_event(self, checkout, sample_items):
        """Test that approval records domain event."""
        checkout.set_quote(
            items=sample_items,
            subtotal_cents=5997,
            tax_cents=480,
            shipping_cents=999,
            total_cents=7476,
            currency="USD",
            merchant_checkout_id="merchant-123",
            receipt_hash="abc123",
        )
        checkout.request_approval()
        checkout.collect_events()  # Clear previous events

        checkout.approve(approved_by="test-user")

        events = checkout.collect_events()
        assert any(e.event_type == "checkout.approved" for e in events)


# ============================================================================
# Test: Confirm
# ============================================================================


class TestConfirm:
    """Tests for confirming checkout."""

    def test_confirm_from_approved(self, checkout, sample_items):
        """Test successful confirmation."""
        checkout.set_quote(
            items=sample_items,
            subtotal_cents=5997,
            tax_cents=480,
            shipping_cents=999,
            total_cents=7476,
            currency="USD",
            merchant_checkout_id="merchant-123",
            receipt_hash="abc123",
        )
        checkout.request_approval()
        checkout.approve(approved_by="test-user")

        checkout.confirm(merchant_order_id="ORD-123")

        assert checkout.status == CheckoutStatus.CONFIRMED
        assert checkout.merchant_order_id == "ORD-123"
        assert checkout.confirmed_at is not None

    def test_confirm_without_approval_fails(self, checkout, sample_items):
        """Test that confirmation requires approval."""
        checkout.set_quote(
            items=sample_items,
            subtotal_cents=5997,
            tax_cents=480,
            shipping_cents=999,
            total_cents=7476,
            currency="USD",
            merchant_checkout_id="merchant-123",
            receipt_hash="abc123",
        )

        with pytest.raises(Exception):  # Either InvalidStateTransitionError or CheckoutNotApprovedError
            checkout.confirm(merchant_order_id="ORD-123")

    def test_confirm_already_confirmed_raises(self, checkout, sample_items):
        """Test that double confirmation raises error."""
        checkout.set_quote(
            items=sample_items,
            subtotal_cents=5997,
            tax_cents=480,
            shipping_cents=999,
            total_cents=7476,
            currency="USD",
            merchant_checkout_id="merchant-123",
            receipt_hash="abc123",
        )
        checkout.request_approval()
        checkout.approve(approved_by="test-user")
        checkout.confirm(merchant_order_id="ORD-123")

        with pytest.raises(CheckoutAlreadyConfirmedError):
            checkout.confirm(merchant_order_id="ORD-456")


# ============================================================================
# Test: Re-approval on Price Change
# ============================================================================


class TestReapproval:
    """Tests for re-approval on price change."""

    def test_price_change_resets_to_quoted(self, checkout, sample_items):
        """Test that price change in awaiting_approval resets to quoted."""
        checkout.set_quote(
            items=sample_items,
            subtotal_cents=5997,
            tax_cents=480,
            shipping_cents=999,
            total_cents=7476,
            currency="USD",
            merchant_checkout_id="merchant-123",
            receipt_hash="abc123",
        )
        checkout.request_approval()

        # Simulate price change with a new quote
        new_items = [
            CheckoutItem(
                product_id="prod-001",
                sku="SKU-001",
                title="Test Product 1",
                unit_price_cents=3999,  # Price increased
                quantity=1,
                currency="USD",
            ),
        ]

        checkout.set_quote(
            items=new_items,
            subtotal_cents=3999,
            tax_cents=320,
            shipping_cents=999,
            total_cents=5318,  # Different total
            currency="USD",
            merchant_checkout_id="merchant-456",
            receipt_hash="xyz789",
        )

        # Status should be back to quoted
        assert checkout.status == CheckoutStatus.QUOTED
        assert checkout.frozen_receipt is None  # Receipt cleared

    def test_approve_with_price_mismatch_raises(self, checkout, sample_items):
        """Test that approving with price change raises error."""
        checkout.set_quote(
            items=sample_items,
            subtotal_cents=5997,
            tax_cents=480,
            shipping_cents=999,
            total_cents=7476,
            currency="USD",
            merchant_checkout_id="merchant-123",
            receipt_hash="abc123",
        )
        checkout.request_approval()

        # Manually change the total to simulate external price change
        checkout.total_cents = 8000  # Someone changed the price!

        with pytest.raises(ReapprovalRequiredError) as exc_info:
            checkout.approve(approved_by="test-user")

        assert exc_info.value.details["original_total_cents"] == 7476
        assert exc_info.value.details["new_total_cents"] == 8000

    def test_confirm_with_price_mismatch_raises(self, checkout, sample_items):
        """Test that confirming with price change raises error."""
        checkout.set_quote(
            items=sample_items,
            subtotal_cents=5997,
            tax_cents=480,
            shipping_cents=999,
            total_cents=7476,
            currency="USD",
            merchant_checkout_id="merchant-123",
            receipt_hash="abc123",
        )
        checkout.request_approval()
        checkout.approve(approved_by="test-user")

        # Simulate price change after approval
        checkout.total_cents = 8500

        with pytest.raises(ReapprovalRequiredError):
            checkout.confirm(merchant_order_id="ORD-123")


# ============================================================================
# Test: Expiration
# ============================================================================


class TestExpiration:
    """Tests for checkout expiration."""

    def test_expired_checkout_blocks_operations(self, checkout, sample_items):
        """Test that expired checkout cannot be quoted."""
        # Force expiration
        checkout.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)

        with pytest.raises(CheckoutExpiredError):
            checkout.set_quote(
                items=sample_items,
                subtotal_cents=5997,
                tax_cents=480,
                shipping_cents=999,
                total_cents=7476,
                currency="USD",
                merchant_checkout_id="merchant-123",
                receipt_hash="abc123",
            )

    def test_is_expired_property(self, checkout):
        """Test is_expired property."""
        assert not checkout.is_expired

        checkout.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        assert checkout.is_expired


# ============================================================================
# Test: Frozen Receipt
# ============================================================================


class TestFrozenReceipt:
    """Tests for frozen receipt functionality."""

    def test_frozen_receipt_matches_total(self, checkout, sample_items):
        """Test frozen receipt total matching."""
        checkout.set_quote(
            items=sample_items,
            subtotal_cents=5997,
            tax_cents=480,
            shipping_cents=999,
            total_cents=7476,
            currency="USD",
            merchant_checkout_id="merchant-123",
            receipt_hash="abc123",
        )
        frozen = checkout.request_approval()

        assert frozen.matches_total(7476)
        assert not frozen.matches_total(8000)

    def test_frozen_receipt_price_difference(self, checkout, sample_items):
        """Test frozen receipt price difference calculation."""
        checkout.set_quote(
            items=sample_items,
            subtotal_cents=5997,
            tax_cents=480,
            shipping_cents=999,
            total_cents=7476,
            currency="USD",
            merchant_checkout_id="merchant-123",
            receipt_hash="abc123",
        )
        frozen = checkout.request_approval()

        assert frozen.get_price_difference(7476) == 0
        assert frozen.get_price_difference(8000) == 524
        assert frozen.get_price_difference(7000) == -476

    def test_frozen_receipt_hash_changes_with_items(self, checkout, sample_items):
        """Test that different items produce different hashes."""
        checkout.set_quote(
            items=sample_items,
            subtotal_cents=5997,
            tax_cents=480,
            shipping_cents=999,
            total_cents=7476,
            currency="USD",
            merchant_checkout_id="merchant-123",
            receipt_hash="abc123",
        )
        frozen1 = checkout.request_approval()

        # Create new checkout with different items
        checkout2 = Checkout.create(
            offer_id=OfferId.generate(),
            merchant_id=MerchantId("merchant-a"),
        )
        different_items = [
            CheckoutItem(
                product_id="prod-999",
                sku="SKU-999",
                title="Different Product",
                unit_price_cents=7476,  # Same total
                quantity=1,
                currency="USD",
            ),
        ]
        checkout2.set_quote(
            items=different_items,
            subtotal_cents=7476,
            tax_cents=0,
            shipping_cents=0,
            total_cents=7476,  # Same total
            currency="USD",
            merchant_checkout_id="merchant-456",
            receipt_hash="xyz789",
        )
        frozen2 = checkout2.request_approval()

        # Hashes should be different because items are different
        assert frozen1.hash != frozen2.hash


# ============================================================================
# Test: Audit Trail
# ============================================================================


class TestAuditTrail:
    """Tests for checkout audit trail."""

    def test_audit_trail_records_all_transitions(self, checkout, sample_items):
        """Test that audit trail captures all state changes."""
        # Created
        assert len(checkout.audit_trail) == 1

        # Quoted
        checkout.set_quote(
            items=sample_items,
            subtotal_cents=5997,
            tax_cents=480,
            shipping_cents=999,
            total_cents=7476,
            currency="USD",
            merchant_checkout_id="merchant-123",
            receipt_hash="abc123",
        )
        assert len(checkout.audit_trail) == 2

        # Awaiting approval
        checkout.request_approval()
        assert len(checkout.audit_trail) == 3

        # Approved
        checkout.approve(approved_by="test-user")
        assert len(checkout.audit_trail) == 4

        # Confirmed
        checkout.confirm(merchant_order_id="ORD-123")
        assert len(checkout.audit_trail) == 5

        # Verify audit entries
        actions = [entry.action for entry in checkout.audit_trail]
        assert actions == [
            "checkout_created",
            "quote_received",
            "approval_requested",
            "approved",
            "confirmed",
        ]

    def test_audit_trail_includes_actor(self, checkout, sample_items):
        """Test that audit trail records who performed actions."""
        checkout.set_quote(
            items=sample_items,
            subtotal_cents=5997,
            tax_cents=480,
            shipping_cents=999,
            total_cents=7476,
            currency="USD",
            merchant_checkout_id="merchant-123",
            receipt_hash="abc123",
        )
        checkout.request_approval()
        checkout.approve(approved_by="manager@example.com")

        approval_entry = checkout.audit_trail[-1]
        assert approval_entry.actor == "manager@example.com"
