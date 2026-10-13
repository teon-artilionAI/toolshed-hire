"""An in memory unit of work and read for the owner's closure days, with no database at all.

The closure use cases reach the branches, the closure days and the audit log
through the unit of work. Everything is kept here in plain dictionaries, and
work is kept only when `commit` is called, so a test can see that a refusal
wrote nothing.

The store can be told what the database would do. `race_on_add` makes the next
closure lose to the unique index after the use case's own check found the day
open, and `fail_audit` makes the audit write fail. Nothing is locked, because
the lock and the index are proved against PostgreSQL in tests/integration.

`MemoryClosureReads` is the double of the read side. It answers the committed
live closures in a span and the bookings a test put on a day.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from datetime import date
from types import TracebackType
from typing import Final, Self
from uuid import UUID, uuid4

from app.application.trading.closure_models import StrandedBooking, StrandedBookings
from app.application.trading.closure_ports import DuplicateClosureDay
from app.domain.audit import AuditEvent
from app.domain.closure_day import ClosureDay
from app.domain.identity import Branch
from app.domain.trading_calendar import BranchCalendar
from tests.support.clock import DEFAULT_INSTANT
from tests.support.memory_outbox import StoreFault

COMMIT: Final[str] = "commit"


@dataclass
class ClosureRecords:
    """Everything a transaction of the closure days can change."""

    closures: dict[UUID, ClosureDay] = field(default_factory=dict)
    created_by: dict[UUID, UUID] = field(default_factory=dict)
    cancelled_by: dict[UUID, UUID] = field(default_factory=dict)
    audit_events: list[AuditEvent] = field(default_factory=list)


@dataclass
class ClosureStore:
    """The committed closures, the branches and the fault switches.

    Attributes:
        committed: What has been committed so far.
        branches: The branches, by code.
        closed_branch_codes: The codes of branches that stopped trading.
        bookings: The bookings the read finds, with the key of their branch.
        journal: `commit` for every commit, in order.
        race_on_add: True to make the next closure lose to the unique index.
        fail_audit: When True, recording an audit event raises.

    """

    committed: ClosureRecords = field(default_factory=ClosureRecords)
    branches: dict[str, Branch] = field(default_factory=dict)
    closed_branch_codes: set[str] = field(default_factory=set)
    bookings: list[tuple[UUID, StrandedBooking]] = field(default_factory=list)
    journal: list[str] = field(default_factory=list)
    race_on_add: bool = False
    fail_audit: bool = False

    def branch(self, code: str) -> Branch:
        """Add a trading branch with the design's week and return it."""
        added = Branch(
            id=uuid4(), code=code, name=f"{code} branch", calendar=BranchCalendar.standard()
        )
        self.branches[code] = added
        return added

    def keep(self, *, branch_code: str | None, day: date, reason: str = "Stocktake") -> ClosureDay:
        """Commit a live closure a test starts from and return it."""
        branch = self.branches[branch_code] if branch_code is not None else None
        closure = ClosureDay(
            id=uuid4(),
            branch_id=branch.id if branch is not None else None,
            branch_code=branch_code,
            day=day,
            reason=reason,
            created_at=DEFAULT_INSTANT,
        )
        self.committed.closures[closure.id] = closure
        return closure

    @property
    def events(self) -> list[AuditEvent]:
        """Return the audit events committed so far."""
        return self.committed.audit_events


class MemoryClosureBranches:
    """The branch repository, as far as a closure asks it."""

    def __init__(self, store: ClosureStore) -> None:
        """Bind to the store that holds the branches."""
        self._store = store

    def get(self, branch_id: UUID) -> Branch | None:
        """Return the branch with this key, if there is one."""
        return next((b for b in self._store.branches.values() if b.id == branch_id), None)

    def find_active_by_code(self, code: str) -> Branch | None:
        """Return the trading branch with this code, if there is one."""
        if code in self._store.closed_branch_codes:
            return None
        return self._store.branches.get(code)


