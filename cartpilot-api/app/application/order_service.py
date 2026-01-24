"""Order application service.

Orchestrates order lifecycle management including:
- Creating orders from confirmed checkouts
- Tracking order status transitions
- Handling order events from merchants
- Supporting simulate_time for testing
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import structlog

from app.domain.state_machines import OrderStatus

logger = structlog.get_logger()


# ============================================================================
# Order Data Transfer Objects
# ============================================================================


@dataclass
class OrderItemDTO:
    """Order item data transfer object."""

    product_id: str
    title: str
    quantity: int
    unit_price_cents: int
    currency: str = "USD"
    variant_id: str | None = None
    sku: str | None = None

    @property
    def line_total_cents(self) -> int:
        """Calculate line total."""
        return self.unit_price_cents * self.quantity


@dataclass
class AddressDTO:
    """Address data transfer object."""

    line1: str
    city: str
    postal_code: str
    country: str
    line2: str | None = None
    state: str | None = None


@dataclass
class CustomerDTO:
    """Customer data transfer object."""

    email: str
    name: str | None = None
    phone: str | None = None


@dataclass
class OrderDTO:
    """Order data transfer object."""

    id: str
    checkout_id: str
    merchant_id: str
    status: OrderStatus
    customer: CustomerDTO
    shipping_address: AddressDTO
    billing_address: AddressDTO | None
    items: list[OrderItemDTO]
    subtotal_cents: int
    tax_cents: int
    shipping_cents: int
    total_cents: int
    currency: str
    merchant_order_id: str | None = None
    tracking_number: str | None = None
    carrier: str | None = None
    cancelled_reason: str | None = None
    cancelled_by: str | None = None
    refund_amount_cents: int | None = None
    refund_reason: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    confirmed_at: datetime | None = None
    shipped_at: datetime | None = None
    delivered_at: datetime | None = None
    cancelled_at: datetime | None = None
    refunded_at: datetime | None = None
    status_history: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class StatusHistoryEntry:
    """Status history entry."""

    from_status: str | None
    to_status: str
    reason: str | None = None
    actor: str | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================================
# Service Result Types
# ============================================================================


@dataclass
class CreateOrderResult:
    """Result of creating an order."""

    order: OrderDTO | None = None
    success: bool = True
    error: str | None = None
    error_code: str | None = None


@dataclass
class GetOrderResult:
    """Result of getting an order."""

    order: OrderDTO | None = None
    success: bool = True
    error: str | None = None
    error_code: str | None = None


@dataclass
class UpdateOrderResult:
    """Result of updating an order."""

    order: OrderDTO | None = None
    success: bool = True
    error: str | None = None
    error_code: str | None = None


@dataclass
class ListOrdersResult:
    """Result of listing orders."""

    orders: list[OrderDTO] = field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    success: bool = True
    error: str | None = None


# ============================================================================
# In-Memory Order Repository
# ============================================================================


class OrderRepository:
    """In-memory repository for orders.

    In production, this would be replaced with database persistence.
    """

    def __init__(self) -> None:
        self._orders: dict[str, OrderDTO] = {}
        self._by_checkout_id: dict[str, str] = {}
        self._by_merchant_order_id: dict[str, str] = {}

    def save(self, order: OrderDTO) -> None:
        """Save an order."""
        self._orders[order.id] = order
        self._by_checkout_id[order.checkout_id] = order.id
        if order.merchant_order_id:
            key = f"{order.merchant_id}:{order.merchant_order_id}"
            self._by_merchant_order_id[key] = order.id

    def get(self, order_id: str) -> OrderDTO | None:
        """Get order by ID."""
        return self._orders.get(order_id)

    def get_by_checkout_id(self, checkout_id: str) -> OrderDTO | None:
        """Get order by checkout ID."""
        order_id = self._by_checkout_id.get(checkout_id)
        if order_id:
            return self._orders.get(order_id)
        return None

    def get_by_merchant_order_id(
        self, merchant_id: str, merchant_order_id: str
    ) -> OrderDTO | None:
        """Get order by merchant order ID."""
        key = f"{merchant_id}:{merchant_order_id}"
        order_id = self._by_merchant_order_id.get(key)
        if order_id:
            return self._orders.get(order_id)
        return None

    def list_all(
        self,
        page: int = 1,
        page_size: int = 20,
        status: OrderStatus | None = None,
        merchant_id: str | None = None,
    ) -> tuple[list[OrderDTO], int]:
        """List orders with pagination and filtering."""
        orders = list(self._orders.values())

        # Apply filters
        if status:
            orders = [o for o in orders if o.status == status]
        if merchant_id:
            orders = [o for o in orders if o.merchant_id == merchant_id]

        # Sort by created_at descending
        orders.sort(key=lambda o: o.created_at, reverse=True)

        total = len(orders)
        start = (page - 1) * page_size
        end = start + page_size
        return orders[start:end], total


# Global repository instance
_order_repo: OrderRepository | None = None


def get_order_repository() -> OrderRepository:
    """Get order repository singleton."""
    global _order_repo
    if _order_repo is None:
        _order_repo = OrderRepository()
    return _order_repo


def reset_order_repository() -> None:
    """Reset order repository (for testing)."""
    global _order_repo
    _order_repo = OrderRepository()


# ============================================================================
# Order Service
# ============================================================================


class OrderService:
    """Application service for managing orders.

    Handles order lifecycle:
    - Create order from confirmed checkout
    - Track status transitions
    - Handle merchant webhooks
    - Support simulate_time for testing
    """

    def __init__(
        self,
        order_repo: OrderRepository | None = None,
        request_id: str | None = None,
    ) -> None:
        """Initialize service.

        Args:
            order_repo: Order repository.
            request_id: Request ID for correlation.
        """
        self.order_repo = order_repo or get_order_repository()
        self.request_id = request_id

    async def create_order_from_checkout(
        self,
        checkout_id: str,
        merchant_id: str,
        merchant_order_id: str,
        customer: CustomerDTO,
        shipping_address: AddressDTO,
        billing_address: AddressDTO | None,
        items: list[OrderItemDTO],
        subtotal_cents: int,
        tax_cents: int,
        shipping_cents: int,
        total_cents: int,
        currency: str = "USD",
    ) -> CreateOrderResult:
        """Create an order from a confirmed checkout.

        Args:
            checkout_id: Source checkout ID.
            merchant_id: Merchant fulfilling the order.
            merchant_order_id: Merchant's order reference.
            customer: Customer information.
            shipping_address: Shipping address.
            billing_address: Billing address.
            items: Order items.
            subtotal_cents: Subtotal in cents.
            tax_cents: Tax in cents.
            shipping_cents: Shipping in cents.
            total_cents: Total in cents.
            currency: Currency code.

        Returns:
            CreateOrderResult with the created order.
        """
        try:
            # Check if order already exists for this checkout (idempotent)
            existing = self.order_repo.get_by_checkout_id(checkout_id)
            if existing:
                logger.info(
                    "Order already exists for checkout",
                    checkout_id=checkout_id,
                    order_id=existing.id,
                )
                return CreateOrderResult(order=existing)

            order_id = str(uuid4())
            now = datetime.now(timezone.utc)

            order = OrderDTO(
                id=order_id,
                checkout_id=checkout_id,
                merchant_id=merchant_id,
                merchant_order_id=merchant_order_id,
                status=OrderStatus.PENDING,
                customer=customer,
                shipping_address=shipping_address,
                billing_address=billing_address,
                items=items,
                subtotal_cents=subtotal_cents,
                tax_cents=tax_cents,
                shipping_cents=shipping_cents,
                total_cents=total_cents,
                currency=currency,
                created_at=now,
                updated_at=now,
                status_history=[
                    {
                        "from_status": None,
                        "to_status": OrderStatus.PENDING.value,
                        "reason": "Order created from checkout",
                        "actor": "system",
                        "created_at": now.isoformat(),
                    }
                ],
            )

            self.order_repo.save(order)

            logger.info(
                "Order created",
                order_id=order_id,
                checkout_id=checkout_id,
                merchant_order_id=merchant_order_id,
                total_cents=total_cents,
                request_id=self.request_id,
            )

            return CreateOrderResult(order=order)

        except Exception as e:
            logger.error(
                "Failed to create order",
                checkout_id=checkout_id,
                error=str(e),
                request_id=self.request_id,
            )
            return CreateOrderResult(
                success=False,
                error=str(e),
                error_code="CREATE_FAILED",
            )

    async def get_order(self, order_id: str) -> GetOrderResult:
        """Get an order by ID.

        Args:
            order_id: Order identifier.

        Returns:
            GetOrderResult with the order if found.
        """
        order = self.order_repo.get(order_id)
        if not order:
            return GetOrderResult(
                success=False,
                error=f"Order not found: {order_id}",
                error_code="ORDER_NOT_FOUND",
            )
        return GetOrderResult(order=order)

    async def get_order_by_merchant_order_id(
        self, merchant_id: str, merchant_order_id: str
    ) -> GetOrderResult:
        """Get an order by merchant order ID.

        Args:
            merchant_id: Merchant identifier.
            merchant_order_id: Merchant's order ID.

        Returns:
            GetOrderResult with the order if found.
        """
        order = self.order_repo.get_by_merchant_order_id(merchant_id, merchant_order_id)
        if not order:
            return GetOrderResult(
                success=False,
                error=f"Order not found for merchant order: {merchant_order_id}",
                error_code="ORDER_NOT_FOUND",
            )
        return GetOrderResult(order=order)

    async def list_orders(
        self,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        merchant_id: str | None = None,
    ) -> ListOrdersResult:
        """List orders with pagination and filtering.

        Args:
            page: Page number (1-based).
            page_size: Items per page.
            status: Filter by status.
            merchant_id: Filter by merchant.

        Returns:
            ListOrdersResult with paginated orders.
        """
        try:
            status_enum = OrderStatus(status) if status else None
        except ValueError:
            status_enum = None

        orders, total = self.order_repo.list_all(
            page=page,
            page_size=page_size,
            status=status_enum,
            merchant_id=merchant_id,
        )

        return ListOrdersResult(
            orders=orders,
            total=total,
            page=page,
            page_size=page_size,
        )

    async def confirm_order(
        self,
        order_id: str,
        merchant_order_id: str | None = None,
        actor: str = "merchant",
    ) -> UpdateOrderResult:
        """Confirm an order (transition from pending to confirmed).

        Args:
            order_id: Order identifier.
            merchant_order_id: Updated merchant order ID if changed.
            actor: Who initiated the transition.

        Returns:
            UpdateOrderResult with the updated order.
        """
        return await self._transition_order(
            order_id=order_id,
            target_status=OrderStatus.CONFIRMED,
            actor=actor,
            metadata={"merchant_order_id": merchant_order_id} if merchant_order_id else None,
            update_fn=lambda o: setattr(o, "confirmed_at", datetime.now(timezone.utc)),
        )

    async def ship_order(
        self,
        order_id: str,
        tracking_number: str | None = None,
        carrier: str | None = None,
        actor: str = "merchant",
    ) -> UpdateOrderResult:
        """Mark order as shipped.

        Args:
            order_id: Order identifier.
            tracking_number: Shipment tracking number.
            carrier: Shipping carrier name.
            actor: Who initiated the transition.

        Returns:
            UpdateOrderResult with the updated order.
        """
        def update_shipping(order: OrderDTO) -> None:
            order.tracking_number = tracking_number
            order.carrier = carrier
            order.shipped_at = datetime.now(timezone.utc)

        return await self._transition_order(
            order_id=order_id,
            target_status=OrderStatus.SHIPPED,
            actor=actor,
            metadata={
                "tracking_number": tracking_number,
                "carrier": carrier,
            },
            update_fn=update_shipping,
        )

    async def deliver_order(
        self,
        order_id: str,
        actor: str = "merchant",
    ) -> UpdateOrderResult:
        """Mark order as delivered.

        Args:
            order_id: Order identifier.
            actor: Who initiated the transition.

        Returns:
            UpdateOrderResult with the updated order.
        """
        return await self._transition_order(
            order_id=order_id,
            target_status=OrderStatus.DELIVERED,
            actor=actor,
            update_fn=lambda o: setattr(o, "delivered_at", datetime.now(timezone.utc)),
        )

    async def cancel_order(
        self,
        order_id: str,
        reason: str,
        cancelled_by: str = "customer",
    ) -> UpdateOrderResult:
        """Cancel an order.

        Args:
            order_id: Order identifier.
            reason: Cancellation reason.
            cancelled_by: Who cancelled (customer/merchant/system).

        Returns:
            UpdateOrderResult with the updated order.
        """
        def update_cancellation(order: OrderDTO) -> None:
            order.cancelled_reason = reason
            order.cancelled_by = cancelled_by
            order.cancelled_at = datetime.now(timezone.utc)

        return await self._transition_order(
            order_id=order_id,
            target_status=OrderStatus.CANCELLED,
            actor=cancelled_by,
            reason=reason,
            update_fn=update_cancellation,
        )

    async def refund_order(
        self,
        order_id: str,
        refund_amount_cents: int | None = None,
        reason: str = "",
        actor: str = "system",
    ) -> UpdateOrderResult:
        """Refund an order.

        Args:
            order_id: Order identifier.
            refund_amount_cents: Refund amount (None for full refund).
            reason: Refund reason.
            actor: Who initiated the refund.

        Returns:
            UpdateOrderResult with the updated order.
        """
        order = self.order_repo.get(order_id)
        if not order:
            return UpdateOrderResult(
                success=False,
                error=f"Order not found: {order_id}",
                error_code="ORDER_NOT_FOUND",
            )

        amount = refund_amount_cents if refund_amount_cents is not None else order.total_cents

        def update_refund(o: OrderDTO) -> None:
            o.refund_amount_cents = amount
            o.refund_reason = reason
            o.refunded_at = datetime.now(timezone.utc)

        return await self._transition_order(
            order_id=order_id,
            target_status=OrderStatus.REFUNDED,
            actor=actor,
            reason=reason,
            metadata={"refund_amount_cents": amount},
            update_fn=update_refund,
        )

    async def simulate_advance_order(
        self,
        order_id: str,
        steps: int = 1,
    ) -> UpdateOrderResult:
        """Advance order through lifecycle for testing.

        Simulates order progression:
        - pending → confirmed → shipped → delivered

        Args:
            order_id: Order identifier.
            steps: Number of steps to advance.

        Returns:
            UpdateOrderResult with the updated order.
        """
        order = self.order_repo.get(order_id)
        if not order:
            return UpdateOrderResult(
                success=False,
                error=f"Order not found: {order_id}",
                error_code="ORDER_NOT_FOUND",
            )

        progression = [
            (OrderStatus.PENDING, OrderStatus.CONFIRMED, self.confirm_order),
            (OrderStatus.CONFIRMED, OrderStatus.SHIPPED, self._ship_simulated),
            (OrderStatus.SHIPPED, OrderStatus.DELIVERED, self.deliver_order),
        ]

        result = UpdateOrderResult(order=order)

        for _ in range(steps):
            current_status = result.order.status if result.order else None
            advanced = False

            for from_status, to_status, handler in progression:
                if current_status == from_status:
                    if handler == self._ship_simulated:
                        result = await handler(order_id)
                    else:
                        result = await handler(order_id, actor="simulate_time")
                    if not result.success:
                        return result
                    advanced = True
                    break

            if not advanced:
                # No more transitions available
                break

        return result

    async def _ship_simulated(self, order_id: str) -> UpdateOrderResult:
        """Ship order with simulated tracking info."""
        return await self.ship_order(
            order_id=order_id,
            tracking_number=f"SIM{uuid4().hex[:8].upper()}",
            carrier="SimCarrier",
            actor="simulate_time",
        )

    async def _transition_order(
        self,
        order_id: str,
        target_status: OrderStatus,
        actor: str,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
        update_fn: Any = None,
    ) -> UpdateOrderResult:
        """Perform a status transition on an order.

        Args:
            order_id: Order identifier.
            target_status: Target status.
            actor: Who initiated the transition.
            reason: Reason for transition.
            metadata: Additional metadata.
            update_fn: Function to update order fields.

        Returns:
            UpdateOrderResult with the updated order.
        """
        order = self.order_repo.get(order_id)
        if not order:
            return UpdateOrderResult(
                success=False,
                error=f"Order not found: {order_id}",
                error_code="ORDER_NOT_FOUND",
            )

        # Validate transition
        if not order.status.can_transition_to(target_status):
            return UpdateOrderResult(
                success=False,
                error=f"Cannot transition from {order.status.value} to {target_status.value}",
                error_code="INVALID_TRANSITION",
            )

        from_status = order.status
        now = datetime.now(timezone.utc)

        # Apply custom updates
        if update_fn:
            update_fn(order)

        # Update status
        order.status = target_status
        order.updated_at = now

        # Add to status history
        history_entry = {
            "from_status": from_status.value,
            "to_status": target_status.value,
            "reason": reason,
            "actor": actor,
            "metadata": metadata,
            "created_at": now.isoformat(),
        }
        order.status_history.append(history_entry)

        self.order_repo.save(order)

        logger.info(
            "Order status transitioned",
            order_id=order_id,
            from_status=from_status.value,
            to_status=target_status.value,
            actor=actor,
            request_id=self.request_id,
        )

        return UpdateOrderResult(order=order)


# ============================================================================
# Service Factory
# ============================================================================


def get_order_service(request_id: str | None = None) -> OrderService:
    """Get order service instance.

    Args:
        request_id: Request ID for correlation.

    Returns:
        OrderService instance.
    """
    return OrderService(request_id=request_id)
