"""Tests for domain state machines."""

import pytest

from app.domain import (
    ApprovalStatus,
    CartStatus,
    OrderStatus,
)
from app.domain.exceptions import InvalidStateTransitionError
from app.domain.state_machines import (
    validate_approval_transition,
    validate_cart_transition,
    validate_order_transition,
)


class TestCartStatus:
    """Tests for CartStatus state machine."""

    def test_draft_can_transition_to_checkout(self) -> None:
        """DRAFT can transition to CHECKOUT."""
        assert CartStatus.DRAFT.can_transition_to(CartStatus.CHECKOUT)

    def test_draft_can_transition_to_abandoned(self) -> None:
        """DRAFT can transition to ABANDONED."""
        assert CartStatus.DRAFT.can_transition_to(CartStatus.ABANDONED)

    def test_draft_cannot_transition_to_completed(self) -> None:
        """DRAFT cannot transition directly to COMPLETED."""
        assert not CartStatus.DRAFT.can_transition_to(CartStatus.COMPLETED)

    def test_checkout_can_transition_to_pending_approval(self) -> None:
        """CHECKOUT can transition to PENDING_APPROVAL."""
        assert CartStatus.CHECKOUT.can_transition_to(CartStatus.PENDING_APPROVAL)

    def test_checkout_can_go_back_to_draft(self) -> None:
        """CHECKOUT can transition back to DRAFT."""
        assert CartStatus.CHECKOUT.can_transition_to(CartStatus.DRAFT)

    def test_submitted_can_complete_or_fail(self) -> None:
        """SUBMITTED can transition to COMPLETED or FAILED."""
        assert CartStatus.SUBMITTED.can_transition_to(CartStatus.COMPLETED)
        assert CartStatus.SUBMITTED.can_transition_to(CartStatus.FAILED)

    def test_completed_is_terminal(self) -> None:
        """COMPLETED is a terminal state."""
        assert CartStatus.COMPLETED.is_terminal()
        assert CartStatus.COMPLETED.allowed_transitions() == []

    def test_abandoned_is_terminal(self) -> None:
        """ABANDONED is a terminal state."""
        assert CartStatus.ABANDONED.is_terminal()

    def test_failed_can_retry(self) -> None:
        """FAILED can transition back to DRAFT for retry."""
        assert CartStatus.FAILED.can_transition_to(CartStatus.DRAFT)

    def test_draft_is_editable(self) -> None:
        """DRAFT is an editable state."""
        assert CartStatus.DRAFT.is_editable()

    def test_checkout_is_editable(self) -> None:
        """CHECKOUT is an editable state."""
        assert CartStatus.CHECKOUT.is_editable()

    def test_submitted_is_not_editable(self) -> None:
        """SUBMITTED is not editable."""
        assert not CartStatus.SUBMITTED.is_editable()

    def test_draft_is_active(self) -> None:
        """DRAFT is an active state."""
        assert CartStatus.DRAFT.is_active()

    def test_completed_is_not_active(self) -> None:
        """COMPLETED is not active."""
        assert not CartStatus.COMPLETED.is_active()

    def test_allowed_transitions_from_draft(self) -> None:
        """DRAFT has correct allowed transitions."""
        allowed = CartStatus.DRAFT.allowed_transitions()
        assert CartStatus.CHECKOUT in allowed
        assert CartStatus.ABANDONED in allowed
        assert len(allowed) == 2


class TestOrderStatus:
    """Tests for OrderStatus state machine."""

    def test_pending_can_confirm(self) -> None:
        """PENDING can transition to CONFIRMED."""
        assert OrderStatus.PENDING.can_transition_to(OrderStatus.CONFIRMED)

    def test_pending_can_cancel(self) -> None:
        """PENDING can transition to CANCELLED."""
        assert OrderStatus.PENDING.can_transition_to(OrderStatus.CANCELLED)

    def test_confirmed_can_ship(self) -> None:
        """CONFIRMED can transition to SHIPPED."""
        assert OrderStatus.CONFIRMED.can_transition_to(OrderStatus.SHIPPED)

    def test_shipped_can_deliver(self) -> None:
        """SHIPPED can transition to DELIVERED."""
        assert OrderStatus.SHIPPED.can_transition_to(OrderStatus.DELIVERED)

    def test_delivered_can_refund(self) -> None:
        """DELIVERED can transition to REFUNDED."""
        assert OrderStatus.DELIVERED.can_transition_to(OrderStatus.REFUNDED)

    def test_cancelled_is_terminal(self) -> None:
        """CANCELLED is a terminal state."""
        assert OrderStatus.CANCELLED.is_terminal()

    def test_refunded_is_terminal(self) -> None:
        """REFUNDED is a terminal state."""
        assert OrderStatus.REFUNDED.is_terminal()

    def test_pending_is_cancellable(self) -> None:
        """PENDING is cancellable."""
        assert OrderStatus.PENDING.is_cancellable()

    def test_confirmed_is_cancellable(self) -> None:
        """CONFIRMED is cancellable."""
        assert OrderStatus.CONFIRMED.is_cancellable()

    def test_delivered_is_not_cancellable(self) -> None:
        """DELIVERED is not cancellable."""
        assert not OrderStatus.DELIVERED.is_cancellable()

    def test_pending_is_fulfillable(self) -> None:
        """PENDING is fulfillable."""
        assert OrderStatus.PENDING.is_fulfillable()


