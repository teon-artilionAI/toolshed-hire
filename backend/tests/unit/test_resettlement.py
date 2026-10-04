"""The deposit, the balance and the status of a hire worked out again after a correction.

The worked example of the design document settles a deposit of R1,200.00 with
R240.00 withheld and R960.00 released. Two units back fifteen days late owe
the fourteen days the policy charges each, R1,680.00 a unit, so a deposit of
R2,400.00 settles the first and pays R720.00 of the second, and R960.00 is
due. These follow what a waiver, a reversal and an adjustment do to each,
before and after the deposit is settled, with no database anywhere.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Final
from uuid import uuid4

import pytest

from app.domain.charge import Charge
from app.domain.charge_corrections import SETTLED_HIRE_MESSAGE, adjust, reverse, waive
from app.domain.enums import ChargeStatus, ChargeType, RentalStatus
from app.domain.errors import StateTransitionError
from app.domain.money import Money
from app.domain.rental import Rental
from app.domain.resettlement import deposit_paying_for_pending, rework_settlement
from app.domain.settlement import record_balance_payment, settle_deposit
from tests.support.checkout_domain import ASSISTANT
from tests.support.return_domain import TWO_UNITS, Hire, a_hire, back, days_after_due, returned

SETTLED_AT: Final[datetime] = datetime(2026, 3, 14, 8, 0, tzinfo=UTC)
NOW: Final[datetime] = datetime(2026, 3, 20, 8, 0, tzinfo=UTC)
ADMINISTRATOR: Final = uuid4()
REASON: Final[str] = "Agreed with the customer at the counter."


def figures(rental: Rental) -> tuple[str, str, str, RentalStatus]:
    """Return the withheld, the refunded, the balance due and the status of a rental."""
    return (
        str(rental.deposit_withheld),
        str(rental.deposit_refunded),
        str(rental.balance_due),
        rental.status,
    )


def the_worked_example() -> Hire:
    """Return the worked example, two days late and SETTLED."""
    hire = a_hire()
    returned(hire, days_after_due(2), back(hire))
    settle_deposit(hire.rental, settled_by=ASSISTANT, now=SETTLED_AT)
    return hire


def a_balance_due() -> Hire:
    """Return two units back fifteen days late, the deposit spent and R960.00 due."""
    hire = a_hire(TWO_UNITS)
    returned(hire, days_after_due(15), back(hire))
    settle_deposit(hire.rental, settled_by=ASSISTANT, now=SETTLED_AT)
    return hire


def pending(rental: Rental) -> list[Charge]:
    """Return the charges of a rental still pending."""
    return [charge for charge in rental.charges if charge.is_pending()]


def of_type(rental: Rental, charge_type: ChargeType) -> list[Charge]:
    """Return the charges of one type on a rental."""
    return [charge for charge in rental.charges if charge.charge_type is charge_type]


def reworked(hire: Hire, paying_before: Money) -> None:
    """Work the hire out again after a correction, as the administrator."""
    rework_settlement(hire.rental, paying_before=paying_before, settled_by=ADMINISTRATOR, now=NOW)


class TestBeforeTheDepositIsSettled:
    """Nothing is worked out again, and the settlement still to come counts the correction."""

    def test_a_hire_still_out_is_left_for_its_settlement(self) -> None:
        hire = a_hire()
        adjust(
            hire.rental,
            amount_inc_vat=Money.create("100.00"),
            reason=REASON,
            raised_by=ADMINISTRATOR,
            now=NOW,
        )
        assert rework_settlement(
            hire.rental, paying_before=Money.zero(), settled_by=ADMINISTRATOR, now=NOW
        ) is None
        assert figures(hire.rental) == ("0.00", "0.00", "0.00", RentalStatus.OPEN)

    def test_a_credit_raised_while_out_is_set_against_what_the_return_owes(self) -> None:
        hire = a_hire()
        adjust(
            hire.rental,
            amount_inc_vat=Money.create("-100.00"),
            reason=REASON,
            raised_by=ADMINISTRATOR,
            now=NOW,
        )
        returned(hire, days_after_due(2), back(hire))
        settle_deposit(hire.rental, settled_by=ASSISTANT, now=SETTLED_AT)
        assert figures(hire.rental) == ("140.00", "1060.00", "0.00", RentalStatus.SETTLED)
        assert pending(hire.rental) == []

    def test_a_credit_larger_than_what_is_owed_is_paid_back_by_settling_it(self) -> None:
        hire = a_hire()
        reverse(
            hire.rental,
            of_type(hire.rental, ChargeType.HIRE)[0],
            reason=REASON,
            raised_by=ADMINISTRATOR,
            now=NOW,
        )
        returned(hire, days_after_due(0), back(hire))
        settle_deposit(hire.rental, settled_by=ASSISTANT, now=SETTLED_AT)
        assert figures(hire.rental) == ("0.00", "1200.00", "0.00", RentalStatus.SETTLED)
        assert {charge.status for charge in hire.rental.charges} == {ChargeStatus.SETTLED}

    def test_a_credit_waits_with_a_balance_the_deposit_cannot_cover(self) -> None:
        hire = a_hire(TWO_UNITS)
        credit = adjust(
            hire.rental,
            amount_inc_vat=Money.create("-100.00"),
            reason=REASON,
            raised_by=ADMINISTRATOR,
            now=NOW,
        )
        returned(hire, days_after_due(15), back(hire))
        settle_deposit(hire.rental, settled_by=ASSISTANT, now=SETTLED_AT)
        assert figures(hire.rental) == ("2400.00", "0.00", "860.00", RentalStatus.RETURNED)
        assert credit.id in {charge.id for charge in pending(hire.rental)}
        assert deposit_paying_for_pending(hire.rental) == Money.create("720.00")


class TestAfterASettlementThatLeftABalance:
    """The part of the deposit paying for a pending charge moves, and nothing else does."""

    def test_the_part_of_the_deposit_still_paying_is_what_is_pending_less_what_is_due(
        self,
    ) -> None:
        hire = a_balance_due()
        assert figures(hire.rental) == ("2400.00", "0.00", "960.00", RentalStatus.RETURNED)
        assert deposit_paying_for_pending(hire.rental) == Money.create("720.00")

    def test_waiving_what_is_due_settles_the_hire_and_releases_what_was_paying_for_it(
        self,
    ) -> None:
        hire = a_balance_due()
        paying = deposit_paying_for_pending(hire.rental)
        (unpaid,) = pending(hire.rental)
        waive(hire.rental, unpaid, reason=REASON)
        reworked(hire, paying)

        assert figures(hire.rental) == ("1680.00", "720.00", "0.00", RentalStatus.SETTLED)
        assert hire.rental.settled_at == NOW
        (release,) = of_type(hire.rental, ChargeType.DEPOSIT_RELEASE)
        assert (release.amount_inc_vat, release.status) == (
            Decimal("-720.00"), ChargeStatus.SETTLED
        )
        assert release.description == "Deposit released after R1680.00 was withheld"

    def test_a_credit_lowers_the_balance_and_waits_with_it(self) -> None:
        hire = a_balance_due()
        paying = deposit_paying_for_pending(hire.rental)
        adjust(
            hire.rental,
            amount_inc_vat=Money.create("-500.00"),
            reason=REASON,
            raised_by=ADMINISTRATOR,
            now=NOW,
        )
        reworked(hire, paying)
        assert figures(hire.rental) == ("2400.00", "0.00", "460.00", RentalStatus.RETURNED)
        assert len(pending(hire.rental)) == 2
        assert deposit_paying_for_pending(hire.rental) == Money.create("720.00")

        paying = deposit_paying_for_pending(hire.rental)
        (fee,) = [charge for charge in pending(hire.rental) if charge.total() > Money.zero()]
        waive(hire.rental, fee, reason=REASON)
        reworked(hire, paying)
        assert figures(hire.rental) == ("1680.00", "720.00", "0.00", RentalStatus.SETTLED)
        assert pending(hire.rental) == []

    def test_a_balance_paid_after_a_credit_is_what_the_credit_left(self) -> None:
        hire = a_balance_due()
        paying = deposit_paying_for_pending(hire.rental)
        adjust(
            hire.rental,
            amount_inc_vat=Money.create("-500.00"),
            reason=REASON,
            raised_by=ADMINISTRATOR,
            now=NOW,
        )
        reworked(hire, paying)
        paid = record_balance_payment(hire.rental, payment_reference="EFT-9", now=NOW)
        assert paid == Money.create("460.00")
        assert figures(hire.rental) == ("2400.00", "0.00", "0.00", RentalStatus.SETTLED)


class TestAfterASettlementThatLeftNothing:
    """A SETTLED hire is never edited, so only a correction that gives money back is made."""

    def test_reversing_a_settled_late_fee_pays_it_back_and_the_hire_stays_settled(self) -> None:
        hire = the_worked_example()
        paying = deposit_paying_for_pending(hire.rental)
        (fee,) = of_type(hire.rental, ChargeType.LATE_FEE)
        reversal = reverse(hire.rental, fee, reason=REASON, raised_by=ADMINISTRATOR, now=NOW)
        reworked(hire, paying)

        assert paying == Money.zero()
        assert figures(hire.rental) == ("240.00", "960.00", "0.00", RentalStatus.SETTLED)
        assert hire.rental.settled_at == SETTLED_AT
        stored = [charge for charge in hire.rental.charges if charge.id == reversal.id][0]
        assert (stored.status, stored.payment_reference) == (
            ChargeStatus.SETTLED, "SIM-TSH-H-26-000099-05"
        )
        assert [charge for charge in hire.rental.charges if charge.id == fee.id] == [fee]

    def test_an_amount_owed_is_refused_because_a_settled_hire_is_never_edited(self) -> None:
        hire = the_worked_example()
        charges_before = list(hire.rental.charges)
        with pytest.raises(StateTransitionError, match=SETTLED_HIRE_MESSAGE) as refused:
            adjust(
                hire.rental,
                amount_inc_vat=Money.create("150.00"),
                reason=REASON,
                raised_by=ADMINISTRATOR,
                now=NOW,
            )
        assert refused.value.rule == "BR-53"
        assert hire.rental.charges == charges_before
        assert figures(hire.rental) == ("240.00", "960.00", "0.00", RentalStatus.SETTLED)

    def test_a_credit_on_a_settled_hire_is_paid_back_and_it_stays_settled(self) -> None:
        hire = the_worked_example()
        paying = deposit_paying_for_pending(hire.rental)
        credit = adjust(
            hire.rental,
            amount_inc_vat=Money.create("-150.00"),
            reason=REASON,
            raised_by=ADMINISTRATOR,
            now=NOW,
        )
        reworked(hire, paying)
        assert figures(hire.rental) == ("240.00", "960.00", "0.00", RentalStatus.SETTLED)
        assert hire.rental.settled_at == SETTLED_AT
        assert [c.status for c in hire.rental.charges if c.id == credit.id] == [
            ChargeStatus.SETTLED
        ]
