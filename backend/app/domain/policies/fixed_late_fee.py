"""A late fee policy for tests, which charges the same amount for any unit that is late.

A test of a return wants a fee it can state in one line, without counting the
days to find it. This policy charges one fixed amount for a unit that is late
at all, however late it is and whatever fee per day its booking carries. It
counts the days late the same way the standard policy does, and it stops
charging for days at the same limit, so a unit is beyond accrual on the same
day under both.

It lives beside the standard policy because the design document places the
two Strategies there. Nothing in the running application builds one.
"""

from __future__ import annotations

from datetime import date
from typing import Final

from app.domain.money import Money
from app.domain.policies.late_fee import (
    NO_DAYS,
    InvalidLateFeeInput,
    LateFee,
    ensure_fee_per_day,
    whole_days_late,
)
from app.domain.policies.standard_late_fee import StandardLateFeePolicy

FIXED_LATE_FEE_POLICY_NAME: Final[str] = "fixed-late-fee"


class FixedLateFeePolicy:
    """One fixed fee for a unit that is late at all."""

    # The same limit as the standard policy, so the day a unit may be
    # recorded as lost does not depend on which policy a test uses.
    ACCRUAL_LIMIT_DAYS: Final[int] = StandardLateFeePolicy.ACCRUAL_LIMIT_DAYS

    def __init__(self, fee: Money) -> None:
        """Keep the fee a late unit is charged.

        Args:
            fee: What a late unit owes, however late it is, including VAT.

        Raises:
            InvalidLateFeeInput: If the fee is not Money, or is negative.

        """
        if not isinstance(fee, Money) or fee.is_negative():
            raise InvalidLateFeeInput(
                f"Attempted to build a fixed late fee policy charging {fee!r}. A late fee is "
                "Money and is never negative."
            )
        self._fee = fee.rounded()

    def name(self) -> str:
        """Return the name the policy is logged under."""
        return FIXED_LATE_FEE_POLICY_NAME

    def late_fee(self, *, due_back_on: date, returned_on: date, fee_per_day: Money) -> LateFee:
        """Return the fixed fee for a unit that came back late, and nothing for one that did not.

        Raises:
            InvalidLateFeeInput: If the fee per day is not Money or is negative.

        """
        ensure_fee_per_day(fee_per_day)
        days_late = whole_days_late(due_back_on, returned_on)
        return LateFee(
            days_late=days_late,
            chargeable_days=min(days_late, self.ACCRUAL_LIMIT_DAYS),
            amount=self._fee if days_late > NO_DAYS else Money.zero().rounded(),
            beyond_accrual=days_late > self.ACCRUAL_LIMIT_DAYS,
        )
