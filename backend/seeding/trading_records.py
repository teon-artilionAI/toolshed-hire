"""The records the season planner works with, and the numbering of the hires it plans.

Nothing here touches a database. `FleetUnit` and `CustomerChoice` are what the
planner is handed. `PlannedHire` and the two records inside it are what it
hands back, everything decided about a hire before the domain runs it.

The references come last. They sit in a reserved range at the top of each
documented format, so they can never meet a number the live sequences hand
out. Reservations count up from TSH-R-26-900001 in the order they were booked,
rentals from TSH-H-26-900001 in the order they were collected, and damage
reports from TSH-D-26-90001 in the order they were filed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Final
from uuid import UUID

from app.domain.booking_reference import format_reference
from app.domain.damage import format_damage_reference
from app.domain.money import Money
from app.domain.period import BookingPeriod
from app.domain.rental import format_rental_reference
from seeding.trading_damage import DamagePlan
from seeding.trading_times import BookingTimes

FIRST_RESERVATION_NUMBER: Final[int] = 900001
FIRST_RENTAL_NUMBER: Final[int] = 900001
FIRST_DAMAGE_NUMBER: Final[int] = 90001
# The last number of each range, the largest the documented format can hold.
LAST_RESERVATION_NUMBER: Final[int] = 999999
LAST_RENTAL_NUMBER: Final[int] = 999999
LAST_DAMAGE_NUMBER: Final[int] = 99999
HISTORY_YEAR: Final[int] = 2026
UNNUMBERED: Final[str] = ""


@dataclass(frozen=True, slots=True)
class FleetUnit:
    """One unit the history may put out on hire, as the database holds it."""

    asset_id: UUID
    asset_tag: str
    sku: str
    category_code: str
    branch_code: str
    acquired_on: date
    replacement_value: Money


@dataclass(frozen=True, slots=True)
class CustomerChoice:
    """One customer the history may hire to, how often they hire and where they registered."""

    key: str
    branch_code: str
    weight: int
    has_login: bool


@dataclass(frozen=True, slots=True)
class PlannedLine:
    """One model on a planned hire and the units of it that went out."""

    sku: str
    asset_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class PlannedDamage:
    """The one unit of a hire that came back damaged, and when its report was filed and closed."""

    asset_id: UUID
    plan: DamagePlan
    reported_at: datetime
    resolved_at: datetime
    reference: str = UNNUMBERED


@dataclass(frozen=True, slots=True)
class PlannedHire:
    """Everything decided about one hire before the domain runs it.

    Attributes:
        branch_code: The branch the units went out from.
        customer_key: Who hired, by the key of their `CustomerChoice`.
        booked_online: True when the customer booked through their own login.
        lines: The models and the units of each that went out.
        period: The half open hire period, due back on its end.
        times: When it was booked, confirmed and collected.
        returned_on: The day the units came back, the due day or later.
        returned_at: When on that day they came back.
        damage: The unit that came back damaged, or None.
        reservation_reference: The reservation reference, once numbered.
        rental_reference: The rental reference, once numbered.

    """

    branch_code: str
    customer_key: str
    booked_online: bool
    lines: tuple[PlannedLine, ...]
    period: BookingPeriod
    times: BookingTimes
    returned_on: date
    returned_at: datetime
    damage: PlannedDamage | None
    reservation_reference: str = UNNUMBERED
    rental_reference: str = UNNUMBERED


# The first and the last reference of each reserved range, as the formats write them.
RESERVATION_RANGE: Final[tuple[str, str]] = (
    format_reference(HISTORY_YEAR, FIRST_RESERVATION_NUMBER),
    format_reference(HISTORY_YEAR, LAST_RESERVATION_NUMBER),
)
RENTAL_RANGE: Final[tuple[str, str]] = (
    format_rental_reference(HISTORY_YEAR, FIRST_RENTAL_NUMBER),
    format_rental_reference(HISTORY_YEAR, LAST_RENTAL_NUMBER),
)
DAMAGE_RANGE: Final[tuple[str, str]] = (
    format_damage_reference(HISTORY_YEAR, FIRST_DAMAGE_NUMBER),
    format_damage_reference(HISTORY_YEAR, LAST_DAMAGE_NUMBER),
)


def numbered(hires: Sequence[PlannedHire]) -> tuple[PlannedHire, ...]:
    """Hand out the references in the order of booking, collection and report.

    Raises:
        ValueError: If the season holds more hires or reports than a reserved
            range has numbers for, which only a change to the demand figures
            could cause.

    """
    _ensure_fits(len(hires), FIRST_RESERVATION_NUMBER, LAST_RESERVATION_NUMBER, "hires")
    by_booking = sorted(hires, key=lambda hire: (hire.times.booked_at, hire.branch_code))
    with_reservation = [
        replace(hire, reservation_reference=format_reference(HISTORY_YEAR, number))
        for number, hire in enumerate(by_booking, start=FIRST_RESERVATION_NUMBER)
    ]
    by_collection = sorted(
        with_reservation,
        key=lambda hire: (hire.times.checked_out_at, hire.reservation_reference),
    )
    rental_numbers = {
        hire.reservation_reference: number
        for number, hire in enumerate(by_collection, start=FIRST_RENTAL_NUMBER)
    }
    reports = sorted(
        (hire.damage.reported_at, hire.reservation_reference)
        for hire in with_reservation
        if hire.damage is not None
    )
    _ensure_fits(len(reports), FIRST_DAMAGE_NUMBER, LAST_DAMAGE_NUMBER, "damage reports")
    damage_numbers = {
        reference: number
        for number, (_reported_at, reference) in enumerate(reports, start=FIRST_DAMAGE_NUMBER)
    }
    return tuple(
        _with_references(hire, rental_numbers, damage_numbers) for hire in with_reservation
    )


def _with_references(
    hire: PlannedHire, rental_numbers: Mapping[str, int], damage_numbers: Mapping[str, int]
) -> PlannedHire:
    """Return a hire carrying its rental reference and, when it has one, its report's."""
    damage = hire.damage
    if damage is not None:
        number = damage_numbers[hire.reservation_reference]
        damage = replace(damage, reference=format_damage_reference(HISTORY_YEAR, number))
    return replace(
        hire,
        rental_reference=format_rental_reference(
            HISTORY_YEAR, rental_numbers[hire.reservation_reference]
        ),
        damage=damage,
    )


def _ensure_fits(count: int, first: int, last: int, what: str) -> None:
    """Refuse a season with more of something than its reserved range can number.

    Raises:
        ValueError: Naming what overflowed and the size of its range.

    """
    if count > last - first + 1:
        raise ValueError(
            f"Attempted to number {count} {what} from {first}, and the reserved range ends at "
            f"{last}. Lower the demand in seeding/trading_demand.py."
        )
