"""The late fee policy, the second Strategy, with no database anywhere (BR-30, BR-31).

The standard policy charges each whole day between the day a unit was due
back and the day it came back, at the late fee per day copied onto its
booking, and stops after fourteen days. A return on the due date, or before
it, owes nothing. The fee includes VAT, so nothing is added to it. The fixed
policy is the counterpart a test states in one line.

The hire is due back on the twelfth of March 2026, and the fee is R120.00 a
day, the worked example's.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Final

import pytest

from app.domain.money import Money
from app.domain.policies import (
    FixedLateFeePolicy,
    InvalidLateFeeInput,
    LateFee,
    StandardLateFeePolicy,
)
from tests.support.return_domain import TWO_UNITS, a_hire, back, days_after_due, returned

DUE: Final[date] = date(2026, 3, 12)
FEE: Final[Money] = Money.create("120.00")
STANDARD: Final[StandardLateFeePolicy] = StandardLateFeePolicy()


def late_by(days: int, policy: StandardLateFeePolicy | FixedLateFeePolicy = STANDARD) -> LateFee:
    """Return what the policy charges a unit that came back a number of days after the due date."""
    return policy.late_fee(
        due_back_on=DUE, returned_on=DUE + timedelta(days=days), fee_per_day=FEE
    )


class TestTheStandardPolicy:
    """Each whole day late at the fee per day, for at most fourteen days."""

    @pytest.mark.parametrize(
        ("days", "fee"),
        [
            (0, "0.00"),
            (1, "120.00"),
            (2, "240.00"),
            (14, "1680.00"),
        ],
        ids=["on the due date", "one day", "two days", "fourteen days"],
    )
    def test_each_whole_day_late_is_charged(self, days: int, fee: str) -> None:
        late = late_by(days)
        assert (late.days_late, late.chargeable_days) == (days, days)
        assert late.amount == Money.create(fee)
        assert late.beyond_accrual is False

    def test_the_fifteenth_day_is_not_charged_and_the_unit_is_beyond_accrual(self) -> None:
        late = late_by(15)
        assert (late.days_late, late.chargeable_days) == (15, 14)
        assert late.amount == Money.create("1680.00")
        assert late.beyond_accrual is True

    @pytest.mark.parametrize("days", [-1, -5])
    def test_an_early_return_owes_nothing(self, days: int) -> None:
        late = late_by(days)
        assert (late.days_late, late.amount, late.is_due()) == (0, Money.zero().rounded(), False)

    def test_the_limit_is_a_named_constant_on_the_policy(self) -> None:
        assert StandardLateFeePolicy.ACCRUAL_LIMIT_DAYS == 14
        assert STANDARD.name() == "standard-late-fee"

    def test_a_fee_that_is_not_money_or_is_negative_is_refused(self) -> None:
        with pytest.raises(InvalidLateFeeInput, match="never negative"):
            STANDARD.late_fee(due_back_on=DUE, returned_on=DUE, fee_per_day=Money.create("-1"))

    def test_each_unit_of_a_line_of_more_than_one_is_charged_its_own_fee(self) -> None:
        hire = a_hire(TWO_UNITS)
        outcome = returned(hire, days_after_due(2), back(hire))
        fees = [closed.late_fee_charge for closed in outcome.units]
        assert [fee.amount_inc_vat if fee else None for fee in fees] == [
            Decimal("240.00"), Decimal("240.00")
        ]
        assert {fee.rental_item_id for fee in fees if fee} == {
            item.id for item in hire.rental.items
        }


class TestTheFixedPolicy:
    """One fixed fee for a unit that is late at all, the same limit as the standard one."""

    def test_a_late_unit_is_charged_the_fixed_fee_however_late_it_is(self) -> None:
        fixed = FixedLateFeePolicy(Money.create("50.00"))
        assert late_by(1, fixed).amount == Money.create("50.00")
        assert late_by(9, fixed).amount == Money.create("50.00")
        assert late_by(0, fixed).amount == Money.zero().rounded()
        assert late_by(15, fixed).beyond_accrual is True
        assert fixed.name() == "fixed-late-fee"

    def test_a_fixed_fee_that_is_negative_is_refused(self) -> None:
        with pytest.raises(InvalidLateFeeInput, match="never negative"):
            FixedLateFeePolicy(Money.create("-0.01"))

    def test_a_return_charges_what_the_policy_it_is_handed_says(self) -> None:
        hire = a_hire()
        fixed = FixedLateFeePolicy(Money.create("75.00"))
        (closed,) = returned(hire, days_after_due(3), back(hire), policy=fixed).units
        assert closed.late_fee_charge is not None
        assert closed.late_fee_charge.amount_inc_vat == Decimal("75.00")
        assert closed.item.days_late == 3
