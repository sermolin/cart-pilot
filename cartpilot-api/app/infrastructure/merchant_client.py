"""Merchant HTTP client for communicating with merchant APIs.

Provides discovery and unified interface for calling merchant endpoints.
"""

from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from app.infrastructure.config import settings

logger = structlog.get_logger()


# ============================================================================
# Merchant Configuration
# ============================================================================


@dataclass
class MerchantConfig:
    """Configuration for a merchant."""

    id: str
    url: str
    enabled: bool
    name: str | None = None

    @property
    def display_name(self) -> str:
        """Get display name for merchant."""
        return self.name or self.id.replace("-", " ").title()


class MerchantRegistry:
    """Registry of available merchants.

    Discovers merchants from environment configuration and provides
    lookup functionality.
    """

    def __init__(self) -> None:
        """Initialize registry with merchants from settings."""
        self._merchants: dict[str, MerchantConfig] = {}
        self._discover_merchants()

    def _discover_merchants(self) -> None:
        """Discover merchants from environment settings."""
        # Merchant A
        if settings.merchant_a_enabled:
            self._merchants[settings.merchant_a_id] = MerchantConfig(
                id=settings.merchant_a_id,
                url=settings.merchant_a_url,
                enabled=True,
                name="Merchant A",
            )
            logger.info(
                "Discovered merchant",
                merchant_id=settings.merchant_a_id,
                url=settings.merchant_a_url,
            )

        # Merchant B
        if settings.merchant_b_enabled:
            self._merchants[settings.merchant_b_id] = MerchantConfig(
                id=settings.merchant_b_id,
                url=settings.merchant_b_url,
                enabled=True,
                name="Merchant B",
            )
            logger.info(
                "Discovered merchant",
                merchant_id=settings.merchant_b_id,
                url=settings.merchant_b_url,
            )

    def get_merchant(self, merchant_id: str) -> MerchantConfig | None:
        """Get merchant by ID.

        Args:
            merchant_id: Merchant identifier.

        Returns:
            MerchantConfig if found and enabled, None otherwise.
        """
        merchant = self._merchants.get(merchant_id)
        if merchant and merchant.enabled:
            return merchant
        return None

    def list_merchants(self) -> list[MerchantConfig]:
        """List all enabled merchants.

        Returns:
            List of enabled merchant configurations.
        """
        return [m for m in self._merchants.values() if m.enabled]

    def get_enabled_merchant_ids(self) -> list[str]:
        """Get list of enabled merchant IDs.

        Returns:
            List of merchant IDs.
        """
        return [m.id for m in self._merchants.values() if m.enabled]


# Global registry instance
_merchant_registry: MerchantRegistry | None = None


def get_merchant_registry() -> MerchantRegistry:
    """Get the merchant registry singleton.

    Returns:
        MerchantRegistry instance.
    """
    global _merchant_registry
    if _merchant_registry is None:
        _merchant_registry = MerchantRegistry()
    return _merchant_registry


# ============================================================================
# Merchant HTTP Client
# ============================================================================


@dataclass
class MerchantProduct:
    """Product data from a merchant."""

    id: str
    sku: str | None
    title: str
    description: str | None
    brand: str | None
    category_id: int | None
    category_path: str | None
    price_cents: int
    currency: str
    rating: float | None
    review_count: int | None
    image_url: str | None
    in_stock: bool
    stock_quantity: int
    variants: list[dict[str, Any]]

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "MerchantProduct":
        """Create from merchant API response.

        Args:
            data: API response data.

        Returns:
            MerchantProduct instance.
        """
        price_data = data.get("price", {})
        return cls(
            id=data["id"],
            sku=data.get("sku"),
            title=data["title"],
            description=data.get("description"),
            brand=data.get("brand"),
            category_id=data.get("category_id"),
            category_path=data.get("category_path"),
            price_cents=price_data.get("amount", 0),
            currency=price_data.get("currency", "USD"),
            rating=data.get("rating"),
            review_count=data.get("review_count"),
            image_url=data.get("image_url"),
            in_stock=data.get("in_stock", True),
            stock_quantity=data.get("stock_quantity", 0),
            variants=data.get("variants", []),
        )


@dataclass
class MerchantProductList:
    """List of products from a merchant."""

    items: list[MerchantProduct]
    total: int
    page: int
    page_size: int
    has_more: bool


