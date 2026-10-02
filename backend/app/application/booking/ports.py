"""The reservation port.

The booking module owns the reservation and its lines and is the only module
that writes them. The repository adds a whole aggregate at once, the
reservation together with its lines, so no caller can store half a booking.

Every lookup of one reservation takes the scope of the caller. The repository
puts that scope in the query itself, so a booking that belongs to another
customer is not found, and there is no step in between at which it was
(BR-42).

A reservation that is going to change is read with `find_for_update`, which
locks its row until the unit of work ends. Two requests that act on one
booking at the same moment therefore take turns, and the second one sees what
the first one did.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.application.booking.read_models import (
    ReservationDetail,
    ReservationKey,
    ReservationPage,
    ReservationSearch,
)
from app.application.ownership import OwnerScope
from app.domain.booking import Reservation


class ReservationRepository(Protocol):
    """Where reservations are stored and where their references come from."""

    def add(self, reservation: Reservation) -> None:
        """Write a new reservation and its lines inside the current transaction."""
        ...

    def next_reference(self, year: int) -> str:
        """Return the next unused reservation reference, for example TSH-R-26-000124.

        The number comes from a database sequence. Deriving it from a row count
        would hand two concurrent bookings the same reference.

        Args:
            year: The calendar year the hire starts in.

        """
        ...

    def find_for_update(self, key: ReservationKey, scope: OwnerScope) -> Reservation | None:
        """Return one reservation with its lines and allocations, locked for a change.

        Args:
            key: The reservation asked for, by its key or its reference.
            scope: Whose records the caller may act on. A restricted scope is
                applied in the query, never after it.

        Returns:
            The aggregate, or None. None means the same thing whether there is
            no such reservation or it belongs to somebody else.

        """
        ...

    def save(self, reservation: Reservation) -> None:
        """Write the status, the dates of its moves and the releases of a reservation.

        The lines and their figures are never rewritten (BR-20). An allocation
        made by a hold is written by the asset repository, so this writes only
        the release of one that already exists.
        """
        ...

    def lock_due_holds(self, now: datetime, limit: int) -> list[Reservation]:
        """Lock and return up to `limit` held reservations whose hold has run out.

        The oldest expiry comes first. A row another transaction is changing
        is waited for and then read again, so a reservation that was confirmed
        or expired in the meantime is not returned.
        """
        ...

    def find_detail(self, key: ReservationKey, scope: OwnerScope) -> ReservationDetail | None:
        """Return one reservation as a read model, if the scope lets the caller see it."""
        ...

    def search(self, search: ReservationSearch, scope: OwnerScope) -> ReservationPage:
        """Return one page of the reservations the scope lets the caller see, newest first."""
        ...
