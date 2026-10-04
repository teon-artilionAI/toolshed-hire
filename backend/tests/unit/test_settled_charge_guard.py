"""A settled charge is never edited, with no database anywhere (BR-24).

A charge that is owed is PENDING, and `settled` is the one way it moves on. A
charge that is settled, waived or reversed is final, so the guard refuses to
hand back a changed copy of one, and a correction is a new charge. The
repository refuses the same thing again, which tests/integration/test_return_transaction.py
proves against PostgreSQL.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Final
from uuid import uuid4

import pytest

from app.domain.charge import Charge
from app.domain.enums import ChargeStatus, ChargeType
from app.domain.errors import StateTransitionError
from app.domain.money import Money
from tests.support.return_domain import a_hire

NOW: Final[datetime] = datetime(2026, 3, 14, 8, 0, tzinfo=UTC)
LATER: Final[datetime] = datetime(2026, 3, 20, 8, 0, tzinfo=UTC)


def an_owed_fee() -> Charge:
    """Return a late fee of R240.00 that is owed and not yet paid."""
    return Charge.owed(
        rental_id=uuid4(),
        charge_type=ChargeType.LATE_FEE,
        description="Late fee for 2 days at R120.00 a day, including VAT",
        amount_ex_vat=Money.create("208.695"),
        vat_rate=Decimal("15.00"),
        vat_amount=Money.create("31.304"),
        raised_at=NOW,
        raised_by_user_id=uuid4(),
    )


def test_an_owed_charge_is_pending_and_rounded_as_it_is_written() -> None:
    fee = an_owed_fee()
    assert (fee.status, fee.settled_at, fee.payment_reference) == (ChargeStatus.PENDING, None, None)
    assert (fee.amount_ex_vat, fee.vat_amount, fee.amount_inc_vat) == (
        Decimal("208.70"), Decimal("31.30"), Decimal("240.00")
    )
    assert fee.total() == Money.create("240.00")


def test_a_pending_charge_is_settled_with_its_time_and_reference() -> None:
    fee = an_owed_fee()
    settled = fee.settled(settled_at=LATER, payment_reference="EFT-1")
    assert (settled.status, settled.settled_at, settled.payment_reference) == (
        ChargeStatus.SETTLED, LATER, "EFT-1"
    )
    assert (settled.id, settled.amount_inc_vat) == (fee.id, fee.amount_inc_vat)
    assert fee.status is ChargeStatus.PENDING, "The charge was changed in place."


@pytest.mark.parametrize(
    ("status", "words"),
    [
        (ChargeStatus.SETTLED, "settled"),
        (ChargeStatus.WAIVED, "waived"),
        (ChargeStatus.REVERSED, "reversed"),
    ],
)
def test_a_charge_that_is_no_longer_pending_is_never_changed(
    status: ChargeStatus, words: str
) -> None:
    final = replace(an_owed_fee(), status=status, reason="Corrected by the office.")
    with pytest.raises(StateTransitionError, match=f"This charge is {words}") as refused:
        final.settled(settled_at=LATER, payment_reference="EFT-2")
    assert refused.value.rule == "BR-24"
    assert refused.value.detail == {"from_status": status.value, "to_status": "SETTLED"}


def test_a_charge_settled_at_the_counter_cannot_be_settled_again() -> None:
    hire_charge = a_hire().rental.charges[0]
    assert hire_charge.status is ChargeStatus.SETTLED
    with pytest.raises(StateTransitionError):
        hire_charge.ensure_may_change()


@pytest.mark.parametrize("reference", ["", "   ", "R" * 41])
def test_a_reference_that_cannot_be_stored_is_refused(reference: str) -> None:
    with pytest.raises(ValueError, match="between one and 40"):
        an_owed_fee().settled(settled_at=LATER, payment_reference=reference)


def test_numbering_a_charge_the_rental_does_not_carry_is_a_fault_in_the_caller() -> None:
    with pytest.raises(ValueError, match="does not carry it"):
        a_hire().rental.charge_position(an_owed_fee())