class MerchantClientError(Exception):
    """Error from merchant API call."""

    def __init__(
        self, merchant_id: str, message: str, status_code: int | None = None
    ) -> None:
        self.merchant_id = merchant_id
        self.message = message
        self.status_code = status_code
        super().__init__(f"[{merchant_id}] {message}")


@dataclass
class MerchantQuoteItem:
    """Item in a merchant quote."""

    product_id: str
    variant_id: str | None
    sku: str
    title: str
    unit_price_cents: int
    quantity: int
    line_total_cents: int
    currency: str

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "MerchantQuoteItem":
        """Create from API response data."""
        unit_price = data.get("unit_price", {})
        line_total = data.get("line_total", {})
        return cls(
            product_id=data["product_id"],
            variant_id=data.get("variant_id"),
            sku=data.get("sku", ""),
            title=data.get("title", ""),
            unit_price_cents=unit_price.get("amount", 0),
            quantity=data.get("quantity", 1),
            line_total_cents=line_total.get("amount", 0),
            currency=unit_price.get("currency", "USD"),
        )


@dataclass
class MerchantQuoteResponse:
    """Quote response from a merchant."""

    checkout_id: str
    status: str
    items: list[MerchantQuoteItem]
    subtotal_cents: int
    tax_cents: int
    shipping_cents: int
    total_cents: int
    currency: str
    receipt_hash: str | None
    expires_at: str | None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "MerchantQuoteResponse":
        """Create from API response data."""
        subtotal = data.get("subtotal", {})
        tax = data.get("tax", {})
        shipping = data.get("shipping", {})
        total = data.get("total", {})

        return cls(
            checkout_id=data["id"],
            status=data.get("status", "unknown"),
            items=[MerchantQuoteItem.from_api_response(i) for i in data.get("items", [])],
            subtotal_cents=subtotal.get("amount", 0),
            tax_cents=tax.get("amount", 0),
            shipping_cents=shipping.get("amount", 0),
            total_cents=total.get("amount", 0),
            currency=total.get("currency", "USD"),
            receipt_hash=data.get("receipt_hash"),
            expires_at=data.get("expires_at"),
        )


@dataclass
class MerchantConfirmResponse:
    """Confirmation response from a merchant."""

    checkout_id: str
    merchant_order_id: str
    status: str
    total_cents: int
    currency: str
    confirmed_at: str

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "MerchantConfirmResponse":
        """Create from API response data."""
        total = data.get("total", {})
        return cls(
            checkout_id=data.get("checkout_id", ""),
            merchant_order_id=data.get("merchant_order_id", ""),
            status=data.get("status", "unknown"),
            total_cents=total.get("amount", 0),
            currency=total.get("currency", "USD"),
            confirmed_at=data.get("confirmed_at", ""),
        )


