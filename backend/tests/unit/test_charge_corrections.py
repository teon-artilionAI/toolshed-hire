"""Waiving, reversing and adjusting a charge, with no database anywhere (BR-24, BR-25).

A waiver lets a pending charge go through the guard that settles one, a
reversal is a new negated charge that points back at a settled one and leaves
it as it was, and an adjustment is a new ADJUSTMENT charge split for VAT like a
late fee. Each needs a reason of five to two hundred characters. The hire is
the one the domain's own checkout makes from the worked example's hammer.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Final
from uuid import uuid4

import pytest

from app.domain.charge import Charge
from app.domain.charge_corrections import (
    ALREADY_REVERSED_MESSAGE,
    CREDIT_DESCRIPTION,
    DEBIT_DESCRIPTION,
    DEPOSIT_MOVEMENT_MESSAGE,
    NOT_SETTLED_MESSAGE,
    REVERSAL_OF_A_REVERSAL_MESSAGE,
    adjust,
    charge_on,
    reverse,
    waive,
)
from app.domain.customer_account import REFUSED_FIELD
from app.domain.enums import ChargeStatus, ChargeType
from app.domain.errors import StateTransitionError, ValidationFailure
from app.domain.money import Money
from app.domain.override_reason import REASON_LENGTH_MESSAGE, written_reason
from tests.support.return_domain import TWO_UNITS, Hire, a_hire, back, days_after_due, returned

NOW: Final[datetime] = datetime(2026, 3, 16, 8, 0, tzinfo=UTC)
ADMINISTRATOR: Final = uuid4()
REASON: Final[str] = "Agreed with the customer at the counter."


def a_pending_fee() -> tuple[Hire, Charge]:
    """Return a hire of two units with one back two days late, and its pending late fee."""
    hire = a_hire(TWO_UNITS)
    returned(hire, days_after_due(2), back(hire, 0))
    (fee,) = [charge for charge in hire.rental.charges if charge.is_pending()]
    return hire, fee


def the_hire_charge(hire: Hire) -> Charge:
    """Return the hire charge a checkout settles at the counter."""
    (charge,) = [c for c in hire.rental.charges if c.charge_type is ChargeType.HIRE]
    return charge


class TestTheReason:
    """A reason says something and fits its column (BR-25)."""

    @pytest.mark.parametrize("reason", ["", "   ", "abcd", "x" * 201])
    def test_a_reason_too_short_or_too_long_is_refused_naming_the_field(self, reason: str) -> None:
        with pytest.raises(ValidationFailure) as refused:
            written_reason(reason)
        assert refused.value.message == REASON_LENGTH_MESSAGE
        assert refused.value.detail[REFUSED_FIELD] == "reason"
        assert refused.value.rule == "BR-25"

    def test_a_reason_is_kept_trimmed(self) -> None:
        assert written_reason("  Goodwill  ") == "Goodwill"
        assert written_reason("x" * 200) == "x" * 200


class TestAWaiver:
    """Only a pending charge is waived, and it keeps the reason."""

    def test_a_pending_fee_is_waived_with_its_reason_and_nothing_else_changes(self) -> None:
        hire, fee = a_pending_fee()
        waived = waive(hire.rental, fee, reason=f"  {REASON}  ")

        assert (waived.status, waived.reason, waived.id) == (ChargeStatus.WAIVED, REASON, fee.id)
        assert waived.amount_inc_vat == fee.amount_inc_vat
        assert charge_on(hire.rental, fee.id) is waived
        assert len(hire.rental.charges) == 3

    def test_a_settled_charge_is_never_waived(self) -> None:
        hire = a_hire()
        settled = the_hire_charge(hire)
        with pytest.raises(StateTransitionError, match="settled, so it cannot be changed") as no:
            waive(hire.rental, settled, reason=REASON)
        assert no.value.rule == "BR-24"
        assert no.value.detail == {"from_status": "SETTLED", "to_status": "WAIVED"}
        assert charge_on(hire.rental, settled.id).status is ChargeStatus.SETTLED

    def test_a_waiver_with_no_reason_leaves_the_charge_pending(self) -> None:
        hire, fee = a_pending_fee()
        with pytest.raises(ValidationFailure):
            waive(hire.rental, fee, reason="no")
        assert charge_on(hire.rental, fee.id).status is ChargeStatus.PENDING

    def test_a_waived_charge_cannot_be_built_without_a_reason(self) -> None:
        _hire, fee = a_pending_fee()
        with pytest.raises(ValueError, match="no reason"):
            replace(fee, status=ChargeStatus.WAIVED)


class TestAReversal:
    """A reversal is a new negated charge that points back at a settled one (BR-24)."""

    def test_the_hire_charge_is_reversed_by_a_new_negated_charge(self) -> None:
        hire = a_hire()
        original = the_hire_charge(hire)
        reversal = reverse(hire.rental, original, reason=REASON, raised_by=ADMINISTRATOR, now=NOW)

        assert reversal.charge_type is ChargeType.HIRE
        assert (reversal.amount_ex_vat, reversal.vat_amount, reversal.amount_inc_vat) == (
            -original.amount_ex_vat, -original.vat_amount, -original.amount_inc_vat
        )
        assert reversal.vat_rate == original.vat_rate
        assert (reversal.reverses_charge_id, reversal.reason) == (original.id, REASON)
        assert (reversal.status, reversal.raised_at, reversal.raised_by_user_id) == (
            ChargeStatus.PENDING, NOW, ADMINISTRATOR
        )
        assert reversal.rental_item_id == original.rental_item_id
        assert reversal.description == f"Reversal of {original.description}"
        assert charge_on(hire.rental, original.id) == original
        assert hire.rental.charges[-1] is reversal

    def test_a_pending_charge_is_waived_and_not_reversed(self) -> None:
        hire, fee = a_pending_fee()
        with pytest.raises(StateTransitionError, match=NOT_SETTLED_MESSAGE) as no:
            reverse(hire.rental, fee, reason=REASON, raised_by=ADMINISTRATOR, now=NOW)
        assert no.value.detail == {"from_status": "PENDING", "to_status": "REVERSED"}

    def test_a_deposit_movement_is_never_reversed(self) -> None:
        hire = a_hire()
        (hold,) = [c for c in hire.rental.charges if c.charge_type is ChargeType.DEPOSIT_HOLD]
        with pytest.raises(StateTransitionError, match=DEPOSIT_MOVEMENT_MESSAGE):
            reverse(hire.rental, hold, reason=REASON, raised_by=ADMINISTRATOR, now=NOW)

    def test_a_charge_is_reversed_once_and_a_reversal_is_never_reversed(self) -> None:
        hire = a_hire()
        original = the_hire_charge(hire)
        reversal = reverse(hire.rental, original, reason=REASON, raised_by=ADMINISTRATOR, now=NOW)
        with pytest.raises(StateTransitionError, match=ALREADY_REVERSED_MESSAGE):
            reverse(hire.rental, original, reason=REASON, raised_by=ADMINISTRATOR, now=NOW)
        settled = reversal.settled(settled_at=NOW, payment_reference="SIM-1")
        with pytest.raises(StateTransitionError, match=REVERSAL_OF_A_REVERSAL_MESSAGE):
            reverse(hire.rental, settled, reason=REASON, raised_by=ADMINISTRATOR, now=NOW)
        assert len(hire.rental.charges) == 3

    def test_the_description_of_a_reversal_fits_its_column(self) -> None:
        hire = a_hire()
        long_one = replace(the_hire_charge(hire), description="H" * 200)
        reversal = reverse(hire.rental, long_one, reason=REASON, raised_by=ADMINISTRATOR, now=NOW)
        assert len(reversal.description) == 200
        assert reversal.description.startswith("Reversal of HHH")


class TestAnAdjustment:
    """A new ADJUSTMENT charge for an amount that includes VAT, positive or negative."""

    def test_an_amount_owed_is_split_for_vat_like_a_late_fee(self) -> None:
        hire = a_hire()
        adjustment = adjust(
            hire.rental,
            amount_inc_vat=Money.create("150.00"),
            reason=REASON,
            raised_by=ADMINISTRATOR,
            now=NOW,
        )
        assert adjustment.charge_type is ChargeType.ADJUSTMENT
        assert (adjustment.amount_ex_vat, adjustment.vat_amount, adjustment.amount_inc_vat) == (
            Decimal("130.43"), Decimal("19.57"), Decimal("150.00")
        )
        assert (adjustment.status, adjustment.reason, adjustment.description) == (
            ChargeStatus.PENDING, REASON, DEBIT_DESCRIPTION
        )
        assert (adjustment.rental_item_id, adjustment.reverses_charge_id) == (None, None)
        assert hire.rental.charges[-1] is adjustment

    def test_an_amount_the_customer_is_owed_is_a_credit(self) -> None:
        hire = a_hire()
        credit = adjust(
            hire.rental,
            amount_inc_vat=Money.create("-150.00"),
            reason=REASON,
            raised_by=ADMINISTRATOR,
            now=NOW,
        )
        assert (credit.amount_ex_vat, credit.vat_amount, credit.amount_inc_vat) == (
            Decimal("-130.43"), Decimal("-19.57"), Decimal("-150.00")
        )
        assert credit.description == CREDIT_DESCRIPTION

    @pytest.mark.parametrize("amount", ["0.00", "0.004", "-0.00"])
    def test_nothing_is_not_an_adjustment(self, amount: str) -> None:
        hire = a_hire()
        with pytest.raises(ValidationFailure) as refused:
            adjust(
                hire.rental,
                amount_inc_vat=Money.create(amount),
                reason=REASON,
                raised_by=ADMINISTRATOR,
                now=NOW,
            )
        assert refused.value.detail == {REFUSED_FIELD: "amount_inc_vat"}
        assert len(hire.rental.charges) == 2


def test_a_charge_the_rental_does_not_carry_is_a_fault_in_the_caller() -> None:
    with pytest.raises(LookupError, match="does not carry it"):
        charge_on(a_hire().rental, uuid4())