class TestApprovalStatus:
    """Tests for ApprovalStatus state machine."""

    def test_pending_can_approve(self) -> None:
        """PENDING can transition to APPROVED."""
        assert ApprovalStatus.PENDING.can_transition_to(ApprovalStatus.APPROVED)

    def test_pending_can_reject(self) -> None:
        """PENDING can transition to REJECTED."""
        assert ApprovalStatus.PENDING.can_transition_to(ApprovalStatus.REJECTED)

    def test_pending_can_expire(self) -> None:
        """PENDING can transition to EXPIRED."""
        assert ApprovalStatus.PENDING.can_transition_to(ApprovalStatus.EXPIRED)

    def test_approved_is_terminal(self) -> None:
        """APPROVED is a terminal state."""
        assert ApprovalStatus.APPROVED.is_terminal()

    def test_rejected_is_terminal(self) -> None:
        """REJECTED is a terminal state."""
        assert ApprovalStatus.REJECTED.is_terminal()

    def test_pending_is_actionable(self) -> None:
        """PENDING is actionable."""
        assert ApprovalStatus.PENDING.is_actionable()

    def test_approved_is_not_actionable(self) -> None:
        """APPROVED is not actionable."""
        assert not ApprovalStatus.APPROVED.is_actionable()

    def test_approved_is_resolved(self) -> None:
        """APPROVED is resolved."""
        assert ApprovalStatus.APPROVED.is_resolved()

    def test_rejected_is_resolved(self) -> None:
        """REJECTED is resolved."""
        assert ApprovalStatus.REJECTED.is_resolved()

    def test_expired_is_not_resolved(self) -> None:
        """EXPIRED is not resolved (it wasn't approved or rejected)."""
        assert not ApprovalStatus.EXPIRED.is_resolved()


class TestValidateTransitions:
    """Tests for transition validation functions."""

    def test_validate_cart_transition_valid(self) -> None:
        """Valid cart transition does not raise."""
        validate_cart_transition("cart-1", CartStatus.DRAFT, CartStatus.CHECKOUT)

    def test_validate_cart_transition_invalid(self) -> None:
        """Invalid cart transition raises error."""
        with pytest.raises(InvalidStateTransitionError) as exc_info:
            validate_cart_transition("cart-1", CartStatus.DRAFT, CartStatus.COMPLETED)
        
        assert exc_info.value.details["entity_type"] == "Cart"
        assert exc_info.value.details["current_state"] == "draft"
        assert exc_info.value.details["target_state"] == "completed"

    def test_validate_order_transition_valid(self) -> None:
        """Valid order transition does not raise."""
        validate_order_transition("order-1", OrderStatus.PENDING, OrderStatus.CONFIRMED)

    def test_validate_order_transition_invalid(self) -> None:
        """Invalid order transition raises error."""
        with pytest.raises(InvalidStateTransitionError):
            validate_order_transition("order-1", OrderStatus.PENDING, OrderStatus.DELIVERED)

    def test_validate_approval_transition_valid(self) -> None:
        """Valid approval transition does not raise."""
        validate_approval_transition("approval-1", ApprovalStatus.PENDING, ApprovalStatus.APPROVED)

    def test_validate_approval_transition_invalid(self) -> None:
        """Invalid approval transition raises error."""
        with pytest.raises(InvalidStateTransitionError):
            validate_approval_transition("approval-1", ApprovalStatus.APPROVED, ApprovalStatus.REJECTED)
