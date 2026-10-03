"""The two charges a checkout raises, with no database anywhere (BR-20, BR-27).

The hire charge is the subtotal and the VAT already stored on the reservation,
and is never worked out again. The deposit hold is one unit's deposit for
every unit collected, added up unit by unit, with no VAT. Both are paid at the
counter. These pin the figures, the attribution, the settlement references and
the description a customer reads beside the hire.

The hire is the worked example of the reservation tests, two rotary hammers
and one concrete mixer for three days. The builders are in
tests/support/checkout_domain.py.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

from app.domain.checkout_charges import (
    DEPOSIT_HOLD_DESCRIPTION,
    deposit_to_hold,
    hire_description,
)
from app.domain.enums import ChargeStatus, ChargeType, ReservationStatus
from app.domain.money import Money
from app.domain.policies import FixedRatePricingPolicy
from tests.support.checkout_domain import (
    ASSISTANT,
    NO_DISCOUNT,
    NOW,
    ONE_HAMMER,
    RENTAL_REFERENCE,
    a_confirmed,
    checked_out,
    hold_every_unit,
)
from tests.support.reservations import HAMMER, MIXER, TWO_LINES, a_draft

TEN_PERCENT: Final[Decimal] = Decimal("10.00")


class TestTheHireCharge:
    """The figures stored on the reservation, paid at the counter (BR-20)."""

    def test_the_hire_charge_is_the_subtotal_and_the_vat_stored_on_the_reservation(self) -> None:
        reservation = a_confirmed()
        hire, _deposit = checked_out(reservation).rental.charges
        assert hire.charge_type is ChargeType.HIRE
        assert (hire.amount_ex_vat, hire.vat_rate, hire.vat_amount) == (
            Decimal("3030.00"), Decimal("15.00"), Decimal("454.50")
        )
        assert hire.amount_inc_vat == reservation.estimated_total_inc_vat == Decimal("3484.50")
        assert hire.rental_item_id is None

    def test_the_hire_charge_is_never_worked_out_again(self) -> None:
        """A reservation priced at a fixed R100.00 a unit is charged that."""
        reservation = a_draft(*TWO_LINES)
        reservation.price_with(FixedRatePricingPolicy(Money.create("100.00")), NO_DISCOUNT)
        hold_every_unit(reservation)
        reservation.status = ReservationStatus.CONFIRMED
        hire, _deposit = checked_out(reservation).rental.charges
        assert (hire.amount_ex_vat, hire.vat_amount) == (
            reservation.subtotal_ex_vat().amount, reservation.vat_amount
        )
        assert hire.amount_ex_vat == Decimal("300.00")

    def test_a_hire_of_one_unit_puts_the_hire_charge_on_its_item(self) -> None:
        rental = checked_out(a_confirmed(ONE_HAMMER)).rental
        hire, deposit = rental.charges
        assert hire.rental_item_id == rental.items[0].id
        assert deposit.rental_item_id is None

    def test_both_charges_are_settled_at_the_counter_with_a_numbered_reference(self) -> None:
        charges = checked_out(a_confirmed()).rental.charges
        assert [charge.charge_type for charge in charges] == [
            ChargeType.HIRE, ChargeType.DEPOSIT_HOLD
        ]
        assert {charge.status for charge in charges} == {ChargeStatus.SETTLED}
        assert {charge.settled_at for charge in charges} == {NOW}
        assert {charge.raised_by_user_id for charge in charges} == {ASSISTANT}
        assert [charge.payment_reference for charge in charges] == [
            f"SIM-{RENTAL_REFERENCE}-01", f"SIM-{RENTAL_REFERENCE}-02"
        ]


class TestTheDeposit:
    """The deposit copied onto each line, once for every unit collected (BR-27)."""

    def test_the_deposit_is_added_up_unit_by_unit(self) -> None:
        deposits = [Decimal("1200.00"), Decimal("1200.00"), Decimal("2000.00")]
        assert deposit_to_hold(deposits) == Money.create("4400.00")

    def test_no_unit_holds_no_deposit(self) -> None:
        assert deposit_to_hold([]) == Money.create("0.00")

    def test_the_sum_is_rounded_to_the_cent_as_a_charge_is_written(self) -> None:
        assert deposit_to_hold([Decimal("0.005")]) == Money.create("0.01")

    def test_the_rental_holds_the_deposit_of_every_unit_of_every_line(self) -> None:
        rental = checked_out(a_confirmed()).rental
        _hire, deposit = rental.charges
        assert rental.deposit_held == Decimal("4400.00")
        assert (deposit.charge_type, deposit.description) == (
            ChargeType.DEPOSIT_HOLD, DEPOSIT_HOLD_DESCRIPTION
        )
        assert (deposit.amount_ex_vat, deposit.vat_rate, deposit.vat_amount) == (
            Decimal("4400.00"), Decimal("0.00"), Decimal("0.00")
        )
        assert deposit.amount_inc_vat == Decimal("4400.00")


class TestTheHireDescription:
    """What the customer reads beside the hire charge."""

    def test_one_unit_of_one_model(self) -> None:
        assert hire_description([("Bosch GBH 2-26", 1)], 4, NO_DISCOUNT) == "Bosch GBH 2-26, 4 days"

    def test_several_units_and_several_models(self) -> None:
        described = hire_description([(HAMMER.name, 2), (MIXER.name, 1)], 3, NO_DISCOUNT)
        assert described == f"2 x {HAMMER.name}; {MIXER.name}, 3 days"

    def test_one_day_is_written_as_one_day(self) -> None:
        assert hire_description([("Plate Compactor", 1)], 1, NO_DISCOUNT).endswith(", 1 day")

    def test_a_trade_discount_is_named(self) -> None:
        described = hire_description([(HAMMER.name, 1)], 3, TEN_PERCENT)
        assert described == f"{HAMMER.name}, 3 days, less 10.00% trade discount"

    def test_a_list_too_long_for_the_column_is_written_as_a_count(self) -> None:
        lines = [(f"Model with a long descriptive name number {index}", 2) for index in range(8)]
        assert hire_description(lines, 5, NO_DISCOUNT) == "Hire of 16 units, 5 days"

    def test_the_checkout_describes_the_discounted_hire_it_charges(self) -> None:
        reservation = a_confirmed(discount=TEN_PERCENT)
        hire, _deposit = checked_out(reservation).rental.charges
        assert hire.description == (
            f"2 x {HAMMER.name}; {MIXER.name}, 3 days, less 10.00% trade discount"
        )
        assert hire.amount_ex_vat == reservation.subtotal_ex_vat().amount
