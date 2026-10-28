"""The ports of the closure days, one that writes and one that reads.

`ClosureDayRepository` is reached through the unit of work, so a closure and
its audit event commit together (BR-49). A closure about to be cancelled is
read under a lock, so two owners cancelling it at once take turns and the
second is told it was cancelled already.

The database allows one live closure per branch and day, and has the last
word on it. A use case asks first whether the day is closed already, so it can
say so in a plain sentence, and a repository that loses a race to the unique
index raises `DuplicateClosureDay`, which the use case answers the same way.

`ClosureDayQuery` is the read side. It lists the live closures in a span of
days and the bookings and hires out a new closure would strand, and nothing
here writes.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol
from uuid import UUID

from app.application.trading.closure_models import StrandedBookings
from app.domain.closure_day import ClosureDay


class DuplicateClosureDay(Exception):
    """The unique index refused a second live closure of one branch on one day."""

    def __init__(self, branch_id: UUID | None, day: date) -> None:
        """Keep the branch and the day that were refused."""
        target = str(branch_id) if branch_id is not None else "every branch"
        super().__init__(
            f"Attempted to store a second live closure for {target} on {day.isoformat()}."
        )
        self.branch_id = branch_id
        self.day = day


class ClosureDayRepository(Protocol):
    """The closure days, read and written inside a unit of work."""

    def live_on(self, branch_id: UUID | None, day: date) -> ClosureDay | None:
        """Return the live closure that already closes a branch on a day, or None.

        Args:
            branch_id: The branch, or None for every branch.
            day: The day.

        Returns:
            A closure of that branch on the day, or else one for every branch
            on the day. Asked for every branch, only one for every branch.

        """
        ...

    def get_for_update(self, closure_id: UUID) -> ClosureDay | None:
        """Return the closure with this key locked for the rest of the transaction, or None."""
        ...

    def add(self, closure: ClosureDay, created_by_user_id: UUID) -> None:
        """Write a new live closure inside the current transaction.

        Raises:
            DuplicateClosureDay: If the unique index refused it.

        """
        ...

    def save_cancellation(self, closure: ClosureDay, cancelled_by_user_id: UUID) -> None:
        """Stamp a closure this transaction locked as cancelled, by whom and when.

        Args:
            closure: The closure as `ClosureDay.cancelled` returned it.
            cancelled_by_user_id: The account that cancelled it.

        """
        ...


class ClosureDayQuery(Protocol):
    """What the owner reads of the closure days."""

    def live_between(self, first: date, last: date) -> list[ClosureDay]:
        """Return every live closure from `first` to `last`, both included, by day.

        It takes one statement however many closures there are.
        """
        ...

    def bookings_on(self, branch_id: UUID | None, day: date, limit: int) -> StrandedBookings:
        """Return the bookings that start or end on a day, and the hires due back.

        A booking counts while it is held or confirmed. A hire counts while its
        equipment is still out. Both are read in a number of statements that
        does not grow with how many there are.

        Args:
            branch_id: The collection branch, or None for every branch.
            day: The day that would close.
            limit: The most to list. `total` counts all of them.

        """
        ...