class _Closures:
    """The closure repository over the working copy."""

    def __init__(self, store: ClosureStore, working: ClosureRecords) -> None:
        """Bind to the store and to the working copy of one transaction."""
        self._store = store
        self._working = working

    def live_on(self, branch_id: UUID | None, day: date) -> ClosureDay | None:
        """Return the branch's own live closure on the day, or else one for every branch."""
        live = [c for c in self._working.closures.values() if c.is_live and c.day == day]
        own = [c for c in live if branch_id is not None and c.branch_id == branch_id]
        every = [c for c in live if c.branch_id is None]
        return (own or every or [None])[0]

    def get_for_update(self, closure_id: UUID) -> ClosureDay | None:
        """Return the closure with this key, if there is one."""
        return self._working.closures.get(closure_id)

    def add(self, closure: ClosureDay, created_by_user_id: UUID) -> None:
        """Keep a new closure, or lose to the unique index when the test says so."""
        if self._store.race_on_add:
            self._store.race_on_add = False
            raise DuplicateClosureDay(closure.branch_id, closure.day)
        self._working.closures[closure.id] = closure
        self._working.created_by[closure.id] = created_by_user_id

    def save_cancellation(self, closure: ClosureDay, cancelled_by_user_id: UUID) -> None:
        """Keep the cancellation of a closure."""
        self._working.closures[closure.id] = closure
        self._working.cancelled_by[closure.id] = cancelled_by_user_id


class _AuditLog:
    """The audit log over the working copy."""

    def __init__(self, store: ClosureStore, working: ClosureRecords) -> None:
        """Bind to the store and to the working copy of one transaction."""
        self._store = store
        self._working = working

    def record(self, event: AuditEvent) -> None:
        """Keep the event, or fail when the test has switched the fault on."""
        if self._store.fail_audit:
            raise StoreFault("The audit event could not be written.")
        self._working.audit_events.append(event)


class MemoryClosureUnitOfWork:
    """A unit of work over the closure days that keeps its records in memory."""

    branches: MemoryClosureBranches
    closure_days: _Closures
    audit: _AuditLog

    def __init__(self, store: ClosureStore) -> None:
        """Bind the unit of work to the store it commits into."""
        self.store = store
        self._working: ClosureRecords | None = None

    def __enter__(self) -> Self:
        """Take a working copy of the committed records."""
        working = copy.deepcopy(self.store.committed)
        self._working = working
        self.branches = MemoryClosureBranches(self.store)
        self.closure_days = _Closures(self.store, working)
        self.audit = _AuditLog(self.store, working)
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


class MemoryClosureReads:
    """The read side of the closure days, over the committed state."""

    def __init__(self, store: ClosureStore) -> None:
        """Bind to the store the closures were committed into."""
        self._store = store
        self.limits_asked: list[int] = []

    def live_between(self, first: date, last: date) -> list[ClosureDay]:
        """Return the committed live closures in the span, by day."""
        found = [
            c
            for c in self._store.committed.closures.values()
            if c.is_live and first <= c.day <= last
        ]
        return sorted(found, key=lambda closure: (closure.day, closure.branch_code or ""))

    def bookings_on(self, branch_id: UUID | None, day: date, limit: int) -> StrandedBookings:
        """Return the bookings a test put on the day, at the branch or at every branch."""
        self.limits_asked.append(limit)
        found = [
            replace(booking)
            for booked_at, booking in self._store.bookings
            if (branch_id is None or booked_at == branch_id) and day in (booking.start, booking.end)
        ]
        return StrandedBookings(items=tuple(found[:limit]), total=len(found))


__all__ = [
    "COMMIT",
    "ClosureStore",
    "MemoryClosureBranches",
    "MemoryClosureReads",
    "MemoryClosureUnitOfWork",
    "StoreFault",
]
