"""Where a rental stands on the way to being settled, one replaceable function per question.

A rental is read with three answers that belong to the changes after this one.
What the late fee would be if a unit came back today belongs to the late fee
policy (BR-30). Whether a returned unit waits for its damage to be assessed
belongs to damage and quarantine (BR-35). What the deposit is waiting on before
it can be settled belongs to returns and settlement (BR-32, BR-53).

Each answer is worked out here by one function, and each function is the one
thing its change replaces. Until then they answer as a rental that has just
gone out stands. Nothing is late yet, nothing needs assessing, and the deposit
waits for the units to come back.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final

from app.application.hire.read_models import RentalDetail, RentalItemDetail
from app.domain.rental import NO_DAYS_LATE, DamageAssessment, SettlementWait

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


def late_fee_if_returned_today(item: RentalItemDetail, today: date) -> LateFeeToday:
    """Return the late fee a unit still out would carry if it came back today.

    The late fee policy is the next change. Until it is built nothing accrues,
    so this answers nothing for every unit, whether it is out or back.
    """
    return LateFeeToday(days_late=NO_DAYS_LATE, amount=NO_LATE_FEE)


def damage_assessment_of(item: RentalItemDetail) -> DamageAssessment:
    """Return whether a unit waits for its damage to be assessed.

    Damage and quarantine come later. Until then no unit is ever flagged.
    """
    return DamageAssessment.NOT_NEEDED


def settlement_waiting_on(rental: RentalDetail) -> SettlementWait | None:
    """Return what the deposit of a rental waits on before it can be settled.

    Returns and settlement come later. Until then a rental with a unit out
    waits for it, and one with nothing out waits on nothing, which is the
    closed hire of the worked example.
    """
    return SettlementWait.ITEMS_OUT if any(item.is_out() for item in rental.items) else None
