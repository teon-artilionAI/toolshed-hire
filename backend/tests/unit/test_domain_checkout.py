"""Checking a reservation out, with no database anywhere (BR-26 to BR-28).

A confirmed reservation is built by hand with its allocations in place, and the
domain is asked to check it out. These pin when a checkout may happen, what
the counter's list of units has to be, what a checkout makes of the rental,
its items and the units, and that a refused checkout changes nothing. The rule
about the branch is the identity module's and is pinned at the foot of the
file.

The two charges a checkout raises are pinned in test_checkout_charges.py. The
builders are in tests/support/checkout_domain.py.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Final
from uuid import uuid4

import pytest

from app.domain.checkout import (
    AGREEMENT_NOT_SIGNED_MESSAGE,
    UNIT_LISTED_TWICE_MESSAGE,
    UNIT_MISSING_MESSAGE,
    UNIT_NOT_HELD_MESSAGE,
    HandOver,
    collection_refusal,
)
from app.domain.customer_account import REFUSED_FIELD
from app.domain.enums import (
    AssetStatus,
    ConditionGrade,
    ReleaseReason,
    RentalStatus,
    ReservationStatus,
    UserRole,
)
from app.domain.errors import BranchScopeError, StateTransitionError, ValidationFailure
from app.domain.identity import Actor, ensure_branch_scope, within_branch_scope
from app.domain.states.guards import TOO_EARLY_TO_COLLECT_MESSAGE
from tests.support.checkout_domain import (
    ASSISTANT,
    HOUR_METER_ON_FILE,
    NOW,
    ONE_HAMMER,
    RENTAL_REFERENCE,
    a_confirmed,
    checked_out,
    every_unit,
    units_of,
)
from tests.support.reservations import (
    NINTH,
    TODAY,
    a_reservation_in,
    an_allocation,
    refused_and_untouched,
)

TENTH: Final[date] = date(2026, 3, 10)
TWELFTH: Final[date] = date(2026, 3, 12)
HOUR_METER_OUT: Final[int] = 401
UNITS_IN_TWO_LINES: Final[int] = 3


def refused_field_of(failure: ValidationFailure) -> object:
    """Return the field a refusal of the counter's list names."""
    return failure.detail[REFUSED_FIELD]


class TestWhenACheckoutMayHappen:
    """From a confirmed reservation, on or after its first day (BR-26)."""

    @pytest.mark.parametrize(
        ("status", "standing"),
        [
            (ReservationStatus.DRAFT, "is still a draft"),
            (ReservationStatus.HELD, "is on hold"),
            (ReservationStatus.COLLECTED, "has been collected"),
            (ReservationStatus.CANCELLED, "has been cancelled"),
            (ReservationStatus.NO_SHOW, "was not collected"),
            (ReservationStatus.EXPIRED, "has expired"),
            (ReservationStatus.RETURNED, "has been returned"),
        ],
    )
    def test_any_status_but_confirmed_is_refused_in_its_own_words(
        self, status: ReservationStatus, standing: str
    ) -> None:
        sentence = f"This reservation {standing}, so it cannot be collected."
        assert collection_refusal(status, NINTH, TENTH) == sentence

    def test_the_status_is_named_before_the_date(self) -> None:
        refusal = collection_refusal(ReservationStatus.HELD, NINTH, TODAY)
        assert refusal == "This reservation is on hold, so it cannot be collected."

    @pytest.mark.parametrize(
        ("today", "refusal"),
        [(TODAY, TOO_EARLY_TO_COLLECT_MESSAGE), (NINTH, None), (TENTH, None), (TWELFTH, None)],
    )
    def test_a_confirmed_reservation_may_be_collected_from_its_first_day(
        self, today: date, refusal: str | None
    ) -> None:
        assert collection_refusal(ReservationStatus.CONFIRMED, NINTH, today) == refusal

    def test_a_held_reservation_is_refused_and_left_as_it_was(self) -> None:
        reservation = a_reservation_in(ReservationStatus.HELD)
        hand_overs = every_unit(reservation)
        with refused_and_untouched(reservation, StateTransitionError) as refusal:
            checked_out(reservation, hand_overs)
        assert (refusal.value.from_status, refusal.value.to_status) == ("HELD", "COLLECTED")
        assert refusal.value.rule == "BR-26"

    def test_a_checkout_before_the_first_day_is_refused_and_left_as_it_was(self) -> None:
        reservation = a_confirmed()
        with refused_and_untouched(reservation, StateTransitionError) as refusal:
            checked_out(reservation, today=TODAY)
        assert refusal.value.message == TOO_EARLY_TO_COLLECT_MESSAGE
        assert (refusal.value.from_status, refusal.value.to_status) == ("CONFIRMED", "COLLECTED")

    def test_a_unit_that_cannot_go_on_hire_refuses_the_whole_checkout(self) -> None:
        reservation = a_confirmed()
        units = units_of(reservation)
        first = next(iter(units))
        units[first] = replace(units[first], status=AssetStatus.QUARANTINED)
        with refused_and_untouched(reservation, StateTransitionError) as refusal:
            checked_out(reservation, units=units)
        assert refusal.value.message == (
            "Unit TSH-DR-0001 is in quarantine, so it cannot be handed over."
        )


