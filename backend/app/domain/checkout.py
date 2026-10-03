"""Checking a reservation out, which is the moment a booking becomes a hire (BR-26 to BR-28).

A rental may only be opened from a confirmed reservation, on or after the
first day of its hire, by staff at the collection branch (BR-26). The branch
is the caller's to check, because it is about who is asking. The status and
the date are checked here, and each refusal is a `StateTransitionError`, which
the API answers with 409 and a sentence that says which of the two it was.

The counter lists every unit it hands over, by its allocation, with the
condition it went out in, what went with it and the meter reading. Every
active allocation of the reservation has to be listed exactly once. Each one
becomes one rental item (BR-28), and each unit moves to ON_HIRE through the
asset state model. The customer signs the hire agreement first.

The money is the hire charge and the deposit hold, which are raised by
`app.domain.checkout_charges`.

Nothing is changed until every check has passed. The reservation moves to
COLLECTED last, through its own state, so a refused checkout leaves the
reservation, the units and everything else exactly as they were.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Final
from uuid import UUID

from app.domain.asset_lifecycle import moved
from app.domain.availability import AssetAllocation
from app.domain.booking import Reservation
from app.domain.booking_line import ReservationLine
from app.domain.catalogue import Asset
from app.domain.checkout_charges import deposit_hold_charge, deposit_to_hold, hire_charge
from app.domain.customer_account import REFUSED_FIELD
from app.domain.enums import AssetStatus, ConditionGrade, ReservationStatus
from app.domain.errors import StateTransitionError, ValidationFailure
from app.domain.rental import Rental, RentalItem, UnitTerms
from app.domain.states import state_for
from app.domain.states.base import COLLECT_MOVE, COLLECTED, refusal_sentence
from app.domain.states.guards import TOO_EARLY_TO_COLLECT_MESSAGE

CHECKOUT_RULE: Final[str] = "BR-26"
HAND_OVER_RULE: Final[str] = "BR-28"

# The names of the fields a refusal of the counter's list points at.
ITEMS_FIELD: Final[str] = "items"
ALLOCATION_FIELD: Final[str] = "allocation_id"
AGREEMENT_FIELD: Final[str] = "agreement_signed"

UNIT_MISSING_MESSAGE: Final[str] = (
    "Every unit on this reservation is handed over at once. One or more is missing from "
    "the list."
)
UNIT_LISTED_TWICE_MESSAGE: Final[str] = "This unit is already in the list. List each unit once."
UNIT_NOT_HELD_MESSAGE: Final[str] = "This unit is not held for this reservation."
AGREEMENT_NOT_SIGNED_MESSAGE: Final[str] = (
    "The customer has to sign the hire agreement before the equipment is handed over."
)
ALREADY_CHECKED_OUT_MESSAGE: Final[str] = "This reservation has already been checked out."


@dataclass(frozen=True, slots=True)
class HandOver:
    """What the counter records about one unit as it goes out.

    Attributes:
        allocation_id: The allocation the unit is held under.
        condition_out: The grade the unit goes out in.
        accessories_out: What goes out with it, or None.
        hour_meter_out: The meter reading, for a unit that has a meter.

    """

    allocation_id: UUID
    condition_out: ConditionGrade
    accessories_out: str | None = None
    hour_meter_out: int | None = None


@dataclass(frozen=True, slots=True)
class HandedOverUnit:
    """One allocation of the reservation paired with what the counter recorded for it."""

    line: ReservationLine
    allocation: AssetAllocation
    hand_over: HandOver


@dataclass(frozen=True, slots=True)
class Checkout:
    """What a checkout produced, for the caller to store.

    Attributes:
        rental: The new rental, with its items and its two charges.
        units: Every unit handed over, now ON_HIRE, with its condition and
            its meter reading as they went out.

    """

    rental: Rental
    units: tuple[Asset, ...]


def collection_refusal(status: ReservationStatus, start_date: date, today: date) -> str | None:
    """Return why a reservation cannot be collected today, or None when it can (BR-26).

    Args:
        status: Where the reservation stands.
        start_date: The first day of its hire.
        today: The current business day, from the clock.

    Returns:
        The sentence of the first refusal, which is the status before the
        date, or None.

    """
    if not state_for(status).permits(COLLECT_MOVE):
        return refusal_sentence(status, COLLECTED)
    if today < start_date:
        return TOO_EARLY_TO_COLLECT_MESSAGE
    return None


def ensure_collectable(reservation: Reservation, today: date) -> None:
    """Refuse a checkout of a reservation that is not confirmed or whose hire has not started.

    Raises:
        StateTransitionError: Naming the status held and COLLECTED, with the
            sentence of `collection_refusal`.

    """
    refusal = collection_refusal(reservation.status, reservation.period.start, today)
    if refusal is not None:
        raise StateTransitionError(
            refusal,
            from_status=reservation.status.value,
            to_status=ReservationStatus.COLLECTED.value,
            rule=CHECKOUT_RULE,
        )


def units_handed_over(
    reservation: Reservation, hand_overs: Sequence[HandOver]
) -> list[HandedOverUnit]:
    """Pair every active allocation of the reservation with what the counter recorded for it.

    Raises:
        ValidationFailure: If a unit is listed twice, if a listed allocation
            is not one the reservation holds, or if an allocation it holds is
            left out. The detail names the field.

    """
    active = {
        allocation.id: (line, allocation)
        for line in reservation.lines
        for allocation in line.active_allocations()
    }
    paired: dict[UUID, HandedOverUnit] = {}
    for index, hand_over in enumerate(hand_overs):
        field = f"{ITEMS_FIELD}.{index}.{ALLOCATION_FIELD}"
        if hand_over.allocation_id in paired:
            raise _refused(field, UNIT_LISTED_TWICE_MESSAGE)
        found = active.get(hand_over.allocation_id)
        if found is None:
            raise _refused(field, UNIT_NOT_HELD_MESSAGE)
        line, allocation = found
        paired[allocation.id] = HandedOverUnit(
            line=line, allocation=allocation, hand_over=hand_over
        )
    if len(paired) < len(active):
        raise _refused(ITEMS_FIELD, UNIT_MISSING_MESSAGE)
    return list(paired.values())


def ensure_agreement_signed(agreement_signed: bool) -> None:
    """Refuse a checkout the customer has not signed the hire agreement for.

    Raises:
        ValidationFailure: Naming the field.

    """
    if not agreement_signed:
        raise _refused(AGREEMENT_FIELD, AGREEMENT_NOT_SIGNED_MESSAGE)


def check_out(
    *,
    reservation: Reservation,
    hand_overs: Sequence[HandOver],
    agreement_signed: bool,
    reference: str,
    model_names: Mapping[UUID, str],
    units: Mapping[UUID, Asset],
    checked_out_by: UUID,
    now: datetime,
    today: date,
) -> Checkout:
    """Open the rental of a confirmed reservation and move its units on hire.

    Args:
        reservation: The reservation, locked by the caller.
        hand_overs: What the counter recorded for each unit.
        agreement_signed: Whether the customer signed the hire agreement.
        reference: The reference the rental is given.
        model_names: The name of each model on the reservation, by its key.
        units: Every unit the reservation holds, by its key.
        checked_out_by: The member of staff handing the equipment over.
        now: The current instant, from the clock.
        today: The current business day, from the clock.

    Raises:
        StateTransitionError: If the reservation is not confirmed, its hire
            has not started, or a unit cannot go out on hire.
        ValidationFailure: If the list of units is wrong or the agreement is
            not signed. The detail names the field.

    """
    ensure_collectable(reservation, today)
    handed = units_handed_over(reservation, hand_overs)
    ensure_agreement_signed(agreement_signed)
    on_hire = tuple(
        _put_on_hire(units[unit.allocation.asset_id], unit.hand_over) for unit in handed
    )
    deposit = deposit_to_hold(unit.line.deposit_snapshot for unit in handed)
    rental = Rental(
        reference=reference,
        reservation_id=reservation.id,
        branch_id=reservation.branch_id,
        checked_out_at=now,
        checked_out_by_user_id=checked_out_by,
        due_back_on=reservation.period.end,
        deposit_held=deposit.amount,
        agreement_signed=agreement_signed,
    )
    rental.items = [_item_of(rental, unit, now) for unit in handed]
    rental.charges = [
        hire_charge(
            rental=rental,
            reservation=reservation,
            units_by_line=Counter(unit.line.id for unit in handed),
            model_names=model_names,
            raised_by=checked_out_by,
        ),
        deposit_hold_charge(rental=rental, deposit=deposit, raised_by=checked_out_by),
    ]
    reservation.collect(today=today)
    return Checkout(rental=rental, units=on_hire)


def _refused(field: str, message: str) -> ValidationFailure:
    """Return the refusal of one field of the counter's list."""
    return ValidationFailure(message, {REFUSED_FIELD: field}, rule=HAND_OVER_RULE)


def _put_on_hire(asset: Asset, hand_over: HandOver) -> Asset:
    """Return a unit moved to ON_HIRE, carrying the condition and the reading it went out with."""
    on_hire = moved(asset, AssetStatus.ON_HIRE)
    reading = (
        hand_over.hour_meter_out
        if hand_over.hour_meter_out is not None
        else asset.hour_meter_reading
    )
    return replace(on_hire, condition_grade=hand_over.condition_out, hour_meter_reading=reading)


def _item_of(rental: Rental, unit: HandedOverUnit, now: datetime) -> RentalItem:
    """Return the rental item one handed over allocation becomes (BR-28)."""
    accessories = (unit.hand_over.accessories_out or "").strip()
    return RentalItem(
        rental_id=rental.id,
        asset_allocation_id=unit.allocation.id,
        asset_id=unit.allocation.asset_id,
        condition_out=unit.hand_over.condition_out,
        checked_out_at=now,
        terms=UnitTerms(
            late_fee_per_day=unit.line.late_fee_per_day_snapshot,
            deposit=unit.line.deposit_snapshot,
            replacement_value=unit.line.replacement_value_snapshot,
        ),
        hour_meter_out=unit.hand_over.hour_meter_out,
        accessories_out=accessories or None,
    )
