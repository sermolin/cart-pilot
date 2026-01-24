"""CartPilot API Client.

Thin HTTP client for communicating with the CartPilot REST API.
This module handles authentication, error handling, and response parsing.
"""

from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()


@dataclass
class APIError:
    """Represents an API error response."""

    error_code: str
    message: str
    status_code: int
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class APIResponse:
    """Represents an API response."""

    success: bool
    data: dict[str, Any] | list[Any] | None = None
    error: APIError | None = None


class CartPilotAPIClient:
    """HTTP client for CartPilot REST API.

    Provides methods for all CartPilot API endpoints used by MCP tools.
    Handles authentication, request correlation, and error handling.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the API client.

        Args:
            base_url: CartPilot API base URL.
            api_key: API key for authentication.
            timeout: Request timeout in seconds.
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> APIResponse:
        """Make an API request.

        Args:
            method: HTTP method.
            path: API endpoint path.
            json: Request body as JSON.
            params: Query parameters.
            idempotency_key: Optional idempotency key.

        Returns:
            APIResponse with success status and data or error.
        """
        client = await self._get_client()

        headers = {}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        # Filter out None params
        if params:
            params = {k: v for k, v in params.items() if v is not None}

        try:
            logger.debug(
                "Making API request",
                method=method,
                path=path,
                has_body=json is not None,
            )

            response = await client.request(
                method=method,
                url=path,
                json=json,
                params=params,
                headers=headers,
            )

            if response.status_code >= 400:
                error_data = response.json()
                return APIResponse(
                    success=False,
                    error=APIError(
                        error_code=error_data.get("error_code", "UNKNOWN_ERROR"),
                        message=error_data.get("message", "Unknown error"),
                        status_code=response.status_code,
                        details=error_data.get("details", {}),
                    ),
                )

            # Handle empty responses (204 No Content)
            if response.status_code == 204:
                return APIResponse(success=True, data=None)

            return APIResponse(success=True, data=response.json())

        except httpx.TimeoutException as e:
            logger.error("API request timeout", path=path, error=str(e))
            return APIResponse(
                success=False,
                error=APIError(
                    error_code="TIMEOUT",
                    message=f"Request timed out: {path}",
                    status_code=504,
                ),
            )
        except httpx.RequestError as e:
            logger.error("API request failed", path=path, error=str(e))
            return APIResponse(
                success=False,
                error=APIError(
                    error_code="REQUEST_ERROR",
                    message=f"Request failed: {str(e)}",
                    status_code=500,
                ),
            )
        except Exception as e:
            logger.exception("Unexpected API error", path=path)
            return APIResponse(
                success=False,
                error=APIError(
                    error_code="INTERNAL_ERROR",
                    message=f"Internal error: {str(e)}",
                    status_code=500,
                ),
            )

    # =========================================================================
    # Intent Endpoints
    # =========================================================================

    async def create_intent(
        self,
        query: str,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> APIResponse:
        """Create a purchase intent.

        Args:
            query: Natural language purchase intent query.
            session_id: Optional session ID for tracking.
            metadata: Optional metadata to attach.

        Returns:
            APIResponse with created intent data.
        """
        return await self._request(
            method="POST",
            path="/intents",
            json={
                "query": query,
                "session_id": session_id,
                "metadata": metadata or {},
            },
        )

    async def get_intent(self, intent_id: str) -> APIResponse:
        """Get an intent by ID.

        Args:
            intent_id: Intent identifier.

        Returns:
            APIResponse with intent data.
        """
        return await self._request(
            method="GET",
            path=f"/intents/{intent_id}",
        )

    async def get_intent_offers(
        self,
        intent_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> APIResponse:
        """Get offers for an intent.

        Args:
            intent_id: Intent identifier.
            page: Page number.
            page_size: Items per page.

        Returns:
            APIResponse with paginated offers.
        """
        return await self._request(
            method="GET",
            path=f"/intents/{intent_id}/offers",
            params={"page": page, "page_size": page_size},
        )

    # =========================================================================
    # Offer Endpoints
    # =========================================================================

    async def get_offer(self, offer_id: str) -> APIResponse:
        """Get an offer by ID.

        Args:
            offer_id: Offer identifier.

        Returns:
            APIResponse with offer data.
        """
        return await self._request(
            method="GET",
            path=f"/offers/{offer_id}",
        )

    # =========================================================================
    # Checkout Endpoints
    # =========================================================================

    async def create_checkout(
        self,
        offer_id: str,
        items: list[dict[str, Any]],
        idempotency_key: str | None = None,
    ) -> APIResponse:
        """Create a checkout from an offer.

        Args:
            offer_id: Offer identifier.
            items: List of items with product_id, variant_id, quantity.
            idempotency_key: Optional idempotency key.

        Returns:
            APIResponse with created checkout data.
        """
        return await self._request(
            method="POST",
            path="/checkouts",
            json={
                "offer_id": offer_id,
                "items": items,
                "idempotency_key": idempotency_key,
            },
            idempotency_key=idempotency_key,
        )

    async def get_checkout(self, checkout_id: str) -> APIResponse:
        """Get a checkout by ID.

        Args:
            checkout_id: Checkout identifier.

        Returns:
            APIResponse with checkout data.
        """
        return await self._request(
            method="GET",
            path=f"/checkouts/{checkout_id}",
        )

    async def quote_checkout(
        self,
        checkout_id: str,
        items: list[dict[str, Any]],
        customer_email: str | None = None,
    ) -> APIResponse:
        """Get a quote from the merchant.

        Args:
            checkout_id: Checkout identifier.
            items: List of items to quote.
            customer_email: Optional customer email.

        Returns:
            APIResponse with quoted checkout data.
        """
        return await self._request(
            method="POST",
            path=f"/checkouts/{checkout_id}/quote",
            json={
                "items": items,
                "customer_email": customer_email,
            },
        )

    async def request_approval(self, checkout_id: str) -> APIResponse:
        """Request approval for a checkout.

        Args:
            checkout_id: Checkout identifier.

        Returns:
            APIResponse with checkout awaiting approval.
        """
        return await self._request(
            method="POST",
            path=f"/checkouts/{checkout_id}/request-approval",
        )

    async def approve_checkout(
        self,
        checkout_id: str,
        approved_by: str,
    ) -> APIResponse:
        """Approve a checkout.

        Args:
            checkout_id: Checkout identifier.
            approved_by: Approver identifier.

        Returns:
            APIResponse with approved checkout data.
        """
        return await self._request(
            method="POST",
            path=f"/checkouts/{checkout_id}/approve",
            json={"approved_by": approved_by},
        )

    async def confirm_checkout(
        self,
        checkout_id: str,
        payment_method: str = "test_card",
        idempotency_key: str | None = None,
    ) -> APIResponse:
        """Confirm a checkout and execute the purchase.

        Args:
            checkout_id: Checkout identifier.
            payment_method: Payment method to use.
            idempotency_key: Optional idempotency key.

        Returns:
            APIResponse with confirmation data.
        """
        return await self._request(
            method="POST",
            path=f"/checkouts/{checkout_id}/confirm",
            json={
                "payment_method": payment_method,
                "idempotency_key": idempotency_key,
            },
            idempotency_key=idempotency_key,
        )

    # =========================================================================
    # Order Endpoints
    # =========================================================================

    async def get_order(self, order_id: str) -> APIResponse:
        """Get an order by ID.

        Args:
            order_id: Order identifier.

        Returns:
            APIResponse with order data.
        """
        return await self._request(
            method="GET",
            path=f"/orders/{order_id}",
        )

    async def list_orders(
        self,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        merchant_id: str | None = None,
    ) -> APIResponse:
        """List orders with pagination.

        Args:
            page: Page number.
            page_size: Items per page.
            status: Filter by status.
            merchant_id: Filter by merchant.

        Returns:
            APIResponse with paginated orders.
        """
        return await self._request(
            method="GET",
            path="/orders",
            params={
                "page": page,
                "page_size": page_size,
                "status": status,
                "merchant_id": merchant_id,
            },
        )

    async def simulate_advance_order(
        self,
        order_id: str,
        steps: int = 1,
    ) -> APIResponse:
        """Simulate order advancement for testing.

        Args:
            order_id: Order identifier.
            steps: Number of steps to advance.

        Returns:
            APIResponse with advanced order data.
        """
        return await self._request(
            method="POST",
            path=f"/orders/{order_id}/simulate-advance",
            json={"steps": steps},
        )


class MerchantBChaosClient:
    """HTTP client for Merchant B chaos endpoints.

    Provides methods to configure chaos scenarios for testing.
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 10.0,
    ) -> None:
        """Initialize the chaos client.

        Args:
            base_url: Merchant B base URL.
            timeout: Request timeout in seconds.
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
    ) -> APIResponse:
        """Make a request to Merchant B."""
        client = await self._get_client()

        try:
            response = await client.request(
                method=method,
                url=path,
                json=json,
            )

            if response.status_code >= 400:
                error_data = response.json()
                return APIResponse(
                    success=False,
                    error=APIError(
                        error_code=error_data.get("error_code", "UNKNOWN_ERROR"),
                        message=error_data.get("message", "Unknown error"),
                        status_code=response.status_code,
                    ),
                )

            return APIResponse(success=True, data=response.json())

        except Exception as e:
            logger.exception("Merchant B request failed", path=path)
            return APIResponse(
                success=False,
                error=APIError(
                    error_code="REQUEST_ERROR",
                    message=str(e),
                    status_code=500,
                ),
            )

    async def get_chaos_config(self) -> APIResponse:
        """Get current chaos configuration."""
        return await self._request("GET", "/chaos/config")

    async def configure_chaos(
        self,
        scenarios: dict[str, bool],
        price_change_percent: int = 15,
        out_of_stock_probability: float = 0.3,
        duplicate_webhook_count: int = 3,
        webhook_delay_seconds: float = 5.0,
    ) -> APIResponse:
        """Configure chaos scenarios.

        Args:
            scenarios: Map of scenario name to enabled status.
            price_change_percent: Price change percentage.
            out_of_stock_probability: OOS probability.
            duplicate_webhook_count: Number of duplicate webhooks.
            webhook_delay_seconds: Webhook delay.

        Returns:
            APIResponse with updated config.
        """
        return await self._request(
            method="POST",
            path="/chaos/configure",
            json={
                "scenarios": scenarios,
                "price_change_percent": price_change_percent,
                "out_of_stock_probability": out_of_stock_probability,
                "duplicate_webhook_count": duplicate_webhook_count,
                "webhook_delay_seconds": webhook_delay_seconds,
            },
        )

    async def enable_scenario(self, scenario: str) -> APIResponse:
        """Enable a specific chaos scenario.

        Args:
            scenario: Scenario name (price_change, out_of_stock, etc.)

        Returns:
            APIResponse with updated config.
        """
        return await self._request(
            method="POST",
            path=f"/chaos/scenarios/{scenario}/enable",
        )

    async def disable_scenario(self, scenario: str) -> APIResponse:
        """Disable a specific chaos scenario.

        Args:
            scenario: Scenario name.

        Returns:
            APIResponse with updated config.
        """
        return await self._request(
            method="POST",
            path=f"/chaos/scenarios/{scenario}/disable",
        )

    async def enable_all(self) -> APIResponse:
        """Enable all chaos scenarios."""
        return await self._request("POST", "/chaos/enable")

    async def disable_all(self) -> APIResponse:
        """Disable all chaos scenarios."""
        return await self._request("POST", "/chaos/disable")

    async def reset(self) -> APIResponse:
        """Reset chaos controller to defaults."""
        return await self._request("POST", "/chaos/reset")

    async def get_events(
        self,
        limit: int = 50,
        scenario: str | None = None,
        checkout_id: str | None = None,
    ) -> APIResponse:
        """Get chaos event log."""
        client = await self._get_client()

        params = {"limit": limit}
        if scenario:
            params["scenario"] = scenario
        if checkout_id:
            params["checkout_id"] = checkout_id

        try:
            response = await client.get("/chaos/events", params=params)
            return APIResponse(success=True, data=response.json())
        except Exception as e:
            return APIResponse(
                success=False,
                error=APIError(
                    error_code="REQUEST_ERROR",
                    message=str(e),
                    status_code=500,
                ),
            )