class TestTheListOfUnits:
    """Every unit the reservation holds, once each, and the customer's signature (BR-28)."""

    def test_a_unit_left_out_is_refused_naming_the_list(self) -> None:
        reservation = a_confirmed()
        with refused_and_untouched(reservation, ValidationFailure) as refusal:
            checked_out(reservation, every_unit(reservation)[:-1])
        assert refusal.value.message == UNIT_MISSING_MESSAGE
        assert refused_field_of(refusal.value) == "items"

    def test_a_unit_named_twice_is_refused_naming_the_second_mention(self) -> None:
        reservation = a_confirmed(ONE_HAMMER)
        (only,) = every_unit(reservation)
        with refused_and_untouched(reservation, ValidationFailure) as refusal:
            checked_out(reservation, [only, only])
        assert refusal.value.message == UNIT_LISTED_TWICE_MESSAGE
        assert refused_field_of(refusal.value) == "items.1.allocation_id"

    def test_an_allocation_the_reservation_does_not_hold_is_refused(self) -> None:
        reservation = a_confirmed()
        stranger = HandOver(allocation_id=uuid4(), condition_out=ConditionGrade.A)
        with refused_and_untouched(reservation, ValidationFailure) as refusal:
            checked_out(reservation, [stranger, *every_unit(reservation)])
        assert refusal.value.message == UNIT_NOT_HELD_MESSAGE
        assert refused_field_of(refusal.value) == "items.0.allocation_id"

    def test_an_allocation_already_released_is_not_one_it_holds(self) -> None:
        reservation = a_confirmed(ONE_HAMMER)
        released = an_allocation(
            reservation.lines[0],
            branch_id=reservation.branch_id,
            released_as=ReleaseReason.REALLOCATED,
        )
        reservation.lines[0].allocations.append(released)
        late = HandOver(allocation_id=released.id, condition_out=ConditionGrade.A)
        with refused_and_untouched(reservation, ValidationFailure) as refusal:
            checked_out(reservation, [*every_unit(reservation), late])
        assert refused_field_of(refusal.value) == "items.1.allocation_id"

    def test_an_agreement_that_is_not_signed_is_refused_naming_it(self) -> None:
        reservation = a_confirmed()
        with refused_and_untouched(reservation, ValidationFailure) as refusal:
            checked_out(reservation, agreement_signed=False)
        assert refusal.value.message == AGREEMENT_NOT_SIGNED_MESSAGE
        assert refused_field_of(refusal.value) == "agreement_signed"


