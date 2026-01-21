"""State machines for domain entities.

Deterministic state machines that define valid state transitions
for carts, orders, and approvals. State machines enforce business
rules about what operations are valid in each state.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Generic, Self, TypeVar

from app.domain.exceptions import InvalidStateTransitionError

# Type variable for state machine states
S = TypeVar("S", bound=Enum)


# ============================================================================
# Cart State Machine
# ============================================================================


class CartStatus(str, Enum):
    """Cart lifecycle states.

    State diagram:
        DRAFT ──────────────────┬──────────────────────► ABANDONED
          │                     │
          │ start_checkout      │ expire
          ▼                     │
        CHECKOUT ───────────────┤
          │                     │
          │ submit              │
          ▼                     │
        PENDING_APPROVAL ───────┤
          │       │             │
          │       │ reject      │
          │       ▼             │
          │     REJECTED ───────┘
          │
          │ approve
          ▼
        SUBMITTED ──────────────┬──────────────────────► FAILED
          │                     │
          │ confirm             │ fail
          ▼                     │
        COMPLETED ◄─────────────┘
    """

    DRAFT = "draft"
    CHECKOUT = "checkout"
    PENDING_APPROVAL = "pending_approval"
    REJECTED = "rejected"
    SUBMITTED = "submitted"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"

    def can_transition_to(self, target: "CartStatus") -> bool:
        """Check if transition to target state is valid.

        Args:
            target: Target state to transition to.

        Returns:
            True if transition is valid.
        """
        return target in _CART_TRANSITIONS.get(self, set())

    def allowed_transitions(self) -> list["CartStatus"]:
        """Get list of valid target states.

        Returns:
            List of states that can be transitioned to.
        """
        return list(_CART_TRANSITIONS.get(self, set()))

    def is_editable(self) -> bool:
        """Check if cart can be modified (add/remove items).

        Returns:
            True if cart is in an editable state.
        """
        return self in {CartStatus.DRAFT, CartStatus.CHECKOUT}

    def is_terminal(self) -> bool:
        """Check if this is a terminal (final) state.

        Returns:
            True if no further transitions are possible.
        """
        return len(_CART_TRANSITIONS.get(self, set())) == 0

    def is_active(self) -> bool:
        """Check if cart is in an active (non-terminal) state.

        Returns:
            True if cart is still active.
        """
        return not self.is_terminal()


# Cart state transitions (defined outside enum to avoid Enum restrictions)
_CART_TRANSITIONS: dict[CartStatus, set[CartStatus]] = {
    CartStatus.DRAFT: {CartStatus.CHECKOUT, CartStatus.ABANDONED},
    CartStatus.CHECKOUT: {CartStatus.PENDING_APPROVAL, CartStatus.DRAFT, CartStatus.ABANDONED},
    CartStatus.PENDING_APPROVAL: {CartStatus.SUBMITTED, CartStatus.REJECTED, CartStatus.ABANDONED},
    CartStatus.REJECTED: {CartStatus.DRAFT, CartStatus.ABANDONED},
    CartStatus.SUBMITTED: {CartStatus.COMPLETED, CartStatus.FAILED},
    CartStatus.COMPLETED: set(),  # Terminal state
    CartStatus.FAILED: {CartStatus.DRAFT},  # Can retry from failed
    CartStatus.ABANDONED: set(),  # Terminal state
}


# ============================================================================
# Order State Machine
# ============================================================================


class OrderStatus(str, Enum):
    """Order lifecycle states.

    State diagram:
        PENDING ─────────────────────────────────────► CANCELLED
          │                                              ▲
          │ confirm                                      │
          ▼                                              │
        CONFIRMED ────────────────────────────────────►──┤
          │                                              │
          │ ship                                         │
          ▼                                              │
        SHIPPED ──────────────────────────────────────►──┘
          │
          │ deliver
          ▼
        DELIVERED
          │
          │ return (partial or full)
          ▼
        RETURNED (optional)
    """

    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    RETURNED = "returned"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"

    def can_transition_to(self, target: "OrderStatus") -> bool:
        """Check if transition to target state is valid.

        Args:
            target: Target state to transition to.

        Returns:
            True if transition is valid.
        """
        return target in _ORDER_TRANSITIONS.get(self, set())

    def allowed_transitions(self) -> list["OrderStatus"]:
        """Get list of valid target states.

        Returns:
            List of states that can be transitioned to.
        """
        return list(_ORDER_TRANSITIONS.get(self, set()))

    def is_cancellable(self) -> bool:
        """Check if order can be cancelled.

        Returns:
            True if order can be cancelled.
        """
        return self in {OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.SHIPPED}

    def is_terminal(self) -> bool:
        """Check if this is a terminal (final) state.

        Returns:
            True if no further transitions are possible.
        """
        return len(_ORDER_TRANSITIONS.get(self, set())) == 0

    def is_fulfillable(self) -> bool:
        """Check if order is in a fulfillable state.

        Returns:
            True if order can proceed toward delivery.
        """
        return self in {OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.SHIPPED}


# Order state transitions
_ORDER_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PENDING: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED, OrderStatus.CANCELLED},
    OrderStatus.DELIVERED: {OrderStatus.RETURNED, OrderStatus.REFUNDED},
    OrderStatus.RETURNED: {OrderStatus.REFUNDED},
    OrderStatus.CANCELLED: set(),  # Terminal state
    OrderStatus.REFUNDED: set(),  # Terminal state
}


# ============================================================================
# Approval State Machine
# ============================================================================


class ApprovalStatus(str, Enum):
    """Approval request lifecycle states.

    Approvals are required for agent-initiated purchases above
    certain thresholds or for sensitive operations.

    State diagram:
        PENDING ──────────────────────────────────► EXPIRED
          │           │
          │ approve   │ reject
          ▼           ▼
        APPROVED    REJECTED
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"

    def can_transition_to(self, target: "ApprovalStatus") -> bool:
        """Check if transition to target state is valid.

        Args:
            target: Target state to transition to.

        Returns:
            True if transition is valid.
        """
        return target in _APPROVAL_TRANSITIONS.get(self, set())

    def allowed_transitions(self) -> list["ApprovalStatus"]:
        """Get list of valid target states.

        Returns:
            List of states that can be transitioned to.
        """
        return list(_APPROVAL_TRANSITIONS.get(self, set()))

    def is_terminal(self) -> bool:
        """Check if this is a terminal (final) state.

        Returns:
            True if no further transitions are possible.
        """
        return self != ApprovalStatus.PENDING

    def is_resolved(self) -> bool:
        """Check if approval has been resolved (approved or rejected).

        Returns:
            True if approval has been resolved.
        """
        return self in {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED}

    def is_actionable(self) -> bool:
        """Check if approval can still be acted upon.

        Returns:
            True if approval is pending and not expired.
        """
        return self == ApprovalStatus.PENDING


