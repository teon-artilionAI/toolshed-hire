"""The rental port.

The hire module owns the rental, its items and its charges, and is the only
module that writes them. The repository adds a whole rental at once, with its
items and its charges, so no caller can store half a checkout.

The two reads that return read models sit behind the same port, so a use case
reads what it has just written inside the transaction that wrote it, the way
the booking module does. Each one takes a bounded number of statements however
many units a hire has.

The counter's dashboard and diary are read through a port of their own,
`CounterOverviewQuery`. They write nothing, so they need no unit of work, and
each takes a bounded number of statements however many rows come back.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol
from uuid import UUID

from app.application.booking.read_models import ReservationKey
from app.application.hire.overview_models import DashboardRows, DiaryRows
from app.application.hire.read_models import CheckoutDetail, RentalDetail, RentalKey
from app.domain.rental import Rental


class CounterOverviewQuery(Protocol):
    """What the counter reads about the bookings and hires of one branch."""

    def dashboard(self, branch_id: UUID, today: date, list_limit: int) -> DashboardRows:
        """Return what is due at a branch today.

        Args:
            branch_id: The branch.
            today: The current business day.
            list_limit: The most rows each list holds. The counts are the
                true totals whatever this is.

        """
        ...

    def diary(self, branch_id: UUID, first_day: date, last_day: date) -> DiaryRows:
        """Return the collections and the returns of a branch from one day to another.

        Args:
            branch_id: The branch.
            first_day: The first day of the run.
            last_day: The last day of the run, which is included.

        """
        ...


class RentalRepository(Protocol):
    """Where rentals are stored and where their references come from."""

    def next_reference(self, year: int) -> str:
        """Return the next unused rental reference, for example TSH-H-26-000099.

        The number comes from a database sequence, which never hands one
        number out twice and never takes one back.

        Args:
            year: The calendar year the hire starts in.

        """
        ...

    def add(self, rental: Rental) -> None:
        """Write a new rental, its items and its charges inside the current transaction."""
        ...

    def find_id_for_reservation(self, reservation_id: UUID) -> UUID | None:
        """Return the key of the rental opened from a reservation, or None when there is none."""
        ...

    def find_detail(self, key: RentalKey) -> RentalDetail | None:
        """Return one rental with its items and its charges, or None when there is none."""
        ...

    def find_checkout(self, key: ReservationKey) -> CheckoutDetail | None:
        """Return what the counter needs to check a reservation out, or None when there is none."""
        ...
