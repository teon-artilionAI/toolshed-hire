"""Taking units back and recording a loss, with no database anywhere (BR-29 to BR-31, BR-52).

A return is run against a hire the domain's own checkout put out, so these
pin the moves of the rental's status, what happens to each item, its
allocation and its unit, the refusals and the order they are tried in, and
what a loss charges. The hire is due back on the twelfth of March 2026.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.enums import (
    AssetStatus,
    ChargeStatus,
    ChargeType,
    ConditionGrade,
    ReleaseReason,
    RentalStatus,
    ReservationStatus,
)
from app.domain.errors import NotFound, StateTransitionError, ValidationFailure
from app.domain.loss import record_loss, recovery_after_forfeit
from app.domain.money import Money
from app.domain.returns import ItemReturn, release_allocation_of
from app.domain.settlement import settle_deposit
from tests.support.checkout_domain import ASSISTANT
from tests.support.reservations import NINTH
from tests.support.return_domain import (
    DUE_BACK_ON,
    POLICY,
    TWO_UNITS,
    WORKED_HAMMER,
    a_hire,
    back,
    days_after_due,
    lost,
    on_day,
    returned,
)


class TestTheStatusMoves:
    """OPEN, PARTIALLY_RETURNED, OVERDUE and RETURNED, from the items and the due date."""

    def test_a_rental_out_before_its_due_date_is_open_and_after_it_overdue(self) -> None:
        rental = a_hire().rental
        assert rental.status_on(NINTH) is RentalStatus.OPEN
        assert rental.status_on(DUE_BACK_ON) is RentalStatus.OPEN
        assert rental.status_on(days_after_due(1)) is RentalStatus.OVERDUE

    def test_the_first_unit_back_makes_it_partly_returned_and_the_last_returned(self) -> None:
        hire = a_hire(TWO_UNITS)
        first = returned(hire, NINTH, back(hire, 0))
        assert (first.status_before, hire.rental.status) == (
            RentalStatus.OPEN, RentalStatus.PARTIALLY_RETURNED
        )
        assert (first.closed_the_hire, hire.rental.returned_at) == (False, None)
        assert hire.reservation.status is ReservationStatus.COLLECTED

        last = returned(hire, DUE_BACK_ON, back(hire, 1))
        assert (last.closed_the_hire, hire.rental.status) == (True, RentalStatus.RETURNED)
        assert hire.rental.returned_at is not None
        assert hire.reservation.status is ReservationStatus.RETURNED

    def test_a_unit_still_out_past_its_due_date_keeps_the_rental_overdue(self) -> None:
        hire = a_hire(TWO_UNITS)
        hire.rental.status = RentalStatus.OVERDUE
        returned(hire, days_after_due(1), back(hire, 0))
        assert hire.rental.status is RentalStatus.OVERDUE
        returned(hire, days_after_due(2), back(hire, 1))
        assert hire.rental.status is RentalStatus.RETURNED

    def test_a_settled_rental_stays_settled(self) -> None:
        rental = a_hire().rental
        rental.status = RentalStatus.SETTLED
        assert rental.status_on(days_after_due(9)) is RentalStatus.SETTLED


class TestWhatAReturnDoes:
    """Each unit is recorded, charged, let go and shelved."""

    def test_the_unit_is_recorded_shelved_and_its_allocation_let_go(self) -> None:
        hire = a_hire()
        returns = back(hire, condition_in=ConditionGrade.B, hour_meter_in=500, notes=" Dusty ")
        (closed,) = returned(hire, days_after_due(2), returns).units

        item = closed.item
        assert (item.condition_in, item.hour_meter_in, item.notes, item.days_late) == (
            ConditionGrade.B, 500, "Dusty", 2
        )
        assert (closed.unit_before.status, closed.unit.status) == (
            AssetStatus.ON_HIRE, AssetStatus.AVAILABLE
        )
        assert (closed.unit.condition_grade, closed.unit.hour_meter_reading) == (
            ConditionGrade.B, 500
        )
        (allocation,) = hire.reservation.lines[0].allocations
        assert allocation.release_reason is ReleaseReason.RETURNED

    def test_the_late_fee_is_owed_and_split_for_vat(self) -> None:
        hire = a_hire()
        (closed,) = returned(hire, days_after_due(2), back(hire)).units
        fee = closed.late_fee_charge
        assert fee is not None
        assert (fee.charge_type, fee.status) == (ChargeType.LATE_FEE, ChargeStatus.PENDING)
        assert (fee.amount_ex_vat, fee.vat_amount, fee.amount_inc_vat) == (
            Decimal("208.70"), Decimal("31.30"), Decimal("240.00")
        )
        assert fee.description == "Late fee for 2 days at R120.00 a day, including VAT"

    def test_a_unit_back_on_its_due_date_raises_no_charge(self) -> None:
        hire = a_hire()
        (closed,) = returned(hire, DUE_BACK_ON, back(hire)).units
        assert closed.late_fee_charge is None
        assert len(hire.rental.charges) == 2


class TestWhatAReturnRefuses:
    """The list is checked before anything changes, the unit's standing after it."""

    def test_a_unit_listed_twice_is_refused_by_its_field(self) -> None:
        hire = a_hire()
        with pytest.raises(ValidationFailure) as refused:
            returned(hire, NINTH, [*back(hire), *back(hire)])
        assert refused.value.detail == {"field": "items.1.rental_item_id"}

    def test_a_unit_that_is_not_on_the_rental_is_refused_by_its_field(self) -> None:
        hire = a_hire()
        with pytest.raises(ValidationFailure, match="not on this rental") as refused:
            returned(hire, NINTH, [*back(hire), ItemReturn(uuid4(), ConditionGrade.A)])
        assert refused.value.detail == {"field": "items.1.rental_item_id"}
        assert hire.rental.items[0].is_out()

    def test_a_meter_below_the_one_it_went_out_with_is_refused(self) -> None:
        hire = a_hire()
        hire.rental.items[0].hour_meter_out = 400
        with pytest.raises(ValidationFailure) as refused:
            returned(hire, NINTH, back(hire, hour_meter_in=399))
        assert refused.value.detail == {"field": "items.0.hour_meter_in"}

    def test_a_unit_already_back_is_refused_and_nothing_changes(self) -> None:
        hire = a_hire(TWO_UNITS)
        returned(hire, NINTH, back(hire, 0))
        with pytest.raises(StateTransitionError, match="already back"):
            returned(hire, NINTH, back(hire))
        assert hire.rental.items[1].is_out()

    def test_a_unit_recorded_as_lost_cannot_be_returned(self) -> None:
        hire = a_hire()
        lost(hire, days_after_due(15))
        with pytest.raises(StateTransitionError, match="recorded as lost"):
            returned(hire, days_after_due(16), back(hire))

    def test_an_allocation_the_reservation_does_not_hold_is_a_fault_in_the_caller(self) -> None:
        hire = a_hire()
        other = a_hire()
        with pytest.raises(ValueError, match="does not hold it"):
            release_allocation_of(
                other.reservation, hire.rental.items[0], hire.rental.checked_out_at
            )


