"""The reservation port.

The booking module owns the reservation and its lines and is the only module
that writes them. The repository adds a whole aggregate at once, the
reservation together with its lines, so no caller can store half a booking.
"""

from __future__ import annotations

from typing import Protocol

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
