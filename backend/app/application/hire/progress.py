"""Where a rental stands on the way to being settled, worked out for the read of it.

A rental is read with three answers that are worked out and not stored.

What the late fee would be if a unit came back today comes from the late fee
policy (BR-30), asked exactly as a return would ask it, so the figure the
counter is shown is the figure a return today would charge. A unit that is
back accrues nothing more.

What the deposit is waiting on comes from `settlement_wait` in the domain,
which is the same rule the return asks before it settles the deposit (BR-32,
BR-53). So the screen and the settlement cannot disagree.

Whether a returned unit waits for its damage to be assessed comes from
`damage_assessment_of` in `app.domain.quarantine` (BR-35), asked with what the
read found, which is the two grades, the counter's flag and whether a damage
report names the unit. The settlement asks the same rule of the same facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final

from app.application.hire.read_models import RentalDetail, RentalItemDetail
from app.domain import quarantine
from app.domain.money import Money
from app.domain.policies.late_fee import LateFeePolicy
from app.domain.rental import NO_DAYS_LATE, DamageAssessment, SettlementWait
from app.domain.settlement import settlement_wait

NO_LATE_FEE: Final[Decimal] = Decimal("0.00")


@dataclass(frozen=True, slots=True)
class LateFeeToday:
    """What the late fee would be for one unit if it came back today.

    Attributes:
        days_late: The whole days it would be late.
        amount: The fee for those days, including VAT.

    """

    days_late: int
    amount: Decimal


def late_fee_if_returned_today(
    item: RentalItemDetail, due_back_on: date, today: date, policy: LateFeePolicy
) -> LateFeeToday:
    """Return the late fee a unit still out would carry if it came back today.

    Args:
        item: The unit, as it is stored.
        due_back_on: The day the hire was due back.
        today: The current business day, from the clock.
        policy: The late fee policy, asked as a return today would ask it.

    Returns:
        The days late and the fee, or nothing for a unit that is back.

    """
    if not item.is_out():
        return LateFeeToday(days_late=NO_DAYS_LATE, amount=NO_LATE_FEE)
    late = policy.late_fee(
        due_back_on=due_back_on,
        returned_on=today,
        fee_per_day=Money.create(item.late_fee_per_day),
    )
    return LateFeeToday(days_late=late.days_late, amount=late.amount.amount)


def damage_assessment_of(item: RentalItemDetail) -> DamageAssessment:
    """Return whether a unit of a rental waits for its damage to be assessed (BR-35)."""
    return quarantine.damage_assessment_of(
        condition_out=item.condition_out,
        condition_in=item.condition_in,
        flagged=item.flagged_for_damage,
        reported=item.damage_reported,
    )


def settlement_waiting_on(rental: RentalDetail) -> SettlementWait | None:
    """Return what the deposit of a rental waits on before it can be settled, or None."""
    return settlement_wait(
        status=rental.status,
        items_out=sum(item.is_out() for item in rental.items),
        assessments_due=sum(
            damage_assessment_of(item) is DamageAssessment.REQUIRED for item in rental.items
        ),
        balance_due=rental.balance_due,
    )
