"""What the counter's dashboard and diary are read as, in small frozen dataclasses.

The query object fills the rows. A collection is a reservation with the lines
it books, and a return is a rental with the units on it. The overview service
then adds what depends on who is asking and on the day, which is whether staff
may mark a collection as not collected, and how late an overdue hire is and
what it has run up. Neither is a table row.

A line of the overview says what is on the booking in a few words, for example
`2 x Bosch GBH 2-26`. The words are built here from the lines or the units, in
the order the booking lists them, so the dashboard and the diary say it alike.

Money stays `Decimal` all the way to the HTTP boundary (BR-22).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final
from uuid import UUID

from app.domain.enums import RentalStatus, ReservationStatus
from app.domain.identity import Branch

QUANTITY_MARK: Final[str] = " x "
SUMMARY_SEPARATOR: Final[str] = ", "


def summary_of(quantities: Iterable[tuple[str, int]]) -> str:
    """Return a few words that say what a booking holds, for example `2 x Bosch GBH 2-26`.

    Args:
        quantities: Each model name with how many of it, in the order to say them.

    """
    return SUMMARY_SEPARATOR.join(
        f"{quantity}{QUANTITY_MARK}{name}" for name, quantity in quantities
    )


@dataclass(frozen=True, slots=True)
class BookedLine:
    """One line of a reservation, as the overview says it.

    Attributes:
        model_name: The name of the model the line books.
        quantity: How many units of it.

    """

    model_name: str
    quantity: int


@dataclass(frozen=True, slots=True)
class CollectionEntry:
    """A reservation a customer comes to collect.

    Attributes:
        reservation_id: The reservation key.
        reference: Its reference.
        status: Where it stands.
        customer_name: The name staff see for the customer.
        customer_phone: The number the branch can reach them on.
        start_date: The first day of the hire.
        end_date: The day the equipment comes back.
        lines: Its lines, in position order.

    """

    reservation_id: UUID
    reference: str
    status: ReservationStatus
    customer_name: str
    customer_phone: str
    start_date: date
    end_date: date
    lines: tuple[BookedLine, ...]

    @property
    def unit_count(self) -> int:
        """Return how many units the reservation books."""
        return sum(line.quantity for line in self.lines)

    @property
    def summary(self) -> str:
        """Return what the reservation books, in a few words."""
        return summary_of((line.model_name, line.quantity) for line in self.lines)


@dataclass(frozen=True, slots=True)
class HiredUnit:
    """One unit on a rental, as the overview needs it.

    Attributes:
        model_name: The name of the model the unit realises.
        late_fee_per_day: The late fee copied onto its reservation line (BR-20).
        is_out: True while the unit is still with the customer.

    """

    model_name: str
    late_fee_per_day: Decimal
    is_out: bool


@dataclass(frozen=True, slots=True)
class ReturnEntry:
    """A rental that is due back, or overdue.

    Attributes:
        rental_id: The rental key.
        reference: Its reference.
        status: Where the hire stands.
        customer_name: The name staff see for the customer.
        customer_phone: The number the branch can reach them on.
        due_back_on: The day it is due back.
        units: Its units, in line order and then tag order.

    """

    rental_id: UUID
    reference: str
    status: RentalStatus
    customer_name: str
    customer_phone: str
    due_back_on: date
    units: tuple[HiredUnit, ...]

    @property
    def items_out(self) -> int:
        """Return how many units are still with the customer."""
        return sum(unit.is_out for unit in self.units)

    @property
    def item_count(self) -> int:
        """Return how many units went out on the hire."""
        return len(self.units)

    @property
    def summary(self) -> str:
        """Return what went out on the hire, in a few words."""
        return summary_of(Counter(unit.model_name for unit in self.units).items())

    def fees_per_day_of_units_out(self) -> tuple[Decimal, ...]:
        """Return the late fee per day of each unit still out."""
        return tuple(unit.late_fee_per_day for unit in self.units if unit.is_out)


@dataclass(frozen=True, slots=True)
class DashboardCounts:
    """The true totals behind the dashboard, however long each list is."""

    collections_due: int
    returns_due: int
    overdue: int
    on_hire: int
    quarantined: int


@dataclass(frozen=True, slots=True)
class DashboardRows:
    """What the query object found for one branch on one day.

    Attributes:
        counts: The true totals.
        collections_due: Confirmed reservations due for collection by today.
        returns_due: Rentals due back today with a unit still out.
        overdue: Rentals due back before today with a unit still out.

    """

    counts: DashboardCounts
    collections_due: tuple[CollectionEntry, ...]
    returns_due: tuple[ReturnEntry, ...]
    overdue: tuple[ReturnEntry, ...]


@dataclass(frozen=True, slots=True)
class DiaryRows:
    """What the query object found for one branch over a run of days.

    Attributes:
        collections: The reservations starting in the run, in date order.
        returns: The rentals due back in the run, in date order.

    """

    collections: tuple[CollectionEntry, ...]
    returns: tuple[ReturnEntry, ...]


@dataclass(frozen=True, slots=True)
class OverdueEntry:
    """An overdue rental, with how late it is and what it has run up.

    Attributes:
        rental: The rental and its units.
        days_overdue: The whole days since it was due back.
        late_fee_accrued: The late fee run up so far, including VAT.

    """

    rental: ReturnEntry
    days_overdue: int
    late_fee_accrued: Decimal


@dataclass(frozen=True, slots=True)
class BranchDashboard:
    """What is due today at one branch, for the counter."""

    branch: Branch
    business_day: date
    counts: DashboardCounts
    collections_due: tuple[CollectionEntry, ...]
    returns_due: tuple[ReturnEntry, ...]
    overdue: tuple[OverdueEntry, ...]


@dataclass(frozen=True, slots=True)
class DiaryCollection:
    """A collection in the diary, and whether the caller may mark it as not collected."""

    entry: CollectionEntry
    can_mark_no_show: bool


@dataclass(frozen=True, slots=True)
class DiaryDay:
    """One day of the diary, with its collections and its returns."""

    business_day: date
    collections: tuple[DiaryCollection, ...]
    returns: tuple[ReturnEntry, ...]


@dataclass(frozen=True, slots=True)
class BranchDiary:
    """The diary of one branch over a run of days."""

    branch: Branch
    days: tuple[DiaryDay, ...]
