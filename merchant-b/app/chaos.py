"""Chaos controller for Merchant B.

Manages chaos mode configuration and scenario triggering.
"""

import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog

from app.schemas import (
    ChaosConfigRequest,
    ChaosConfigResponse,
    ChaosEventLog,
    ChaosEventsResponse,
    ChaosScenario,
)

logger = structlog.get_logger()


@dataclass
class ChaosConfig:
    """Configuration for chaos mode."""

    enabled: bool = False
    scenarios: dict[ChaosScenario, bool] = field(default_factory=lambda: {
        ChaosScenario.PRICE_CHANGE: False,
        ChaosScenario.OUT_OF_STOCK: False,
        ChaosScenario.DUPLICATE_WEBHOOK: False,
        ChaosScenario.DELAYED_WEBHOOK: False,
        ChaosScenario.OUT_OF_ORDER_WEBHOOK: False,
    })
    price_change_percent: int = 15
    out_of_stock_probability: float = 0.3
    duplicate_webhook_count: int = 3
    webhook_delay_seconds: float = 5.0


class ChaosController:
    """Controls chaos mode behavior for Merchant B.

    Manages:
    - Enabling/disabling chaos scenarios
    - Probability-based triggering
    - Event logging for debugging
    """

    MAX_EVENT_LOG_SIZE = 100

    def __init__(self) -> None:
        """Initialize chaos controller."""
        self.config = ChaosConfig()
        self._event_log: list[ChaosEventLog] = []
        self._rng = random.Random()

    def configure(self, request: ChaosConfigRequest) -> ChaosConfigResponse:
        """Configure chaos mode settings.

        Args:
            request: Configuration request.

        Returns:
            Current configuration.
        """
        # Update scenarios
        for scenario, enabled in request.scenarios.items():
            self.config.scenarios[scenario] = enabled

        # Update parameters
        self.config.price_change_percent = request.price_change_percent
        self.config.out_of_stock_probability = request.out_of_stock_probability
        self.config.duplicate_webhook_count = request.duplicate_webhook_count
        self.config.webhook_delay_seconds = request.webhook_delay_seconds

        # Auto-enable if any scenario is enabled
        self.config.enabled = any(self.config.scenarios.values())

        logger.info(
            "Chaos mode configured",
            enabled=self.config.enabled,
            scenarios={k.value: v for k, v in self.config.scenarios.items()},
        )

        return self.get_config()

    def get_config(self) -> ChaosConfigResponse:
        """Get current chaos configuration.

        Returns:
            Current configuration.
        """
        return ChaosConfigResponse(
            enabled=self.config.enabled,
            scenarios=self.config.scenarios,
            price_change_percent=self.config.price_change_percent,
            out_of_stock_probability=self.config.out_of_stock_probability,
            duplicate_webhook_count=self.config.duplicate_webhook_count,
            webhook_delay_seconds=self.config.webhook_delay_seconds,
        )

    def enable_all(self) -> ChaosConfigResponse:
        """Enable all chaos scenarios.

        Returns:
            Updated configuration.
        """
        for scenario in ChaosScenario:
            self.config.scenarios[scenario] = True
        self.config.enabled = True

        logger.info("All chaos scenarios enabled")

        return self.get_config()

    def disable_all(self) -> ChaosConfigResponse:
        """Disable all chaos scenarios.

        Returns:
            Updated configuration.
        """
        for scenario in ChaosScenario:
            self.config.scenarios[scenario] = False
        self.config.enabled = False

        logger.info("All chaos scenarios disabled")

        return self.get_config()

    def enable_scenario(self, scenario: ChaosScenario) -> ChaosConfigResponse:
        """Enable a specific chaos scenario.

        Args:
            scenario: Scenario to enable.

        Returns:
            Updated configuration.
        """
        self.config.scenarios[scenario] = True
        self.config.enabled = True

        logger.info("Chaos scenario enabled", scenario=scenario.value)

        return self.get_config()

    def disable_scenario(self, scenario: ChaosScenario) -> ChaosConfigResponse:
        """Disable a specific chaos scenario.

        Args:
            scenario: Scenario to disable.

        Returns:
            Updated configuration.
        """
        self.config.scenarios[scenario] = False
        self.config.enabled = any(self.config.scenarios.values())

        logger.info("Chaos scenario disabled", scenario=scenario.value)

        return self.get_config()

    def should_trigger(self, scenario: ChaosScenario) -> bool:
        """Determine if a chaos scenario should trigger.

        Uses probability-based triggering for more realistic chaos.

        Args:
            scenario: Scenario to check.

        Returns:
            True if scenario should trigger.
        """
        if not self.config.enabled:
            return False

        if not self.config.scenarios.get(scenario, False):
            return False

        # Different probabilities for different scenarios
        if scenario == ChaosScenario.PRICE_CHANGE:
            # 50% chance when enabled
            return self._rng.random() < 0.5

        elif scenario == ChaosScenario.OUT_OF_STOCK:
            return self._rng.random() < self.config.out_of_stock_probability

        elif scenario == ChaosScenario.DUPLICATE_WEBHOOK:
            # 70% chance when enabled
            return self._rng.random() < 0.7

        elif scenario == ChaosScenario.DELAYED_WEBHOOK:
            # 60% chance when enabled
            return self._rng.random() < 0.6

        elif scenario == ChaosScenario.OUT_OF_ORDER_WEBHOOK:
            # 40% chance when enabled
            return self._rng.random() < 0.4

        return False

    def force_trigger(self, scenario: ChaosScenario) -> bool:
        """Force a chaos scenario to trigger immediately.

        Bypasses probability checks.

        Args:
            scenario: Scenario to trigger.

        Returns:
            True if scenario was triggered.
        """
        if not self.config.scenarios.get(scenario, False):
            return False

        logger.info("Force triggering chaos scenario", scenario=scenario.value)
        return True

    def log_event(
        self,
        scenario: ChaosScenario,
        checkout_id: str | None,
        details: dict[str, Any],
    ) -> ChaosEventLog:
        """Log a chaos event.

        Args:
            scenario: Triggered scenario.
            checkout_id: Related checkout ID.
            details: Event details.

        Returns:
            Created event log entry.
        """
        event = ChaosEventLog(
            id=str(uuid.uuid4()),
            scenario=scenario,
            checkout_id=checkout_id,
            details=details,
            triggered_at=datetime.now(timezone.utc),
        )

        self._event_log.append(event)

        # Trim log if too large
        if len(self._event_log) > self.MAX_EVENT_LOG_SIZE:
            self._event_log = self._event_log[-self.MAX_EVENT_LOG_SIZE:]

        logger.info(
            "Chaos event logged",
            scenario=scenario.value,
            checkout_id=checkout_id,
            details=details,
        )

        return event

    def get_events(
        self,
        limit: int = 50,
        scenario: ChaosScenario | None = None,
        checkout_id: str | None = None,
    ) -> ChaosEventsResponse:
        """Get chaos event log.

        Args:
            limit: Maximum events to return.
            scenario: Filter by scenario.
            checkout_id: Filter by checkout ID.

        Returns:
            Event log response.
        """
        events = self._event_log.copy()

        # Apply filters
        if scenario:
            events = [e for e in events if e.scenario == scenario]

        if checkout_id:
            events = [e for e in events if e.checkout_id == checkout_id]

        # Sort by most recent first
        events.sort(key=lambda e: e.triggered_at, reverse=True)

        # Apply limit
        events = events[:limit]

        return ChaosEventsResponse(
            events=events,
            total=len(self._event_log),
        )

    def clear_events(self) -> int:
        """Clear all chaos events.

        Returns:
            Number of events cleared.
        """
        count = len(self._event_log)
        self._event_log.clear()
        logger.info("Chaos event log cleared", count=count)
        return count

    def reset(self) -> ChaosConfigResponse:
        """Reset chaos controller to default state.

        Disables all scenarios and clears event log.

        Returns:
            Reset configuration.
        """
        self.disable_all()
        self.clear_events()
        self.config.price_change_percent = 15
        self.config.out_of_stock_probability = 0.3
        self.config.duplicate_webhook_count = 3
        self.config.webhook_delay_seconds = 5.0

        logger.info("Chaos controller reset")

        return self.get_config()


# Global chaos controller instance
_chaos_controller: ChaosController | None = None


def get_chaos_controller() -> ChaosController:
    """Get or create chaos controller instance.

    Returns:
        ChaosController instance.
    """
    global _chaos_controller
    if _chaos_controller is None:
        _chaos_controller = ChaosController()
    return _chaos_controller


def reset_chaos_controller() -> None:
    """Reset chaos controller instance (for testing)."""
    global _chaos_controller
    _chaos_controller = None
