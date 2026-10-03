"""The rental, its items and its charges, with no database anywhere.

A rental is a plain dataclass with its items and its charges. These pin the
reference it is given, which items are still out, and the rules a charge keeps
however it was built, that its amounts add up, that a deposit movement carries
no VAT, that it is rounded once as it is written, and that its description
fits the column it is stored in.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Final
from uuid import uuid4

import pytest

from app.domain.charge import Charge, payment_reference
from app.domain.enums import ChargeStatus, ChargeType, ConditionGrade, RentalStatus
from app.domain.money import Money
from app.domain.rental import Rental, RentalItem, UnitTerms, format_rental_reference

NOW: Final[datetime] = datetime(2026, 3, 9, 6, 30, tzinfo=UTC)
LATER: Final[datetime] = datetime(2026, 3, 12, 7, 40, tzinfo=UTC)
FIFTEEN_PERCENT: Final[Decimal] = Decimal("15.00")
NONE_PERCENT: Final[Decimal] = Decimal("0.00")
TOO_LONG: Final[int] = 201


def a_charge(**changes: object) -> Charge:
    """Return a settled hire charge whose figures agree, with some members replaced."""
    fields: dict[str, object] = {
        "rental_id": uuid4(),
        "charge_type": ChargeType.HIRE,
        "description": "Bosch GBH 2-26, 4 days",
        "amount_ex_vat": Decimal("1120.00"),
        "vat_rate": FIFTEEN_PERCENT,
        "vat_amount": Decimal("168.00"),
        "amount_inc_vat": Decimal("1288.00"),
        "status": ChargeStatus.SETTLED,
        "raised_at": NOW,
        "raised_by_user_id": uuid4(),
    }
    fields.update(changes)
    return Charge(**fields)


def an_item(rental: Rental, returned_at: datetime | None = None) -> RentalItem:
    """Return one item of a rental, out unless a return time is given."""
    return RentalItem(
        rental_id=rental.id,
        asset_allocation_id=uuid4(),
        asset_id=uuid4(),
        condition_out=ConditionGrade.A,
        checked_out_at=NOW,
        terms=UnitTerms(
            late_fee_per_day=Decimal("120.00"),
            deposit=Decimal("1200.00"),
            replacement_value=Decimal("4200.00"),
        ),
        returned_at=returned_at,
    )


class TestTheRental:
    """Its reference and which of its units are still out."""

    def test_the_reference_is_written_like_the_worked_example(self) -> None:
        assert format_rental_reference(2026, 98) == "TSH-H-26-000098"
        assert format_rental_reference(2031, 123456) == "TSH-H-31-123456"

    def test_a_new_rental_is_open_and_owes_nothing(self) -> None:
        rental = Rental(
            reference="TSH-H-26-000099",
            reservation_id=uuid4(),
            branch_id=uuid4(),
            checked_out_at=NOW,
            checked_out_by_user_id=uuid4(),
            due_back_on=date(2026, 3, 12),
            deposit_held=Decimal("1200.00"),
            agreement_signed=True,
        )
        assert rental.status is RentalStatus.OPEN
        assert (rental.deposit_withheld, rental.deposit_refunded, rental.balance_due) == (
            Decimal("0.00"), Decimal("0.00"), Decimal("0.00")
        )
        out = an_item(rental)
        back = an_item(rental, returned_at=LATER)
        rental.items = [out, back]
        assert (out.is_out(), back.is_out()) == (True, False)
        assert rental.items_out() == [out]


class TestACharge:
    """The rules a charge keeps however it was built (BR-22, BR-23)."""

    def test_a_charge_whose_figures_agree_is_built(self) -> None:
        assert a_charge().amount_inc_vat == Decimal("1288.00")

    def test_a_total_that_is_not_the_two_amounts_added_is_refused(self) -> None:
        with pytest.raises(ValueError, match="claims to total"):
            a_charge(amount_inc_vat=Decimal("1288.01"))

    @pytest.mark.parametrize(
        "charge_type",
        [ChargeType.DEPOSIT_HOLD, ChargeType.DEPOSIT_RELEASE, ChargeType.DEPOSIT_FORFEIT],
    )
    def test_a_deposit_movement_with_vat_is_refused(self, charge_type: ChargeType) -> None:
        with pytest.raises(ValueError, match="carries none"):
            a_charge(charge_type=charge_type)

    def test_a_deposit_movement_without_vat_is_built(self) -> None:
        charge = a_charge(
            charge_type=ChargeType.DEPOSIT_RELEASE,
            amount_ex_vat=Decimal("-960.00"),
            vat_rate=NONE_PERCENT,
            vat_amount=Decimal("0.00"),
            amount_inc_vat=Decimal("-960.00"),
        )
        assert charge.amount_inc_vat == Decimal("-960.00")

    @pytest.mark.parametrize("description", ["", "   ", "x" * TOO_LONG])
    def test_a_description_that_cannot_be_stored_is_refused(self, description: str) -> None:
        with pytest.raises(ValueError, match="description"):
            a_charge(description=description)

    def test_a_charge_settled_at_the_counter_is_rounded_once_as_it_is_written(self) -> None:
        rental_id = uuid4()
        charge = Charge.settled_at_the_counter(
            rental_id=rental_id,
            charge_type=ChargeType.HIRE,
            description="Plate Compactor, 1 day",
            amount_ex_vat=Money.create("10.005"),
            vat_rate=FIFTEEN_PERCENT,
            vat_amount=Money.create("1.50075"),
            raised_at=NOW,
            raised_by_user_id=uuid4(),
            reference=payment_reference("TSH-H-26-000099", 1),
        )
        assert (charge.amount_ex_vat, charge.vat_amount, charge.amount_inc_vat) == (
            Decimal("10.01"), Decimal("1.50"), Decimal("11.51")
        )
        assert (charge.status, charge.settled_at, charge.rental_id) == (
            ChargeStatus.SETTLED, NOW, rental_id
        )
        assert charge.payment_reference == "SIM-TSH-H-26-000099-01"
        assert charge.rental_item_id is None
