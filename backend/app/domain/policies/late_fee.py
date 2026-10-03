"""The late fee a hire has run up so far, for the counter's overdue list (BR-30, BR-31).

The late fee policy of the next change replaces this module. That policy is a
strategy beside the pricing policy, and it works out the whole days late of a
unit and the fee they carry when the unit comes back. Until it is built the
counter's dashboard still has to say what an overdue hire has run up, so this
one function works it out the plain way the rules give.

A unit still out accrues the late fee per day copied onto its booking (BR-20)
for each whole day since the day it was due back, and stops accruing after
fourteen days (BR-31). A return on the due date accrues nothing, which follows
from the half open period. A late fee is an amount that includes VAT, so
nothing is added to it.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Final

from app.domain.money import Money

# Late fee stops accruing on a unit after fourteen days (BR-31).
LATE_FEE_CAP_DAYS: Final[int] = 14
NO_DAYS: Final[int] = 0


def late_fee_accrued(fees_per_day_of_units_out: Iterable[Decimal], days_overdue: int) -> Money:
    """Return the late fee a hire has run up so far, rounded to the cent.

    The late fee policy of the next change replaces this function.

    Args:
        fees_per_day_of_units_out: The late fee per day of each unit still out.
        days_overdue: The whole days since the day the hire was due back. Zero
            or fewer means nothing has accrued.

    """
    chargeable_days = min(max(days_overdue, NO_DAYS), LATE_FEE_CAP_DAYS)
    accrued = Money.zero()
    for fee_per_day in fees_per_day_of_units_out:
        accrued = accrued.add(Money.create(fee_per_day).times(chargeable_days))
    return accrued.rounded()