# Approval state transitions
_APPROVAL_TRANSITIONS: dict[ApprovalStatus, set[ApprovalStatus]] = {
    ApprovalStatus.PENDING: {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED, ApprovalStatus.EXPIRED},
    ApprovalStatus.APPROVED: set(),  # Terminal state
    ApprovalStatus.REJECTED: set(),  # Terminal state
    ApprovalStatus.EXPIRED: set(),  # Terminal state
}


# ============================================================================
# Checkout State Machine
# ============================================================================


class CheckoutStatus(str, Enum):
    """Checkout session lifecycle states.

    State diagram:
        [*] ─────────────────────────────────────────────► CANCELLED
         │                                                    ▲
         │ create                                             │
         ▼                                                    │
        CREATED ──────────────────────────────────────────────┤
         │                                                    │
         │ quote                                              │
         ▼                                                    │
        QUOTED ───────────────────────────────────────────────┤
         │                                                    │
         │ request_approval                                   │
         ▼                                                    │
        AWAITING_APPROVAL ────────────────────────────────────┤
         │       │                                            │
         │       │ price_changed → back to QUOTED             │
         │       │                                            │
         │ approve                                            │
         ▼                                                    │
        APPROVED ─────────────────────────────────────────────┤
         │       │                                            │
         │       │ timeout                                    │
         │       ▼                                            │
         │     FAILED ────────────────────────────────────────┘
         │
         │ confirm
         ▼
        CONFIRMED ◄─────────────────────────────────────────
    """

    CREATED = "created"
    QUOTED = "quoted"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def can_transition_to(self, target: "CheckoutStatus") -> bool:
        """Check if transition to target state is valid.

        Args:
            target: Target state to transition to.

        Returns:
            True if transition is valid.
        """
        return target in _CHECKOUT_TRANSITIONS.get(self, set())

    def allowed_transitions(self) -> list["CheckoutStatus"]:
        """Get list of valid target states.

        Returns:
            List of states that can be transitioned to.
        """
        return list(_CHECKOUT_TRANSITIONS.get(self, set()))

    def is_terminal(self) -> bool:
        """Check if this is a terminal (final) state.

        Returns:
            True if no further transitions are possible.
        """
        return len(_CHECKOUT_TRANSITIONS.get(self, set())) == 0

    def is_cancellable(self) -> bool:
        """Check if checkout can be cancelled.

        Returns:
            True if checkout can be cancelled.
        """
        return self in {
            CheckoutStatus.CREATED,
            CheckoutStatus.QUOTED,
            CheckoutStatus.AWAITING_APPROVAL,
            CheckoutStatus.APPROVED,
        }

    def is_quotable(self) -> bool:
        """Check if a new quote can be requested.

        Returns:
            True if quote can be requested.
        """
        return self in {CheckoutStatus.CREATED, CheckoutStatus.QUOTED}

    def requires_reapproval(self) -> bool:
        """Check if price change would require re-approval.

        Returns:
            True if in state that needs re-approval on price change.
        """
        return self in {CheckoutStatus.AWAITING_APPROVAL, CheckoutStatus.APPROVED}


