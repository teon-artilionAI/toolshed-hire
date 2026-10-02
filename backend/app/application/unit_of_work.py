"""The unit of work port, the one owner of a transaction boundary.

One booking writes a reservation, a line, an allocation for every unit, an
audit event and a queued notification. BR-09 and BR-49 need those to commit
together or not at all, so they are written through repositories that share
one transaction, and exactly one object decides when that transaction ends.

A use case enters the unit of work, does its work through the repositories it
exposes and calls `commit`. Leaving the block without a commit, whether by
returning early or by an exception, rolls everything back. Nothing is ever
committed by accident, because commit is a call somebody has to write.
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self

from app.application.audit import AuditLog
from app.application.availability.ports import AssetRepository
from app.application.booking.ports import ReservationRepository
from app.application.catalogue.ports import ProductModelRepository
from app.application.identity.ports import (
    AccountRepository,
    BranchRepository,
    CustomerRepository,
    SessionRepository,
)
from app.application.notification.ports import NotificationOutbox
from app.application.throttle import RateLimitStore


class UnitOfWork(Protocol):
    """A transaction, and the repositories that write inside it.

    The repositories are only usable inside the `with` block. They are declared
    as read only properties so that an implementation may expose any class
    that satisfies the port.
    """

    @property
    def reservations(self) -> ReservationRepository:
        """Return the reservation repository of this transaction."""
        ...

    @property
    def assets(self) -> AssetRepository:
        """Return the asset repository of this transaction."""
        ...

    @property
    def branches(self) -> BranchRepository:
        """Return the branch repository of this transaction."""
        ...

    @property
    def product_models(self) -> ProductModelRepository:
        """Return the product model repository of this transaction."""
        ...

    @property
    def customers(self) -> CustomerRepository:
        """Return the customer repository of this transaction."""
        ...

    @property
    def accounts(self) -> AccountRepository:
        """Return the account repository of this transaction."""
        ...

    @property
    def sessions(self) -> SessionRepository:
        """Return the refresh session repository of this transaction."""
        ...

    @property
    def rate_limits(self) -> RateLimitStore:
        """Return the throttle counters of this transaction."""
        ...

    @property
    def notifications(self) -> NotificationOutbox:
        """Return the notification outbox of this transaction."""
        ...

    @property
    def audit(self) -> AuditLog:
        """Return the audit log of this transaction."""
        ...

    def __enter__(self) -> Self:
        """Open the transaction and return the unit of work."""
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Roll back whatever was not committed and release the transaction."""
        ...

    def commit(self) -> None:
        """Make everything written so far permanent."""
        ...

    def rollback(self) -> None:
        """Discard everything written since the last commit."""
        ...
