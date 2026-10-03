"""Settling the deposit once every unit is back, and the payment of a balance (BR-32, BR-33, BR-53).

The deposit is settled in one calculation with no database anywhere,
`deposit_settlement_of`. What is owed is the late fees and the recovery
charges still pending. The deposit pays what it can of that, so what is
withheld is never more than what is held, and what is left of the deposit is
released. What the deposit cannot cover is the balance due. A deposit kept
for a lost unit was already kept when the loss was recorded, so it counts as
withheld and is not available to pay anything else.

`settle_deposit` applies that calculation to a rental. Each pending charge the
deposit covers in full is settled, in the order the charges were raised, the
remainder is released as a DEPOSIT_RELEASE charge with a negative amount, and
the rental carries the three figures. With nothing left due every charge is
settled or waived, so the rental is SETTLED and `settled_at` is stamped in the
same transaction (BR-53). With a balance due it stays RETURNED until the
balance is paid.

When the deposit may be settled is `settlement_wait`. It is one function, and
it answers what the rental still waits on, in the order the waits are lifted.
The units have to be back, then every damage assessment has to be done, and
only then is the deposit settled. A later rule says "not yet" by adding to it.

`record_balance_payment` records the simulated payment of a balance (BR-33).
It settles every charge still pending with the reference the counter typed,
and the rental is then SETTLED.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final
from uuid import UUID

from app.domain.charge import Charge, payment_reference
from app.domain.enums import ChargeType, RentalStatus
from app.domain.errors import StateTransitionError
from app.domain.money import Money
from app.domain.rental import Rental, SettlementWait
from app.domain.return_charges import deposit_release_charge

SETTLEMENT_RULE: Final[str] = "BR-32"
BALANCE_RULE: Final[str] = "BR-33"
NOTHING_WAITING: Final[int] = 0
# The charges the deposit is withheld for (BR-32).
WITHHELD_FOR: Final[frozenset[ChargeType]] = frozenset(
    {ChargeType.LATE_FEE, ChargeType.DAMAGE_RECOVERY}
)

UNITS_STILL_OUT_MESSAGE: Final[str] = (
    "The deposit is settled once every unit is back. One or more is still out."
)
ALREADY_SETTLED_MESSAGE: Final[str] = "The deposit of this rental has already been settled."
NOTHING_DUE_MESSAGE: Final[str] = "Nothing is owed on this rental, so there is no balance to pay."


@dataclass(frozen=True, slots=True)
class DepositSettlement:
    """The figures of one settlement, every amount rounded to the cent.

    Attributes:
        held: The deposit taken at checkout.
        forfeited: The part of it already kept for lost units.
        owed: The late fees and recoveries the deposit was asked to pay.
        withheld: Everything kept of the deposit, the forfeits included. It
            is never more than `held`.
        released: What is given back. Never negative.
        balance_due: What the deposit could not cover.

    """

    held: Money
    forfeited: Money
    owed: Money
    withheld: Money
    released: Money
    balance_due: Money

    @property
    def covered(self) -> Money:
        """Return how much of what was owed the deposit paid."""
        return self.withheld.subtract(self.forfeited)


def deposit_settlement_of(*, held: Money, forfeited: Money, owed: Money) -> DepositSettlement:
    """Work out how a deposit is settled against what is owed (BR-32).

    Args:
        held: The deposit taken at checkout.
        forfeited: The part of it already kept for lost units.
        owed: The late fees and recoveries still pending.

    Returns:
        The figures. The deposit available is what is held less what was
        forfeited, it pays the smaller of that and what is owed, and the rest
        of it is released. None of the figures is ever negative.

    """
    nothing = Money.zero().rounded()
    held, forfeited, owed = held.rounded(), forfeited.rounded(), owed.rounded()
    kept_already = min(forfeited, held) if forfeited > nothing else nothing
    available = held.subtract(kept_already)
    asked = owed if owed > nothing else nothing
    covered = min(asked, available)
    return DepositSettlement(
        held=held,
        forfeited=kept_already,
        owed=asked,
        withheld=kept_already.add(covered),
        released=available.subtract(covered),
        balance_due=asked.subtract(covered),
    )


def settlement_wait(
    *, status: RentalStatus, items_out: int, assessments_due: int, balance_due: Decimal
) -> SettlementWait | None:
    """Return what a rental waits on before its account is settled, or None when nothing.

    Args:
        status: Where the rental stands.
        items_out: How many units are still with the customer.
        assessments_due: How many units that came back still wait for their
            damage to be assessed.
        balance_due: What the customer still owes once the deposit is offset.

    """
    if status is RentalStatus.SETTLED:
        return None
    if items_out > NOTHING_WAITING:
        return SettlementWait.ITEMS_OUT
    if assessments_due > NOTHING_WAITING:
        return SettlementWait.DAMAGE_ASSESSMENT
    if balance_due > Decimal(NOTHING_WAITING):
        return SettlementWait.BALANCE_PAYMENT
    return None


def deposit_was_settled(rental: Rental) -> bool:
    """Return True when the deposit of the rental has already been settled.

    A settlement leaves one of three marks, a SETTLED status, a balance due,
    or a release of what was left of the deposit.
    """
    return (
        rental.status is RentalStatus.SETTLED
        or rental.balance_due > Decimal(NOTHING_WAITING)
        or any(charge.charge_type is ChargeType.DEPOSIT_RELEASE for charge in rental.charges)
    )


def settle_deposit(rental: Rental, *, settled_by: UUID, now: datetime) -> DepositSettlement:
    """Settle the deposit of a rental whose units are all back (BR-32, BR-53).

    Args:
        rental: The rental, locked by the caller, with its items and charges.
        settled_by: The member of staff whose action settled it.
        now: The current instant, from the clock.

    Returns:
        The figures of the settlement, which are also on the rental now.

    Raises:
        StateTransitionError: If a unit is still out, or the deposit was
            already settled.

    """
    if rental.items_out():
        raise _refused(rental, UNITS_STILL_OUT_MESSAGE, SETTLEMENT_RULE)
    if deposit_was_settled(rental):
        raise _refused(rental, ALREADY_SETTLED_MESSAGE, SETTLEMENT_RULE)
    owed_charges = [
        charge
        for charge in rental.charges
        if charge.is_pending() and charge.charge_type in WITHHELD_FOR
    ]
    settlement = deposit_settlement_of(
        held=Money.create(rental.deposit_held),
        forfeited=_sum(
            charge.total()
            for charge in rental.charges
            if charge.charge_type is ChargeType.DEPOSIT_FORFEIT
        ),
        owed=_sum(charge.total() for charge in owed_charges),
    )
    _settle_what_the_deposit_covers(rental, owed_charges, settlement.covered, now)
    if settlement.released > Money.zero():
        rental.charges.append(
            deposit_release_charge(
                rental=rental,
                released=settlement.released,
                withheld=settlement.withheld,
                raised_by=settled_by,
                now=now,
            )
        )
    rental.deposit_withheld = settlement.withheld.amount
    rental.deposit_refunded = settlement.released.amount
    rental.balance_due = settlement.balance_due.amount
    if settlement.balance_due == Money.zero() and not any(
        charge.is_pending() for charge in rental.charges
    ):
        rental.status = RentalStatus.SETTLED
        rental.settled_at = now
    return settlement


def record_balance_payment(rental: Rental, *, payment_reference: str, now: datetime) -> Money:
    """Record the simulated payment of a rental's balance, and settle it (BR-33, BR-53).

    Args:
        rental: The rental, locked by the caller, with its charges.
        payment_reference: The reference the counter typed for the payment.
        now: The current instant, from the clock.

    Returns:
        The amount that was paid.

    Raises:
        StateTransitionError: If nothing is owed on the rental.

    """
    paid = Money.create(rental.balance_due)
    if rental.status is RentalStatus.SETTLED or not paid > Money.zero():
        raise _refused(rental, NOTHING_DUE_MESSAGE, BALANCE_RULE)
    rental.charges = [
        charge.settled(settled_at=now, payment_reference=payment_reference)
        if charge.is_pending()
        else charge
        for charge in rental.charges
    ]
    rental.balance_due = Money.zero().rounded().amount
    rental.status = RentalStatus.SETTLED
    rental.settled_at = now
    return paid


def _settle_what_the_deposit_covers(
    rental: Rental, owed: list[Charge], covered: Money, now: datetime
) -> None:
    """Settle each owed charge the deposit pays in full, in the order they were raised."""
    remaining = covered
    paid: dict[UUID, Charge] = {}
    for charge in owed:
        if charge.total() <= remaining:
            remaining = remaining.subtract(charge.total())
            paid[charge.id] = charge.settled(
                settled_at=now,
                payment_reference=payment_reference(
                    rental.reference, rental.charge_position(charge)
                ),
            )
    rental.charges = [paid.get(charge.id, charge) for charge in rental.charges]


def _sum(amounts: Iterable[Money]) -> Money:
    """Return the amounts added together."""
    total = Money.zero()
    for amount in amounts:
        total = total.add(amount)
    return total


def _refused(rental: Rental, message: str, rule: str) -> StateTransitionError:
    """Return the refusal of a settlement move on a rental."""
    return StateTransitionError(
        message,
        from_status=rental.status.value,
        to_status=RentalStatus.SETTLED.value,
        rule=rule,
    )
