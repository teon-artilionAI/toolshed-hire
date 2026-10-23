"""The month's charges, for the bookkeeper (B13.3, FR-24).

The export is every charge raised in one calendar month, at one branch or at
every branch. It includes hire charges, late fees, damage recoveries and the
three deposit movements, because all of them are rows in the one ledger. A
deposit taken, released or forfeited is therefore in the same file as the
charge it belongs to, which is what lets the bookkeeper reconcile the month.

The read is a query object over the request session, like the utilisation
report. It takes two statements whatever the month holds: one for the branch,
when a branch was named, and one for the charges. The totals are summed as the
rows are read, so the file and its totals come from the same data.

The month is a calendar month in the business's own day count. The first day
is included and the first day of the next month is excluded.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Final, Protocol
from uuid import UUID

from app.application.refusal import refused
from app.domain.enums import ChargeStatus, ChargeType
from app.domain.identity import Actor

logger = logging.getLogger(__name__)

MONTH_PARAMETER: Final[str] = "month"
BRANCH_PARAMETER: Final[str] = "branchCode"
NOTHING: Final[Decimal] = Decimal("0.00")
MONTH_FORMAT_MESSAGE: Final[str] = "Give the month as YYYY-MM, for example 2026-10."
UNKNOWN_BRANCH_MESSAGE: Final[str] = "Choose one of our branches."


@dataclass(frozen=True, slots=True)
class MonthlyChargeLine:
    """One charge in the month, as the bookkeeper reads it."""

    charge_id: UUID
    raised_at: datetime
    rental_reference: str
    customer_name: str
    branch_code: str
    charge_type: ChargeType
    description: str
    amount_ex_vat: Decimal
    vat_amount: Decimal
    amount_inc_vat: Decimal
    status: ChargeStatus
    settled_at: datetime | None
    reverses_charge_id: UUID | None
    waiver_reason: str | None


@dataclass(frozen=True, slots=True)
class MonthlyChargeTotals:
    """The sums over every charge in the month."""

    charge_count: int
    amount_ex_vat: Decimal
    vat_amount: Decimal
    amount_inc_vat: Decimal
    deposit_held: Decimal
    deposit_released: Decimal
    deposit_forfeited: Decimal


@dataclass(frozen=True, slots=True)
class MonthlyCharges:
    """One month's charges and their totals."""

    month_start: date
    month_end: date
    branch_code: str | None
    lines: tuple[MonthlyChargeLine, ...]

    @property
    def totals(self) -> MonthlyChargeTotals:
        """Return the sums over every line."""
        held = sum(
            (
                line.amount_inc_vat
                for line in self.lines
                if line.charge_type is ChargeType.DEPOSIT_HOLD
            ),
            NOTHING,
        )
        released = sum(
            (
                line.amount_inc_vat
                for line in self.lines
                if line.charge_type is ChargeType.DEPOSIT_RELEASE
            ),
            NOTHING,
        )
        forfeited = sum(
            (
                line.amount_inc_vat
                for line in self.lines
                if line.charge_type is ChargeType.DEPOSIT_FORFEIT
            ),
            NOTHING,
        )
        return MonthlyChargeTotals(
            charge_count=len(self.lines),
            amount_ex_vat=sum((line.amount_ex_vat for line in self.lines), NOTHING),
            vat_amount=sum((line.vat_amount for line in self.lines), NOTHING),
            amount_inc_vat=sum((line.amount_inc_vat for line in self.lines), NOTHING),
            deposit_held=held,
            deposit_released=released,
            deposit_forfeited=forfeited,
        )


@dataclass(frozen=True, slots=True)
class MonthlyChargeQuery:
    """Which month of charges the owner wants."""

    actor: Actor
    month: str
    branch_code: str | None = None


class MonthlyChargeRead(Protocol):
    """The charges of one month."""

    def read(self, month_start: date, month_end: date, branch_code: str | None) -> MonthlyCharges:
        """Return the charges of a month, optionally at one branch."""
        ...


class ReadMonthlyCharges:
    """Read one month of charges for the bookkeeper."""

    def __init__(self, read: MonthlyChargeRead) -> None:
        """Keep the query object the charges are read through."""
        self._read = read

    def execute(self, query: MonthlyChargeQuery) -> MonthlyCharges:
        """Return the month, or refuse the month or branch that cannot be read."""
        month_start = _month_start(query.month)
        month_end = _next_month(month_start)
        logger.info(
            "reporting.monthly_charges_requested",
            extra={
                "actor_user_id": str(query.actor.user_id),
                "month": query.month,
                "branch_code": query.branch_code,
            },
        )
        charges = self._read.read(month_start, month_end, query.branch_code)
        logger.info(
            "reporting.monthly_charges_read",
            extra={"charge_count": len(charges.lines), "month": query.month},
        )
        return charges


def _month_start(value: str) -> date:
    """Return the first day of a YYYY-MM month. Raises ValidationFailure naming `month`."""
    parts = value.split("-")
    if len(parts) != 2 or len(parts[0]) != 4 or len(parts[1]) != 2:
        raise refused(MONTH_PARAMETER, MONTH_FORMAT_MESSAGE)
    try:
        year, month = int(parts[0]), int(parts[1])
        return date(year, month, 1)
    except ValueError as error:
        raise refused(MONTH_PARAMETER, MONTH_FORMAT_MESSAGE) from error


def _next_month(first: date) -> date:
    """Return the first day of the month after `first`."""
    year = first.year + (1 if first.month == 12 else 0)
    month = 1 if first.month == 12 else first.month + 1
    return date(year, month, 1)


__all__ = [
    "MonthlyChargeLine",
    "MonthlyChargeQuery",
    "MonthlyCharges",
    "MonthlyChargeTotals",
    "ReadMonthlyCharges",
]
