"""Working a settled deposit out again after a charge is corrected (BR-24, BR-32, BR-53).

A waiver, a reversal or an adjustment changes what a hire owes. Before the
deposit is settled that needs nothing more, because the settlement still to
come counts every charge pending at that moment, credits included. Once the
deposit has been settled the figures on the rental are worked out again here,
with the calculation the first settlement used, `deposit_settlement_of`, and
nothing that was already paid or given back is taken back.

What can still move is the part of the deposit that is paying for charges not
yet settled. A settlement that left a balance spent all of the deposit, part
of it on a charge it could not pay in full, and that part is what is pending
less what is due (`deposit_paying_for_pending`). The rest of the deposit was
spent on charges that are settled, or given back, and stays as it is.

The rework settles the pending charges against that part with the rules of
the first settlement. Whatever of it is no longer needed is released as a new
DEPOSIT_RELEASE charge, what it cannot cover is the balance due, and a credit
larger than everything still owed is paid back by settling the credit itself.

A hire that was SETTLED is never edited (BR-53), so the only correction it
takes is one that gives money back, and it stays SETTLED, with the credit
settled at once and `settled_at` as it was. A hire that was waiting on a
balance is SETTLED as soon as a correction leaves nothing due, and otherwise
keeps waiting on what is left.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.domain.enums import RentalStatus
from app.domain.money import Money
from app.domain.rental import Rental
from app.domain.return_charges import deposit_release_charge
from app.domain.settlement import (
    DepositSettlement,
    deposit_settlement_of,
    deposit_was_settled,
    pending_total,
    settle_covered_charges,
)


def deposit_paying_for_pending(rental: Rental) -> Money:
    """Return the part of the deposit that is paying for charges not yet settled.

    It is asked before a correction changes anything. After a settlement that
    left a balance it is what is pending less what is due, and once nothing is
    pending it is nothing. It is never negative.
    """
    spent = pending_total(rental).subtract(Money.create(rental.balance_due))
    return spent if spent > Money.zero() else Money.zero()


def rework_settlement(
    rental: Rental, *, paying_before: Money, settled_by: UUID, now: datetime
) -> DepositSettlement | None:
    """Work out the deposit, the balance and the status of a corrected rental again.

    Args:
        rental: The rental, locked by the caller, with the correction applied.
        paying_before: What `deposit_paying_for_pending` answered before the
            correction was applied.
        settled_by: The administrator whose correction this is.
        now: The current instant, from the clock.

    Returns:
        The settlement of the part of the deposit that was reworked, or None
        when the deposit has not been settled yet and nothing needed doing.

    """
    if not deposit_was_settled(rental):
        return None
    was_settled = rental.status is RentalStatus.SETTLED
    settlement = deposit_settlement_of(
        held=paying_before, forfeited=Money.zero(), owed=pending_total(rental)
    )
    settle_covered_charges(rental, settlement, now)
    withheld = (
        Money.create(rental.deposit_withheld).subtract(paying_before).add(settlement.covered)
    )
    if settlement.released > Money.zero():
        rental.charges.append(
            deposit_release_charge(
                rental=rental,
                released=settlement.released,
                withheld=withheld,
                raised_by=settled_by,
                now=now,
            )
        )
    rental.deposit_withheld = withheld.rounded().amount
    rental.deposit_refunded = (
        Money.create(rental.deposit_refunded).add(settlement.released).rounded().amount
    )
    rental.balance_due = settlement.balance_due.amount
    owes_nothing = settlement.balance_due == Money.zero() and not any(
        charge.is_pending() for charge in rental.charges
    )
    if owes_nothing and not was_settled:
        rental.status = RentalStatus.SETTLED
        rental.settled_at = now
    return settlement
