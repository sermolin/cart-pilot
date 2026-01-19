"""Domain exceptions.

All domain-level errors that represent business rule violations.
These exceptions are raised by entities and state machines when
invariants are violated or invalid operations are attempted.
"""

from typing import Any


class DomainError(Exception):
    """Base class for all domain exceptions.

    All domain errors should inherit from this class to allow
    catching domain-specific errors at the application layer.
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Initialize domain error.

        Args:
            message: Human-readable error message.
            details: Optional dictionary with additional error context.
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}


# ============================================================================
# State Machine Errors
# ============================================================================


class InvalidStateTransitionError(DomainError):
    """Raised when an invalid state transition is attempted.

    This error indicates that the requested operation cannot be performed
    in the current state of the entity.
    """

    def __init__(
        self,
        entity_type: str,
        entity_id: str,
        current_state: str,
        target_state: str,
        allowed_transitions: list[str] | None = None,
    ) -> None:
        """Initialize invalid state transition error.

        Args:
            entity_type: Type of entity (e.g., "Cart", "Order").
            entity_id: ID of the entity.
            current_state: Current state of the entity.
            target_state: Attempted target state.
            allowed_transitions: List of allowed target states from current state.
        """
        allowed = allowed_transitions or []
        message = (
            f"Cannot transition {entity_type}({entity_id}) "
            f"from '{current_state}' to '{target_state}'. "
            f"Allowed transitions: {allowed}"
        )
        super().__init__(
            message,
            details={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "current_state": current_state,
                "target_state": target_state,
                "allowed_transitions": allowed,
            },
        )


# ============================================================================
# Cart Errors
# ============================================================================


class CartError(DomainError):
    """Base class for cart-related errors."""

    pass


class CartNotEditableError(CartError):
    """Raised when trying to modify a cart that is not in editable state."""

    def __init__(self, cart_id: str, current_status: str) -> None:
        """Initialize cart not editable error.

        Args:
            cart_id: ID of the cart.
            current_status: Current status of the cart.
        """
        super().__init__(
            f"Cart {cart_id} is not editable in status '{current_status}'",
            details={"cart_id": cart_id, "current_status": current_status},
        )


class CartItemNotFoundError(CartError):
    """Raised when a cart item is not found."""

    def __init__(self, cart_id: str, item_id: str) -> None:
        """Initialize cart item not found error.

        Args:
            cart_id: ID of the cart.
            item_id: ID of the item.
        """
        super().__init__(
            f"Item {item_id} not found in cart {cart_id}",
            details={"cart_id": cart_id, "item_id": item_id},
        )


class CartEmptyError(CartError):
    """Raised when trying to checkout an empty cart."""

    def __init__(self, cart_id: str) -> None:
        """Initialize cart empty error.

        Args:
            cart_id: ID of the cart.
        """
        super().__init__(
            f"Cannot checkout empty cart {cart_id}",
            details={"cart_id": cart_id},
        )


class InvalidQuantityError(CartError):
    """Raised when an invalid quantity is provided."""

    def __init__(self, quantity: int, reason: str = "Quantity must be positive") -> None:
        """Initialize invalid quantity error.

        Args:
            quantity: The invalid quantity value.
            reason: Explanation of why the quantity is invalid.
        """
        super().__init__(
            f"Invalid quantity {quantity}: {reason}",
            details={"quantity": quantity, "reason": reason},
        )


# ============================================================================
# Order Errors
# ============================================================================


class OrderError(DomainError):
    """Base class for order-related errors."""

    pass


class OrderNotCancellableError(OrderError):
    """Raised when trying to cancel an order that cannot be cancelled."""

    def __init__(self, order_id: str, current_status: str) -> None:
        """Initialize order not cancellable error.

        Args:
            order_id: ID of the order.
            current_status: Current status of the order.
        """
        super().__init__(
            f"Order {order_id} cannot be cancelled in status '{current_status}'",
            details={"order_id": order_id, "current_status": current_status},
        )


# ============================================================================
# Approval Errors
# ============================================================================


class ApprovalError(DomainError):
    """Base class for approval-related errors."""

    pass


class ApprovalExpiredError(ApprovalError):
    """Raised when trying to act on an expired approval."""

    def __init__(self, approval_id: str) -> None:
        """Initialize approval expired error.

        Args:
            approval_id: ID of the approval.
        """
        super().__init__(
            f"Approval {approval_id} has expired",
            details={"approval_id": approval_id},
        )


class ApprovalAlreadyResolvedError(ApprovalError):
    """Raised when trying to resolve an already resolved approval."""

    def __init__(self, approval_id: str, current_status: str) -> None:
        """Initialize approval already resolved error.

        Args:
            approval_id: ID of the approval.
            current_status: Current status of the approval.
        """
        super().__init__(
            f"Approval {approval_id} is already resolved with status '{current_status}'",
            details={"approval_id": approval_id, "current_status": current_status},
        )


# ============================================================================
# Money Errors
# ============================================================================


class MoneyError(DomainError):
    """Base class for money-related errors."""

    pass


class CurrencyMismatchError(MoneyError):
    """Raised when attempting to combine money with different currencies."""

    def __init__(self, currency1: str, currency2: str) -> None:
        """Initialize currency mismatch error.

        Args:
            currency1: First currency code.
            currency2: Second currency code.
        """
        super().__init__(
            f"Cannot combine money with different currencies: {currency1} and {currency2}",
            details={"currency1": currency1, "currency2": currency2},
        )


class NegativeMoneyError(MoneyError):
    """Raised when attempting to create money with negative amount."""

    def __init__(self, amount: int) -> None:
        """Initialize negative money error.

        Args:
            amount: The negative amount in cents.
        """
        super().__init__(
            f"Money amount cannot be negative: {amount}",
            details={"amount": amount},
        )
