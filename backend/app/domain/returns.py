"""Taking units back, which is the return of FR-18, US-23 and BR-29 to BR-31.

The counter names the units that came back, each with the condition it came
back in, its meter reading and what came back with it. For each one the late
fee policy says how many whole days late it is and what that costs (BR-30),
and a late fee is raised when there is one. Its allocation is let go with the
reason RETURNED, and the unit moves back to AVAILABLE through the asset state
model, so it can be booked from that day (US-23). A unit the counter flagged,
or one back in a worse grade than it went out in, goes to QUARANTINED instead
and waits for its damage to be assessed (BR-35, `app.domain.quarantine`).

The rental's status then follows its units (BR-29, BR-52). Once the last unit
is back the rental records when and by whom, and the reservation is closed
through its own state, which moves it to RETURNED.

Every refusal is decided before anything changes. A unit listed twice, a unit
that is not on the rental and a meter reading below the one it went out with
are refused as a `ValidationFailure` naming the field, which the API answers
with 422. A unit that is already back is a `StateTransitionError`, answered
with 409. So a refused return changes nothing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Final
from uuid import UUID

from app.domain.asset_lifecycle import moved
from app.domain.booking import Reservation
from app.domain.catalogue import Asset
from app.domain.charge import Charge
from app.domain.customer_account import REFUSED_FIELD
from app.domain.enums import AssetStatus, ConditionGrade, ReleaseReason, RentalStatus
from app.domain.errors import StateTransitionError, ValidationFailure
from app.domain.money import Money
from app.domain.policies.late_fee import LateFee, LateFeePolicy
from app.domain.quarantine import status_on_return
from app.domain.rental import Rental, RentalItem
from app.domain.return_charges import late_fee_charge

RETURN_RULE: Final[str] = "BR-29"
ITEMS_FIELD: Final[str] = "items"
ITEM_FIELD: Final[str] = "rental_item_id"
METER_FIELD: Final[str] = "hour_meter_in"

ITEM_LISTED_TWICE_MESSAGE: Final[str] = "This unit is already in the list. List each unit once."
ITEM_NOT_ON_RENTAL_MESSAGE: Final[str] = "This unit is not on this rental."
METER_BELOW_OUT_MESSAGE: Final[str] = (
    "The meter reading cannot be lower than the reading the unit went out with."
)
ALREADY_BACK_MESSAGE: Final[str] = "This unit is already back, so it cannot be returned again."
ALREADY_LOST_MESSAGE: Final[str] = (
    "This unit was recorded as lost, so it cannot be returned on this rental."
)


@dataclass(frozen=True, slots=True)
class ItemReturn:
    """What the counter records about one unit as it comes back.

    Attributes:
        rental_item_id: The unit, by the key of its rental item.
        condition_in: The grade it came back in.
        hour_meter_in: The meter reading, for a unit that has a meter.
        accessories_in: What came back with it, or None.
        notes: Anything the counter wants to write about it, or None.
        flagged_for_damage: Whether the counter flagged it for a damage
            assessment, which sends it to quarantine.

    """

    rental_item_id: UUID
    condition_in: ConditionGrade
    hour_meter_in: int | None = None
    accessories_in: str | None = None
    notes: str | None = None
    flagged_for_damage: bool = False


@dataclass(frozen=True, slots=True)
class ClosedUnit:
    """One unit a return or a loss closed, with what it owed and where it went.

    Attributes:
        item: The rental item, now closed.
        unit_before: The unit as it stood, on hire.
        unit: The unit as it stands now.
        late_fee: What the late fee policy said it owes.
        late_fee_charge: The late fee raised, or None when it owed nothing.

    """

    item: RentalItem
    unit_before: Asset
    unit: Asset
    late_fee: LateFee
    late_fee_charge: Charge | None


@dataclass(frozen=True, slots=True)
class ReturnOutcome:
    """What a return did, for the caller to store and to record.

    Attributes:
        units: Every unit taken back.
        status_before: The status of the rental before the return.
        closed_the_hire: True when this return brought the last unit back.

    """

    units: tuple[ClosedUnit, ...]
    status_before: RentalStatus
    closed_the_hire: bool


def return_items(
    *,
    rental: Rental,
    reservation: Reservation,
    returns: Sequence[ItemReturn],
    units: Mapping[UUID, Asset],
    policy: LateFeePolicy,
    returned_by: UUID,
    now: datetime,
    today: date,
) -> ReturnOutcome:
    """Take the named units back, charge what each owes, and move the rental on.

    Args:
        rental: The rental, locked by the caller, with its items and charges.
        reservation: The reservation it was opened from, locked by the caller.
        returns: What the counter recorded for each unit coming back.
        units: The units coming back, by their key, locked by the caller.
        policy: The late fee policy. Nothing else works out a late fee.
        returned_by: The member of staff taking the units back.
        now: The current instant, from the clock.
        today: The current business day, from the clock.

    Raises:
        ValidationFailure: If a unit is listed twice, is not on the rental, or
            has a meter reading below the one it went out with. The detail
            names the field.
        StateTransitionError: If a unit is already back or was recorded as lost.

    """
    paired = _items_returned(rental, returns)
    for item, _back in paired:
        ensure_still_out(item)
    status_before = rental.status
    closed = tuple(
        _take_back(
            rental, reservation, item, back, units[item.asset_id], policy, returned_by, now, today
        )
        for item, back in paired
    )
    return ReturnOutcome(
        units=closed,
        status_before=status_before,
        closed_the_hire=close_if_all_back(rental, reservation, returned_by, now, today),
    )


def ensure_still_out(item: RentalItem) -> None:
    """Refuse a unit that is no longer out, because it came back or was recorded as lost.

    Raises:
        StateTransitionError: Naming the unit's standing.

    """
    if item.is_out():
        return
    raise StateTransitionError(
        ALREADY_LOST_MESSAGE if item.is_lost() else ALREADY_BACK_MESSAGE,
        from_status=AssetStatus.LOST.value if item.is_lost() else RentalStatus.RETURNED.value,
        to_status=RentalStatus.RETURNED.value,
        rule=RETURN_RULE,
    )


def release_allocation_of(reservation: Reservation, item: RentalItem, now: datetime) -> None:
    """Let go of the allocation a unit was handed over under, with the reason RETURNED.

    Raises:
        ValueError: If the reservation does not hold the allocation, which
            means the calling code passed the wrong reservation.

    """
    for line in reservation.lines:
        for allocation in line.allocations:
            if allocation.id == item.asset_allocation_id:
                allocation.release(ReleaseReason.RETURNED, now)
                return
    raise ValueError(
        f"Attempted to release allocation {item.asset_allocation_id} of rental item {item.id} "
        f"through reservation {reservation.reference}, which does not hold it."
    )


def close_if_all_back(
    rental: Rental, reservation: Reservation, closed_by: UUID, now: datetime, today: date
) -> bool:
    """Move the rental to the status its units give it, and close the hire when all are back.

    Returns:
        True when every unit is now back or recorded as lost, and the
        reservation was closed with it.

    """
    rental.status = rental.status_on(today)
    if not rental.is_all_back():
        return False
    rental.returned_at = now
    rental.returned_to_user_id = closed_by
    reservation.close(now=now)
    return True


def late_fee_of(
    rental: Rental, item: RentalItem, policy: LateFeePolicy, closed_on: date
) -> LateFee:
    """Return what the late fee policy says a unit owes on the day it is closed."""
    return policy.late_fee(
        due_back_on=rental.due_back_on,
        returned_on=closed_on,
        fee_per_day=Money.create(item.terms.late_fee_per_day),
    )


def _items_returned(
    rental: Rental, returns: Sequence[ItemReturn]
) -> list[tuple[RentalItem, ItemReturn]]:
    """Pair each unit named with its item on the rental, refusing a list that is wrong.

    Raises:
        ValidationFailure: Naming the field of the first entry that is wrong.

    """
    paired: dict[UUID, tuple[RentalItem, ItemReturn]] = {}
    for index, back in enumerate(returns):
        entry = f"{ITEMS_FIELD}.{index}"
        if back.rental_item_id in paired:
            raise _refused(f"{entry}.{ITEM_FIELD}", ITEM_LISTED_TWICE_MESSAGE)
        item = rental.item_with_id(back.rental_item_id)
        if item is None:
            raise _refused(f"{entry}.{ITEM_FIELD}", ITEM_NOT_ON_RENTAL_MESSAGE)
        if (
            back.hour_meter_in is not None
            and item.hour_meter_out is not None
            and back.hour_meter_in < item.hour_meter_out
        ):
            raise _refused(f"{entry}.{METER_FIELD}", METER_BELOW_OUT_MESSAGE)
        paired[item.id] = (item, back)
    return list(paired.values())


def _take_back(
    rental: Rental,
    reservation: Reservation,
    item: RentalItem,
    back: ItemReturn,
    unit: Asset,
    policy: LateFeePolicy,
    returned_by: UUID,
    now: datetime,
    today: date,
) -> ClosedUnit:
    """Record one unit as back, raise its late fee, let its allocation go and shelve it."""
    late = late_fee_of(rental, item, policy, today)
    accessories = (back.accessories_in or "").strip()
    notes = (back.notes or "").strip()
    item.condition_in = back.condition_in
    item.hour_meter_in = back.hour_meter_in
    item.accessories_in = accessories or None
    item.notes = notes or None
    item.flagged_for_damage = back.flagged_for_damage
    item.returned_at = now
    item.days_late = late.days_late
    charge = None
    if late.is_due():
        charge = late_fee_charge(
            rental=rental, item=item, late_fee=late, raised_by=returned_by, now=now
        )
        rental.charges.append(charge)
    release_allocation_of(reservation, item, now)
    reading = back.hour_meter_in if back.hour_meter_in is not None else unit.hour_meter_reading
    target = status_on_return(item.condition_out, back.condition_in, back.flagged_for_damage)
    shelved = replace(
        moved(unit, target),
        condition_grade=back.condition_in,
        hour_meter_reading=reading,
    )
    return ClosedUnit(
        item=item, unit_before=unit, unit=shelved, late_fee=late, late_fee_charge=charge
    )


def _refused(field: str, message: str) -> ValidationFailure:
    """Return the refusal of one field of the counter's list."""
    return ValidationFailure(message, {REFUSED_FIELD: field}, rule=RETURN_RULE)