# Checkout state transitions
_CHECKOUT_TRANSITIONS: dict[CheckoutStatus, set[CheckoutStatus]] = {
    CheckoutStatus.CREATED: {CheckoutStatus.QUOTED, CheckoutStatus.CANCELLED},
    CheckoutStatus.QUOTED: {
        CheckoutStatus.AWAITING_APPROVAL,
        CheckoutStatus.CANCELLED,
    },
    CheckoutStatus.AWAITING_APPROVAL: {
        CheckoutStatus.APPROVED,
        CheckoutStatus.QUOTED,  # price changed - back to quoted
        CheckoutStatus.CANCELLED,
    },
    CheckoutStatus.APPROVED: {
        CheckoutStatus.CONFIRMED,
        CheckoutStatus.FAILED,
        CheckoutStatus.QUOTED,  # price changed - back to quoted
        CheckoutStatus.CANCELLED,
    },
    CheckoutStatus.CONFIRMED: set(),  # Terminal state
    CheckoutStatus.FAILED: set(),  # Terminal state
    CheckoutStatus.CANCELLED: set(),  # Terminal state
}


# ============================================================================
# State Transition Result
# ============================================================================


@dataclass(frozen=True)
class StateTransition(Generic[S]):
    """Represents a state transition result.

    Attributes:
        from_state: Previous state.
        to_state: New state.
        success: Whether transition was successful.
        error: Error message if transition failed.
    """

    from_state: S
    to_state: S
    success: bool = True
    error: str | None = None

    @classmethod
    def successful(cls, from_state: S, to_state: S) -> "StateTransition[S]":
        """Create a successful transition.

        Args:
            from_state: Previous state.
            to_state: New state.

        Returns:
            Successful StateTransition.
        """
        return cls(from_state=from_state, to_state=to_state, success=True)

    @classmethod
    def failed(cls, from_state: S, to_state: S, error: str) -> "StateTransition[S]":
        """Create a failed transition.

        Args:
            from_state: Previous state.
            to_state: Attempted target state.
            error: Error message.

        Returns:
            Failed StateTransition.
        """
        return cls(from_state=from_state, to_state=to_state, success=False, error=error)


# ============================================================================
# State Machine Helpers
# ============================================================================


def validate_cart_transition(
    cart_id: str,
    current_status: CartStatus,
    target_status: CartStatus,
) -> None:
    """Validate and raise if cart state transition is invalid.

    Args:
        cart_id: Cart identifier for error message.
        current_status: Current cart status.
        target_status: Target cart status.

    Raises:
        InvalidStateTransitionError: If transition is not valid.
    """
    if not current_status.can_transition_to(target_status):
        raise InvalidStateTransitionError(
            entity_type="Cart",
            entity_id=cart_id,
            current_state=current_status.value,
            target_state=target_status.value,
            allowed_transitions=[s.value for s in current_status.allowed_transitions()],
        )


def validate_order_transition(
    order_id: str,
    current_status: OrderStatus,
    target_status: OrderStatus,
) -> None:
    """Validate and raise if order state transition is invalid.

    Args:
        order_id: Order identifier for error message.
        current_status: Current order status.
        target_status: Target order status.

    Raises:
        InvalidStateTransitionError: If transition is not valid.
    """
    if not current_status.can_transition_to(target_status):
        raise InvalidStateTransitionError(
            entity_type="Order",
            entity_id=order_id,
            current_state=current_status.value,
            target_state=target_status.value,
            allowed_transitions=[s.value for s in current_status.allowed_transitions()],
        )


def validate_approval_transition(
    approval_id: str,
    current_status: ApprovalStatus,
    target_status: ApprovalStatus,
) -> None:
    """Validate and raise if approval state transition is invalid.

    Args:
        approval_id: Approval identifier for error message.
        current_status: Current approval status.
        target_status: Target approval status.

    Raises:
        InvalidStateTransitionError: If transition is not valid.
    """
    if not current_status.can_transition_to(target_status):
        raise InvalidStateTransitionError(
            entity_type="Approval",
            entity_id=approval_id,
            current_state=current_status.value,
            target_state=target_status.value,
            allowed_transitions=[s.value for s in current_status.allowed_transitions()],
        )


def validate_checkout_transition(
    checkout_id: str,
    current_status: CheckoutStatus,
    target_status: CheckoutStatus,
) -> None:
    """Validate and raise if checkout state transition is invalid.

    Args:
        checkout_id: Checkout identifier for error message.
        current_status: Current checkout status.
        target_status: Target checkout status.

    Raises:
        InvalidStateTransitionError: If transition is not valid.
    """
    if not current_status.can_transition_to(target_status):
        raise InvalidStateTransitionError(
            entity_type="Checkout",
            entity_id=checkout_id,
            current_state=current_status.value,
            target_state=target_status.value,
            allowed_transitions=[s.value for s in current_status.allowed_transitions()],
        )
