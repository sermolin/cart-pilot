"""Base classes for domain layer.

Provides foundational abstractions for entities, value objects,
aggregates, and domain events following DDD patterns.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar, Generic, TypeVar
from uuid import UUID, uuid4


# ============================================================================
# Value Object Base
# ============================================================================


@dataclass(frozen=True)
class ValueObject(ABC):
    """Base class for value objects.

    Value objects are immutable and compared by their attributes,
    not by identity. They have no lifecycle and are interchangeable
    when their values are equal.

    Example:
        @dataclass(frozen=True)
        class Money(ValueObject):
            amount_cents: int
            currency: str
    """

    pass


# ============================================================================
# Entity Base
# ============================================================================


T = TypeVar("T", bound=UUID | str)


@dataclass
class Entity(ABC, Generic[T]):
    """Base class for entities.

    Entities have identity that persists across state changes.
    Two entities are equal if they have the same identity,
    regardless of their other attributes.

    Attributes:
        id: Unique identifier for this entity.
    """

    id: T

    def __eq__(self, other: object) -> bool:
        """Compare entities by identity.

        Args:
            other: Object to compare with.

        Returns:
            True if other is same type with same id.
        """
        if not isinstance(other, self.__class__):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        """Hash entity by identity.

        Returns:
            Hash of the entity id.
        """
        return hash(self.id)


# ============================================================================
# Aggregate Root Base
# ============================================================================


@dataclass(kw_only=True)
class AggregateRoot(Entity[T], Generic[T]):
    """Base class for aggregate roots.

    Aggregate roots are the entry point to a cluster of domain objects.
    They ensure consistency of the aggregate and emit domain events.

    Attributes:
        version: Optimistic locking version for concurrency control.
        created_at: Timestamp when the aggregate was created.
        updated_at: Timestamp of last modification.
    """

    version: int = field(default=1, compare=False)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
        compare=False,
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
        compare=False,
    )
    _events: list["DomainEvent"] = field(
        default_factory=list,
        init=False,
        repr=False,
        compare=False,
    )

    def _record_event(self, event: "DomainEvent") -> None:
        """Record a domain event.

        Events are collected and published after the aggregate is persisted.

        Args:
            event: Domain event to record.
        """
        self._events.append(event)

    def collect_events(self) -> list["DomainEvent"]:
        """Collect and clear recorded events.

        Returns:
            List of domain events that were recorded.
        """
        events = self._events.copy()
        self._events.clear()
        return events

    def _touch(self) -> None:
        """Update the updated_at timestamp and increment version."""
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1


# ============================================================================
# Domain Event Base
# ============================================================================


@dataclass(frozen=True)
class DomainEvent(ABC):
    """Base class for domain events.

    Domain events represent something significant that happened
    in the domain. They are immutable and contain all information
    about what happened.

    Attributes:
        event_id: Unique identifier for this event instance.
        event_type: String identifier for the event type (set by subclass).
        occurred_at: Timestamp when the event occurred.
        aggregate_id: ID of the aggregate that emitted this event.
        aggregate_type: Type name of the aggregate.
    """

    event_type: ClassVar[str]

    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    aggregate_id: str = field(default="")
    aggregate_type: str = field(default="")

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary for serialization.

        Returns:
            Dictionary representation of the event.
        """
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.isoformat(),
            "aggregate_id": self.aggregate_id,
            "aggregate_type": self.aggregate_type,
            "payload": self._payload(),
        }

    @abstractmethod
    def _payload(self) -> dict[str, Any]:
        """Get event-specific payload data.

        Returns:
            Dictionary with event-specific data.
        """
        pass
