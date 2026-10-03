"""The rental repository of the in memory unit of work, as far as the lazy sweep needs it.

The sweep marks hires overdue through `lock_due_overdue` and `save`, so every
use case that runs the sweep in a unit test needs those two. They are kept to
what the sweep asks. The returns, the losses and the reads of a rental run
against the in memory SQL database through the routes, and against PostgreSQL
in tests/integration, because their rules are proved there with the real
statements.

`stale_overdue_query` on the store makes the query return every rental that is
not settled, the way a row read before another transaction committed would
be, so a test can prove the sweep asks the domain again once it holds the lock.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Final

from app.domain.enums import RentalStatus
from app.domain.rental import Rental

if TYPE_CHECKING:
    from tests.support.memory import MemoryStore, Records

# The statuses the sweep may move a rental to OVERDUE from.
OVERDUE_FROM: Final[frozenset[RentalStatus]] = frozenset(
    {RentalStatus.OPEN, RentalStatus.PARTIALLY_RETURNED}
)


class MemoryRentals:
    """The rental repository over the working copy, for the sweep."""

    def __init__(self, store: MemoryStore, working: Records) -> None:
        """Bind to the store and to the working copy of one transaction."""
        self._store = store
        self._working = working

    def lock_due_overdue(self, today: date, limit: int) -> list[Rental]:
        """Return up to `limit` rentals with a unit out past their due date, earliest due first."""
        due = [
            rental
            for rental in self._working.rentals
            if self._store.stale_overdue_query
            or (
                rental.returned_at is None
                and rental.due_back_on < today
                and rental.status in OVERDUE_FROM
            )
        ]
        return sorted(due, key=lambda rental: (rental.due_back_on, str(rental.id)))[:limit]

    def save(self, rental: Rental) -> None:
        """Keep the rental in place of the one with its key."""
        self._working.rentals = [
            rental if stored.id == rental.id else stored for stored in self._working.rentals
        ]


__all__ = ["MemoryRentals"]
