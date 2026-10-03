"""The standard late fee policy, which is the rule of BR-30 and BR-31.

A unit that comes back late is charged the late fee per day copied onto its
booking for each whole day between the day it was due back and the day it
came back. A return on the due date is charged nothing. Accrual stops after
fourteen days, so a unit that never comes back owes at most fourteen days of
late fee, and from the fifteenth day it may be recorded as lost.

This class is the only place in the system that multiplies a late fee per day
by a number of days. A test reads the source of every other module to keep it
that way.
"""

from __future__ import annotations

from datetime import date
from typing import Final

from app.domain.money import Money
from app.domain.policies.late_fee import LateFee, ensure_fee_per_day, whole_days_late

STANDARD_LATE_FEE_POLICY_NAME: Final[str] = "standard-late-fee"


class StandardLateFeePolicy:
    """Each whole day late at the fee per day, for at most fourteen days."""

    # Late fee stops accruing on a unit after this many days (BR-31). A unit
    # later than this may be recorded as lost.
    ACCRUAL_LIMIT_DAYS: Final[int] = 14

    def name(self) -> str:
        """Return the name the policy is logged under."""
        return STANDARD_LATE_FEE_POLICY_NAME

    def late_fee(self, *, due_back_on: date, returned_on: date, fee_per_day: Money) -> LateFee:
        """Return what one unit owes for coming back on a day, by the rule of BR-30.

        Args:
            due_back_on: The day the unit was due back, a business day.
            returned_on: The day it came back, or today if it is still out.
            fee_per_day: The late fee per day copied onto its booking,
                including VAT.

        Returns:
            The days late, the days charged, which stop at fourteen, and the
            fee including VAT, rounded to the cent.

        Raises:
            InvalidLateFeeInput: If the fee per day is not Money or is negative.

        """
        ensure_fee_per_day(fee_per_day)
        days_late = whole_days_late(due_back_on, returned_on)
        chargeable_days = min(days_late, self.ACCRUAL_LIMIT_DAYS)
        return LateFee(
            days_late=days_late,
            chargeable_days=chargeable_days,
            amount=fee_per_day.times(chargeable_days).rounded(),
            beyond_accrual=days_late > self.ACCRUAL_LIMIT_DAYS,
        )
