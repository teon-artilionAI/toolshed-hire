"""An in memory unit of work, for testing use cases with no database at all.

The application layer depends on ports, so a second implementation of those
ports is all it takes to run a use case in a unit test. This one keeps
everything in plain lists and dictionaries. It behaves like a transaction in
the one way that matters to a use case, which is that work is only kept when
`commit` is called and is thrown away when the block is left without one.

It is a test double and not a simulator. It knows the allocation rule, because
a use case that cannot be refused a unit cannot be tested for the refusal, but
it makes no attempt at concurrency. The real constraint and the real row locks
are proved against PostgreSQL in tests/integration.

Faults are switched on through the store, so a test can make the audit log or
the outbox fail at the moment it wants to and then look at what was kept.

The reservation repository is in `memory_booking`, with the read models it
builds, and the repositories of the reference data are in `memory_reference`.
"""

from __future__ import annotations

import copy
import itertools
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, time
from types import TracebackType
from typing import Final, Self
from uuid import UUID

from app.domain.audit import AuditEvent
from app.domain.availability import AssetAllocation
from app.domain.booking import Reservation
from app.domain.catalogue import Asset, ProductModel
from app.domain.enums import AccountStatus, NotificationStatus
from app.domain.errors import AllocationConflictError
from app.domain.identity import Branch, CustomerProfile
from app.domain.notification import Notification
from app.domain.period import BookingPeriod
from tests.support.memory_booking import MemoryReservations
from tests.support.memory_reference import (
    MemoryBranches,
    MemoryCustomers,
    MemoryProductModels,
)

FIRST_REFERENCE_NUMBER: Final[int] = 124
CONSTRAINT_NAME: Final[str] = "asset_allocation_no_overlap"
COMMIT: Final[str] = "commit"
ROLLBACK: Final[str] = "rollback"


class StoreFault(RuntimeError):
    """Raised by the in memory store when a test has switched a fault on."""


@dataclass
class Records:
    """Everything a transaction can change."""

    reservations: list[Reservation] = field(default_factory=list)
    allocations: list[AssetAllocation] = field(default_factory=list)
    audit_events: list[AuditEvent] = field(default_factory=list)
    notifications: dict[UUID, Notification] = field(default_factory=dict)
    late_cancellations: dict[UUID, int] = field(default_factory=dict)
    no_shows: dict[UUID, int] = field(default_factory=dict)
    account_statuses: dict[UUID, AccountStatus] = field(default_factory=dict)


@dataclass
class MemoryStore:
    """The committed state, the reference data and the fault switches.

    Attributes:
        committed: What has been committed so far.
        branches: The branches that exist, by key.
        product_models: The catalogue entries that exist, by key.
        profiles: The customer profiles, by the account they belong to.
        walk_ins: The customer profiles that have no account.
        assets: The fleet.
        unpublished_slugs: The slugs of models that exist and are not published.
        closed_branch_codes: The codes of branches that have stopped trading.
        closing_times: When a branch closes, by its key. 17:00 for any not named.
        stale_no_show_query: True to make the no show query return everything.
        journal: `commit` and `rollback`, in the order they happened.
        fail_audit: When True, recording an audit event raises.
        fail_outbox_read: When True, reading the queued notifications raises.
        fail_outbox_write: When True, recording a send outcome raises.

    """

    committed: Records = field(default_factory=Records)
    branches: dict[UUID, Branch] = field(default_factory=dict)
    product_models: dict[UUID, ProductModel] = field(default_factory=dict)
    profiles: dict[UUID, CustomerProfile] = field(default_factory=dict)
    walk_ins: list[CustomerProfile] = field(default_factory=list)
    assets: list[Asset] = field(default_factory=list)
    unpublished_slugs: set[str] = field(default_factory=set)
    closed_branch_codes: set[str] = field(default_factory=set)
    closing_times: dict[UUID, time] = field(default_factory=dict)
    stale_no_show_query: bool = False
    journal: list[str] = field(default_factory=list)
    fail_audit: bool = False
    fail_outbox_read: bool = False
    fail_outbox_write: bool = False
    _references: itertools.count[int] = field(
        default_factory=lambda: itertools.count(FIRST_REFERENCE_NUMBER)
    )

    def next_reference_number(self) -> int:
        """Return the next reference number. Like a sequence, it never rolls back."""
        return next(self._references)

    def profile_with_id(self, customer_profile_id: UUID) -> CustomerProfile | None:
        """Return the customer profile with this key, with or without an account."""
        for profile in (*self.profiles.values(), *self.walk_ins):
            if profile.id == customer_profile_id:
                return profile
        return None

    def tag_of(self, asset_id: UUID) -> str:
        """Return the tag of a unit of the fleet.

        Raises:
            LookupError: If the store holds no unit with this key.

        """
        for asset in self.assets:
            if asset.id == asset_id:
                return asset.asset_tag
        raise LookupError(f"Attempted to read the tag of asset {asset_id}, which is not stored.")


