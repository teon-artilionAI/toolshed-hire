"""Settling the deposit and paying a balance, with no database anywhere (BR-32, BR-33, BR-53).

The calculation first, on plain amounts, and then the settlement of a hire
the domain's own checkout and return made. The deposit pays what it can of
the late fees and recoveries owed, never more than it holds, the rest of it is
released as a negative charge, and what it cannot cover is the balance due.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Final

import pytest

from app.domain.enums import ChargeStatus, ChargeType, RentalStatus
from app.domain.errors import StateTransitionError
from app.domain.money import Money
from app.domain.rental import SettlementWait
from app.domain.settlement import (
    deposit_settlement_of,
    deposit_was_settled,
    record_balance_payment,
    settle_deposit,
    settlement_wait,
)
from tests.support.checkout_domain import ASSISTANT
from tests.support.return_domain import a_hire, back, days_after_due, lost, on_day, returned

NOW: Final[datetime] = datetime(2026, 3, 14, 8, 0, tzinfo=UTC)


def figures(held: str, owed: str, forfeited: str = "0") -> tuple[str, str, str]:
    """Return the withheld, the released and the balance due of a settlement, as text."""
    settlement = deposit_settlement_of(
        held=Money.create(held), forfeited=Money.create(forfeited), owed=Money.create(owed)
    )
    return (
        str(settlement.withheld.amount),
        str(settlement.released.amount),
        str(settlement.balance_due.amount),
    )


class TestTheCalculation:
    """Withheld is what is owed up to what is held, and the rest is released or due."""

    def test_nothing_owed_releases_the_whole_deposit(self) -> None:
        assert figures("1200.00", "0.00") == ("0.00", "1200.00", "0.00")

    def test_the_worked_example(self) -> None:
        assert figures("1200.00", "240.00") == ("240.00", "960.00", "0.00")

    def test_owed_equal_to_held_releases_nothing_and_leaves_nothing_due(self) -> None:
        assert figures("1200.00", "1200.00") == ("1200.00", "0.00", "0.00")

    def test_owed_above_held_leaves_a_balance(self) -> None:
        assert figures("1200.00", "1500.00") == ("1200.00", "0.00", "300.00")

    @pytest.mark.parametrize(("held", "owed"), [("0.00", "50.00"), ("100.00", "-20.00")])
    def test_the_release_is_never_negative(self, held: str, owed: str) -> None:
        withheld, released, due = figures(held, owed)
        assert Decimal(released) >= 0 and Decimal(withheld) >= 0 and Decimal(due) >= 0

    def test_a_forfeit_counts_as_withheld_and_is_not_available_again(self) -> None:
        assert figures("2400.00", "1680.00", forfeited="1200.00") == (
            "2400.00", "0.00", "480.00"
        )
        assert figures("1200.00", "0.00", forfeited="5000.00") == ("1200.00", "0.00", "0.00")


class TestWhatTheSettlementWaitsOn:
    """The units first, then any assessment, then a balance, and nothing once settled."""

    def test_the_waits_are_lifted_in_order(self) -> None:
        def wait(status: RentalStatus, out: int, due: int, balance: str) -> object:
            return settlement_wait(
                status=status, items_out=out, assessments_due=due, balance_due=Decimal(balance)
            )

        assert wait(RentalStatus.OPEN, 1, 1, "5") is SettlementWait.ITEMS_OUT
        assert wait(RentalStatus.RETURNED, 0, 1, "5") is SettlementWait.DAMAGE_ASSESSMENT
        assert wait(RentalStatus.RETURNED, 0, 0, "5") is SettlementWait.BALANCE_PAYMENT
        assert wait(RentalStatus.RETURNED, 0, 0, "0") is None
        assert wait(RentalStatus.SETTLED, 0, 0, "0") is None


class TestSettlingAHire:
    """The settlement of a hire the domain's checkout made and its return brought back."""

    def test_the_worked_example_settles_the_hire(self) -> None:
        hire = a_hire()
        returned(hire, days_after_due(2), back(hire))
        settlement = settle_deposit(hire.rental, settled_by=ASSISTANT, now=NOW)

        rental = hire.rental
        assert (settlement.withheld, settlement.released) == (
            Money.create("240.00"), Money.create("960.00")
        )
        assert (rental.deposit_withheld, rental.deposit_refunded, rental.balance_due) == (
            Decimal("240.00"), Decimal("960.00"), Decimal("0.00")
        )
        assert (rental.status, rental.settled_at) == (RentalStatus.SETTLED, NOW)
        assert {charge.status for charge in rental.charges} == {ChargeStatus.SETTLED}
        release = rental.charges[-1]
        assert (release.charge_type, release.amount_inc_vat) == (
            ChargeType.DEPOSIT_RELEASE, Decimal("-960.00")
        )
        assert release.payment_reference == "SIM-TSH-H-26-000099-04"
        assert rental.charges[2].payment_reference == "SIM-TSH-H-26-000099-03"

    def test_a_balance_leaves_the_rental_returned_until_it_is_paid(self) -> None:
        hire = a_hire()
        lost(hire, days_after_due(15))
        settle_deposit(hire.rental, settled_by=ASSISTANT, now=NOW)

        rental = hire.rental
        assert (rental.status, rental.settled_at) == (RentalStatus.RETURNED, None)
        assert rental.balance_due == Decimal("6980.00")
        assert deposit_was_settled(rental) is True
        paid = record_balance_payment(rental, payment_reference="EFT-77", now=on_day(NOW.date()))
        assert paid == Money.create("6980.00")
        assert (rental.status, rental.balance_due) == (RentalStatus.SETTLED, Decimal("0.00"))
        assert {charge.status for charge in rental.charges} == {ChargeStatus.SETTLED}
        assert {
            charge.payment_reference
            for charge in rental.charges
            if charge.charge_type in (ChargeType.LATE_FEE, ChargeType.DAMAGE_RECOVERY)
        } == {"EFT-77"}

    def test_a_settlement_with_a_unit_still_out_is_refused(self) -> None:
        hire = a_hire()
        with pytest.raises(StateTransitionError, match="still out"):
            settle_deposit(hire.rental, settled_by=ASSISTANT, now=NOW)

    def test_a_deposit_is_settled_once(self) -> None:
        hire = a_hire()
        returned(hire, days_after_due(0), back(hire))
        settle_deposit(hire.rental, settled_by=ASSISTANT, now=NOW)
        with pytest.raises(StateTransitionError, match="already been settled"):
            settle_deposit(hire.rental, settled_by=ASSISTANT, now=NOW)

    def test_a_balance_payment_with_nothing_due_is_refused(self) -> None:
        hire = a_hire()
        returned(hire, days_after_due(0), back(hire))
        settle_deposit(hire.rental, settled_by=ASSISTANT, now=NOW)
        with pytest.raises(StateTransitionError, match="Nothing is owed"):
            record_balance_payment(hire.rental, payment_reference="EFT-1", now=NOW)