class TestALoss:
    """Fourteen days of late fee, the deposit kept, and the rest of the value recovered."""

    def test_the_loss_closes_the_unit_and_raises_three_charges(self) -> None:
        hire = a_hire()
        outcome = lost(hire, days_after_due(15))
        item = outcome.unit.item
        assert (item.is_lost(), item.days_late, item.condition_in) == (True, 15, None)
        assert outcome.unit.unit.status is AssetStatus.LOST
        assert outcome.unit.late_fee_charge is not None
        assert outcome.unit.late_fee_charge.amount_inc_vat == Decimal("1680.00")
        assert outcome.forfeit_charge is not None and outcome.recovery_charge is not None
        assert (outcome.forfeit_charge.amount_inc_vat, outcome.forfeit_charge.status) == (
            Decimal("1200.00"), ChargeStatus.SETTLED
        )
        assert outcome.recovery_charge.amount_inc_vat == Decimal("5300.00")
        assert (outcome.closed_the_hire, hire.rental.status) == (True, RentalStatus.RETURNED)

    def test_a_unit_fourteen_days_late_is_not_yet_lost(self) -> None:
        hire = a_hire()
        with pytest.raises(StateTransitionError, match="not late enough"):
            lost(hire, days_after_due(14))
        assert hire.rental.items[0].is_out()

    def test_a_unit_that_is_not_on_the_rental_is_not_found(self) -> None:
        hire = a_hire()
        day = days_after_due(15)
        with pytest.raises(NotFound, match="could not find that unit"):
            record_loss(
                rental=hire.rental,
                reservation=hire.reservation,
                rental_item_id=uuid4(),
                units=hire.units,
                policy=POLICY,
                recorded_by=ASSISTANT,
                now=on_day(day),
                today=day,
            )

    def test_a_unit_already_back_cannot_be_lost(self) -> None:
        hire = a_hire()
        returned(hire, DUE_BACK_ON, back(hire))
        with pytest.raises(StateTransitionError, match="already back"):
            lost(hire, days_after_due(15))

    @pytest.mark.parametrize(
        ("replacement", "forfeited", "recovered"),
        [("6500.00", "1200.00", "5300.00"), ("800.00", "1200.00", "0.00")],
    )
    def test_the_recovery_is_never_below_nothing_or_above_the_value(
        self, replacement: str, forfeited: str, recovered: str
    ) -> None:
        assert recovery_after_forfeit(
            Money.create(replacement), Money.create(forfeited)
        ) == Money.create(recovered)


def test_a_settlement_after_a_loss_never_repeats_the_number_of_the_forfeit() -> None:
    """A loss while another unit is out, read back as the database orders it, then settled.

    The forfeit is numbered when it is raised. The late fees and the recovery
    are numbered when the deposit settles them, in a later transaction, after
    the charges have been read back in the order the database keeps them.
    """
    cheap_to_be_late = replace(
        WORKED_HAMMER, deposit_amount=Decimal("2000.00"), late_fee_per_day=Decimal("50.00")
    )
    hire = a_hire(((cheap_to_be_late, 2),))
    lost(hire, days_after_due(15), position=0)
    hire.rental.charges.sort(
        key=lambda charge: (
            charge.raised_at,
            charge.payment_reference is None,
            charge.payment_reference or "",
            str(charge.id),
        )
    )
    returned(hire, days_after_due(16), back(hire, 1))
    settle_deposit(hire.rental, settled_by=ASSISTANT, now=on_day(days_after_due(16)))

    references = [
        charge.payment_reference
        for charge in hire.rental.charges
        if charge.payment_reference is not None
    ]
    assert len(references) == len(set(references)) == 5