class _Assets:
    """The asset repository over the working copy."""

    def __init__(self, store: MemoryStore, working: Records) -> None:
        """Bind to the store and to the working copy of one transaction."""
        self._store = store
        self._working = working

    def lock_allocatable(
        self, product_model_id: UUID, branch_id: UUID, period: BookingPeriod, wanted: int
    ) -> list[Asset]:
        """Return up to `wanted` free units in asset tag order."""
        free = [
            asset
            for asset in self._store.assets
            if asset.product_model_id == product_model_id
            and asset.branch_id == branch_id
            and asset.is_allocatable()
            and not self._is_held(asset.id, period)
        ]
        return sorted(free, key=lambda asset: asset.asset_tag)[:wanted]

    def save_allocations(self, allocations: Sequence[AssetAllocation]) -> None:
        """Keep the allocations, refusing one that overlaps an active allocation."""
        for allocation in allocations:
            if any(allocation.conflicts_with(existing) for existing in self._working.allocations):
                raise AllocationConflictError(
                    "The in memory store refused an overlapping allocation.",
                    constraint_name=CONSTRAINT_NAME,
                )
            self._working.allocations.append(allocation)

    def _is_held(self, asset_id: UUID, period: BookingPeriod) -> bool:
        """Return True when an active allocation of the asset overlaps the period."""
        return any(
            allocation.asset_id == asset_id
            and allocation.is_active()
            and allocation.period.overlaps(period)
            for allocation in self._working.allocations
        )


class _Outbox:
    """The notification outbox over the working copy."""

    def __init__(self, store: MemoryStore, working: Records) -> None:
        """Bind to the store and to the working copy of one transaction."""
        self._store = store
        self._working = working

    def enqueue(self, notification: Notification) -> None:
        """Keep a copy of the queued notification."""
        self._working.notifications[notification.id] = copy.deepcopy(notification)

    def due(self, limit: int) -> list[Notification]:
        """Return copies of the queued notifications, oldest first."""
        if self._store.fail_outbox_read:
            raise StoreFault("The outbox could not be read.")
        queued = [
            notification
            for notification in self._working.notifications.values()
            if notification.status is NotificationStatus.QUEUED
        ]
        queued.sort(key=lambda notification: (notification.queued_at, str(notification.id)))
        return copy.deepcopy(queued[:limit])

    def mark_sent(
        self, notification_id: UUID, provider_message_id: str, sent_at: datetime
    ) -> None:
        """Record a successful send."""
        if self._store.fail_outbox_write:
            raise StoreFault("The outcome could not be written.")
        self._working.notifications[notification_id].mark_sent(provider_message_id, sent_at)

    def mark_failed(self, notification_id: UUID, reason: str) -> None:
        """Record a failed send."""
        if self._store.fail_outbox_write:
            raise StoreFault("The outcome could not be written.")
        self._working.notifications[notification_id].mark_failed(reason)


class _AuditLog:
    """The audit log over the working copy."""

    def __init__(self, store: MemoryStore, working: Records) -> None:
        """Bind to the store and to the working copy of one transaction."""
        self._store = store
        self._working = working

    def record(self, event: AuditEvent) -> None:
        """Keep the event, or fail when the test has switched the fault on."""
        if self._store.fail_audit:
            raise StoreFault("The audit event could not be written.")
        self._working.audit_events.append(event)


class InMemoryUnitOfWork:
    """A unit of work that keeps its records in memory."""

    reservations: MemoryReservations
    assets: _Assets
    branches: MemoryBranches
    product_models: MemoryProductModels
    customers: MemoryCustomers
    notifications: _Outbox
    audit: _AuditLog

    def __init__(self, store: MemoryStore) -> None:
        """Bind the unit of work to the store it commits into."""
        self.store = store
        self._working: Records | None = None

    def __enter__(self) -> Self:
        """Take a working copy of the committed records."""
        self._bind(copy.deepcopy(self.store.committed))
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Throw the working copy away. Anything committed has already been kept."""
        self._working = None

    def commit(self) -> None:
        """Make the working copy the committed state."""
        if self._working is None:
            raise RuntimeError("Attempted to commit an in memory unit of work that is not open.")
        self.store.committed = copy.deepcopy(self._working)
        self.store.journal.append(COMMIT)

    def rollback(self) -> None:
        """Replace the working copy with the committed state."""
        if self._working is None:
            raise RuntimeError("Attempted to roll back an in memory unit of work that is not open.")
        self._bind(copy.deepcopy(self.store.committed))
        self.store.journal.append(ROLLBACK)

    def working_records(self) -> Records:
        """Return the working copy of the open transaction.

        Raises:
            RuntimeError: If the unit of work is not open.

        """
        if self._working is None:
            raise RuntimeError("Attempted to read an in memory unit of work that is not open.")
        return self._working

    def _bind(self, working: Records) -> None:
        """Point every repository at one working copy."""
        self._working = working
        self.reservations = MemoryReservations(self.store, working)
        self.assets = _Assets(self.store, working)
        self.branches = MemoryBranches(self.store)
        self.product_models = MemoryProductModels(self.store)
        self.customers = MemoryCustomers(self.store, working)
        self.notifications = _Outbox(self.store, working)
        self.audit = _AuditLog(self.store, working)


__all__ = ["COMMIT", "ROLLBACK", "InMemoryUnitOfWork", "MemoryStore", "Records", "StoreFault"]