class MerchantClient:
    """HTTP client for communicating with a single merchant.

    Provides methods for calling merchant API endpoints with
    error handling and response normalization.
    """

    def __init__(
        self,
        merchant: MerchantConfig,
        timeout: float = 10.0,
        request_id: str | None = None,
    ) -> None:
        """Initialize merchant client.

        Args:
            merchant: Merchant configuration.
            timeout: Request timeout in seconds.
            request_id: Optional request ID for correlation.
        """
        self.merchant = merchant
        self.timeout = timeout
        self.request_id = request_id
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            headers = {}
            if self.request_id:
                headers["X-Request-ID"] = self.request_id
            self._client = httpx.AsyncClient(
                base_url=self.merchant.url,
                timeout=self.timeout,
                headers=headers,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> bool:
        """Check merchant health.

        Returns:
            True if merchant is healthy.
        """
        try:
            client = await self._get_client()
            response = await client.get("/health")
            return response.status_code == 200
        except Exception as e:
            logger.warning(
                "Merchant health check failed",
                merchant_id=self.merchant.id,
                error=str(e),
            )
            return False

    async def list_products(
        self,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        category_id: int | None = None,
        brand: str | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        in_stock: bool | None = None,
        sort_by: str | None = None,
        sort_order: str = "asc",
    ) -> MerchantProductList:
        """List products from merchant.

        Args:
            page: Page number.
            page_size: Items per page.
            search: Search query.
            category_id: Category filter.
            brand: Brand filter.
            min_price: Minimum price in cents.
            max_price: Maximum price in cents.
            in_stock: Stock availability filter.
            sort_by: Sort field.
            sort_order: Sort order.

        Returns:
            List of products.

        Raises:
            MerchantClientError: On API error.
        """
        try:
            client = await self._get_client()

            params: dict[str, Any] = {
                "page": page,
                "page_size": page_size,
            }
            if search:
                params["search"] = search
            if category_id is not None:
                params["category_id"] = category_id
            if brand:
                params["brand"] = brand
            if min_price is not None:
                params["min_price"] = min_price
            if max_price is not None:
                params["max_price"] = max_price
            if in_stock is not None:
                params["in_stock"] = in_stock
            if sort_by:
                params["sort_by"] = sort_by
                params["sort_order"] = sort_order

            response = await client.get("/products", params=params)

            if response.status_code != 200:
                raise MerchantClientError(
                    self.merchant.id,
                    f"Failed to list products: {response.text}",
                    response.status_code,
                )

            data = response.json()
            items = [MerchantProduct.from_api_response(p) for p in data.get("items", [])]

            return MerchantProductList(
                items=items,
                total=data.get("total", 0),
                page=data.get("page", page),
                page_size=data.get("page_size", page_size),
                has_more=data.get("has_more", False),
            )

        except httpx.RequestError as e:
            logger.error(
                "Merchant API request failed",
                merchant_id=self.merchant.id,
                error=str(e),
            )
            raise MerchantClientError(
                self.merchant.id, f"Request failed: {str(e)}"
            ) from e

    async def get_product(self, product_id: str) -> MerchantProduct | None:
        """Get product by ID.

        Args:
            product_id: Product identifier.

        Returns:
            Product if found, None otherwise.

        Raises:
            MerchantClientError: On API error (except 404).
        """
        try:
            client = await self._get_client()
            response = await client.get(f"/products/{product_id}")

            if response.status_code == 404:
                return None

            if response.status_code != 200:
                raise MerchantClientError(
                    self.merchant.id,
                    f"Failed to get product: {response.text}",
                    response.status_code,
                )

            return MerchantProduct.from_api_response(response.json())

        except httpx.RequestError as e:
            logger.error(
                "Merchant API request failed",
                merchant_id=self.merchant.id,
                product_id=product_id,
                error=str(e),
            )
            raise MerchantClientError(
                self.merchant.id, f"Request failed: {str(e)}"
            ) from e

    async def search_products(
        self, query: str, limit: int = 10
    ) -> list[MerchantProduct]:
        """Search products by query.

        Convenience method that wraps list_products with search.

        Args:
            query: Search query.
            limit: Maximum results.

        Returns:
            List of matching products.
        """
        result = await self.list_products(
            page=1,
            page_size=limit,
            search=query,
            in_stock=True,  # Only return in-stock items
        )
        return result.items

    async def create_quote(
        self,
        items: list[dict[str, Any]],
        customer_email: str | None = None,
        idempotency_key: str | None = None,
    ) -> "MerchantQuoteResponse":
        """Create a quote for items.

        Args:
            items: List of items with product_id, variant_id, quantity.
            customer_email: Optional customer email.
            idempotency_key: Idempotency key.

        Returns:
            Quote response from merchant.

        Raises:
            MerchantClientError: On API error.
        """
        try:
            client = await self._get_client()

            payload: dict[str, Any] = {
                "items": items,
            }
            if customer_email:
                payload["customer_email"] = customer_email
            if idempotency_key:
                payload["idempotency_key"] = idempotency_key

            response = await client.post("/checkout/quote", json=payload)

            if response.status_code not in (200, 201):
                raise MerchantClientError(
                    self.merchant.id,
                    f"Failed to create quote: {response.text}",
                    response.status_code,
                )

            return MerchantQuoteResponse.from_api_response(response.json())

        except httpx.RequestError as e:
            logger.error(
                "Merchant quote request failed",
                merchant_id=self.merchant.id,
                error=str(e),
            )
            raise MerchantClientError(
                self.merchant.id, f"Quote request failed: {str(e)}"
            ) from e

    async def confirm_checkout(
        self,
        checkout_id: str,
        payment_method: str = "test_card",
        idempotency_key: str | None = None,
    ) -> "MerchantConfirmResponse":
        """Confirm a checkout session.

        Args:
            checkout_id: Merchant's checkout session ID.
            payment_method: Payment method identifier.
            idempotency_key: Idempotency key.

        Returns:
            Confirmation response from merchant.

        Raises:
            MerchantClientError: On API error.
        """
        try:
            client = await self._get_client()

            payload: dict[str, Any] = {
                "payment_method": payment_method,
            }
            if idempotency_key:
                payload["idempotency_key"] = idempotency_key

            response = await client.post(
                f"/checkout/{checkout_id}/confirm", json=payload
            )

            if response.status_code == 404:
                raise MerchantClientError(
                    self.merchant.id,
                    f"Checkout not found: {checkout_id}",
                    404,
                )

            if response.status_code == 409:
                # Handle price changed or invalid state
                error_data = response.json()
                error_code = error_data.get("error_code", "CONFLICT")
                error_msg = error_data.get("message", "Checkout conflict")
                raise MerchantClientError(
                    self.merchant.id,
                    f"{error_code}: {error_msg}",
                    409,
                )

            if response.status_code not in (200, 201):
                raise MerchantClientError(
                    self.merchant.id,
                    f"Failed to confirm checkout: {response.text}",
                    response.status_code,
                )

            return MerchantConfirmResponse.from_api_response(response.json())

        except httpx.RequestError as e:
            logger.error(
                "Merchant confirm request failed",
                merchant_id=self.merchant.id,
                checkout_id=checkout_id,
                error=str(e),
            )
            raise MerchantClientError(
                self.merchant.id, f"Confirm request failed: {str(e)}"
            ) from e

    async def get_checkout(self, checkout_id: str) -> "MerchantQuoteResponse | None":
        """Get checkout session status.

        Args:
            checkout_id: Merchant's checkout session ID.

        Returns:
            Checkout response or None if not found.

        Raises:
            MerchantClientError: On API error (except 404).
        """
        try:
            client = await self._get_client()
            response = await client.get(f"/checkout/{checkout_id}")

            if response.status_code == 404:
                return None

            if response.status_code != 200:
                raise MerchantClientError(
                    self.merchant.id,
                    f"Failed to get checkout: {response.text}",
                    response.status_code,
                )

            return MerchantQuoteResponse.from_api_response(response.json())

        except httpx.RequestError as e:
            logger.error(
                "Merchant get checkout request failed",
                merchant_id=self.merchant.id,
                checkout_id=checkout_id,
                error=str(e),
            )
            raise MerchantClientError(
                self.merchant.id, f"Get checkout request failed: {str(e)}"
            ) from e


# ============================================================================
# Merchant Client Factory
# ============================================================================


class MerchantClientFactory:
    """Factory for creating merchant clients.

    Manages client lifecycle and provides convenient access
    to merchant APIs.
    """

    def __init__(
        self,
        registry: MerchantRegistry | None = None,
        request_id: str | None = None,
    ) -> None:
        """Initialize factory.

        Args:
            registry: Merchant registry (uses global if not provided).
            request_id: Request ID for correlation.
        """
        self.registry = registry or get_merchant_registry()
        self.request_id = request_id
        self._clients: dict[str, MerchantClient] = {}

    def get_client(self, merchant_id: str) -> MerchantClient | None:
        """Get client for a merchant.

        Args:
            merchant_id: Merchant identifier.

        Returns:
            MerchantClient if merchant exists and is enabled, None otherwise.
        """
        if merchant_id in self._clients:
            return self._clients[merchant_id]

        merchant = self.registry.get_merchant(merchant_id)
        if not merchant:
            return None

        client = MerchantClient(merchant, request_id=self.request_id)
        self._clients[merchant_id] = client
        return client

    def get_all_clients(self) -> list[MerchantClient]:
        """Get clients for all enabled merchants.

        Returns:
            List of merchant clients.
        """
        clients = []
        for merchant in self.registry.list_merchants():
            client = self.get_client(merchant.id)
            if client:
                clients.append(client)
        return clients

    async def close_all(self) -> None:
        """Close all clients."""
        for client in self._clients.values():
            await client.close()
        self._clients.clear()

    async def __aenter__(self) -> "MerchantClientFactory":
        """Context manager entry."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Context manager exit."""
        await self.close_all()
