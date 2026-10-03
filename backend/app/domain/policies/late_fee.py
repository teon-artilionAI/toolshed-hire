"""The late fee policy port, and what a policy is asked with and answers (BR-30, BR-31).

BR-30 says a late fee is produced by a late fee policy, which the design
document names beside the pricing policy as the second Strategy. A policy is
asked about one unit at a time, because a late fee accrues per asset, with
the day the unit was due back, the day it came back or would come back, and
the late fee per day copied onto its booking (BR-20). It never looks one up.

Both days are business days in Cape Town. The due date is the end of the half
open hire period, the day the unit comes back, so a return on that day is not
late and accrues nothing. Each whole day after it is one day late.

A policy answers with a `LateFee`, which carries the whole days late, the days
it charged for and the fee for them. The fee includes VAT, so two days at
R120.00 is R240.00 and nothing is added to it. How that amount is written as a
charge, R208.70 plus R31.30 VAT, is `app.domain.vat.split_vat_inclusive`.

Accrual stops after a number of days the policy names (BR-31). A unit later
than that is no longer simply late, and `beyond_accrual` says so. It is the
answer the loss of a unit is decided by.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final, Protocol

from app.domain.money import Money

NO_DAYS: Final[int] = 0


class InvalidLateFeeInput(ValueError):
    """Raised when a policy is asked about a unit no late fee could be worked out for."""


@dataclass(frozen=True, slots=True)
class LateFee:
    """What a unit owes for coming back late.

    Attributes:
        days_late: The whole days between the due date and the return, never
            below nought.
        chargeable_days: The days the fee was charged for, which stop at the
            policy's limit.
        amount: The fee, including VAT, rounded to the cent.
        beyond_accrual: True when the unit is later than the policy charges
            for, which is when it may be recorded as lost (BR-31).

    """

    days_late: int
    chargeable_days: int
    amount: Money
    beyond_accrual: bool

    def is_due(self) -> bool:
        """Return True when there is a fee to charge."""
        return self.amount > Money.zero()


class LateFeePolicy(Protocol):
    """How late a unit is and what that costs. The Strategy the design document names for BR-30."""

    def name(self) -> str:
        """Return the name the policy is logged under."""
        ...

    def late_fee(self, *, due_back_on: date, returned_on: date, fee_per_day: Money) -> LateFee:
        """Return what one unit owes for coming back on a day.

        Args:
            due_back_on: The day the unit was due back, a business day.
            returned_on: The day it came back, or the day it is asked about
                if it is still out, a business day.
            fee_per_day: The late fee per day copied onto its booking,
                including VAT.

        Raises:
            InvalidLateFeeInput: If the fee per day is not Money or is negative.

        """
        ...


def whole_days_late(due_back_on: date, returned_on: date) -> int:
    """Return the whole days a unit came back after its due date, and nought for none.

    A return on the due date or before it is not late.
    """
    return max((returned_on - due_back_on).days, NO_DAYS)


def ensure_fee_per_day(fee_per_day: Money) -> None:
    """Refuse a late fee per day no booking could carry.

    Raises:
        InvalidLateFeeInput: If it is not Money, or is negative.

    """
    if not isinstance(fee_per_day, Money) or fee_per_day.is_negative():
        raise InvalidLateFeeInput(
            f"Attempted to work out a late fee at {fee_per_day!r} a day. A late fee per day "
            "is Money and is never negative."
        )