class TestWhatACheckoutMakes:
    """The rental, one item per allocation and the units on hire."""

    def test_the_rental_is_open_and_due_back_on_the_end_of_the_reservation(self) -> None:
        reservation = a_confirmed()
        rental = checked_out(reservation).rental
        assert (rental.reference, rental.reservation_id) == (RENTAL_REFERENCE, reservation.id)
        assert (rental.branch_id, rental.status) == (reservation.branch_id, RentalStatus.OPEN)
        assert (rental.checked_out_at, rental.checked_out_by_user_id) == (NOW, ASSISTANT)
        assert rental.due_back_on == reservation.period.end
        assert rental.agreement_signed is True
        assert (rental.returned_at, rental.settled_at) == (None, None)

    def test_every_allocation_becomes_one_item_with_what_the_counter_recorded(self) -> None:
        reservation = a_confirmed()
        hand_overs = every_unit(
            reservation, condition=ConditionGrade.B, accessories="  Case  ", hour_meter=412
        )
        rental = checked_out(reservation, hand_overs).rental
        allocations = {
            allocation.id: allocation
            for line in reservation.lines
            for allocation in line.allocations
        }
        assert len(rental.items) == UNITS_IN_TWO_LINES
        for item in rental.items:
            assert item.asset_id == allocations[item.asset_allocation_id].asset_id
            assert (item.rental_id, item.checked_out_at) == (rental.id, NOW)
            assert (item.condition_out, item.accessories_out, item.hour_meter_out) == (
                ConditionGrade.B, "Case", 412
            )
            assert item.is_out()
        assert rental.items_out() == rental.items

    def test_blank_accessories_are_kept_as_none(self) -> None:
        reservation = a_confirmed(ONE_HAMMER)
        rental = checked_out(reservation, every_unit(reservation, accessories="   ")).rental
        assert rental.items[0].accessories_out is None

    def test_every_unit_goes_on_hire_with_its_condition_and_reading(self) -> None:
        reservation = a_confirmed()
        hand_overs = every_unit(reservation, condition=ConditionGrade.C)
        hand_overs[0] = replace(hand_overs[0], hour_meter_out=HOUR_METER_OUT)
        units = checked_out(reservation, hand_overs).units
        assert {unit.status for unit in units} == {AssetStatus.ON_HIRE}
        assert {unit.condition_grade for unit in units} == {ConditionGrade.C}
        assert sorted(unit.hour_meter_reading or 0 for unit in units) == [
            HOUR_METER_ON_FILE, HOUR_METER_ON_FILE, HOUR_METER_OUT
        ]

    def test_the_reservation_is_collected_and_still_holds_its_units(self) -> None:
        reservation = a_confirmed()
        checked_out(reservation)
        assert reservation.status is ReservationStatus.COLLECTED
        assert reservation.is_fully_allocated()


class TestTheBranch:
    """Counter staff check out at their own branch, and nobody else is scoped (BR-43)."""

    @pytest.mark.parametrize(
        ("role", "own_branch", "allowed"),
        [
            (UserRole.COUNTER_STAFF, True, True),
            (UserRole.COUNTER_STAFF, False, False),
            (UserRole.ADMIN, False, True),
            (UserRole.CUSTOMER, False, True),
        ],
    )
    def test_only_counter_staff_of_another_branch_are_refused(
        self, role: UserRole, own_branch: bool, allowed: bool
    ) -> None:
        branch_id = uuid4()
        scoped = role is UserRole.COUNTER_STAFF
        actor = Actor(
            user_id=uuid4(),
            role=role,
            branch_id=(branch_id if own_branch else uuid4()) if scoped else None,
        )
        assert within_branch_scope(actor, branch_id) is allowed
        if allowed:
            ensure_branch_scope(actor, branch_id)
        else:
            with pytest.raises(BranchScopeError):
                ensure_branch_scope(actor, branch_id)
