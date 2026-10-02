"""The reservation port.

The booking module owns the reservation and its lines and is the only module
that writes them. The repository adds a whole aggregate at once, the
reservation together with its lines, so no caller can store half a booking.

A read of one reservation takes the scope of the reader. The repository puts
that scope in the query itself, so a booking that belongs to another customer
is not found, and there is no step in between at which it was (BR-42).
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.application.booking.read_models import ReservationSummary
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

    def find_summary(self, reservation_id: UUID, scope: OwnerScope) -> ReservationSummary | None:
        """Return one reservation, if it exists and the scope lets the reader see it.

        Args:
            reservation_id: The reservation asked for.
            scope: Whose records the reader may be shown. A restricted scope
                is applied in the query, never after it.

        Returns:
            The summary, or None. None means the same thing whether there is
            no such reservation or it belongs to somebody else.

        """
        ...
