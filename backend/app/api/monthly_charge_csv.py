"""The month's charges as a CSV file, written a row at a time (B13.3, C-32).

The comment names the month, the branch and the totals. Then every charge is
one row, and the last row repeats the totals so a spreadsheet can read them
without parsing the comment. Every cell goes through `csv_row`, so a
description or a waiver reason cannot run as a formula.

The generator is lazy, so a month with many charges streams instead of being
held as one string.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import Final

from app.api.csv_cells import csv_row
from app.application.reporting.monthly_charges import MonthlyCharges

COMMENT_MARK: Final[str] = "#"
MONEY_FORMAT: Final[str] = "{:.2f}"
EMPTY: Final[str] = ""
HEADINGS: Final[tuple[str, ...]] = (
    "Charge date",
    "Hire reference",
    "Customer",
    "Branch",
    "Charge type",
    "Description",
    "Amount ex VAT",
    "VAT",
    "Amount inc VAT",
    "Charge status",
    "Settled at",
    "Reverses charge",
    "Waiver reason",
)
FILENAME_PATTERN: Final[str] = "toolshed-charges-{month}{branch}.csv"


def monthly_charge_filename(charges: MonthlyCharges) -> str:
    """Return the name the file is saved under."""
    branch = f"-{charges.branch_code}" if charges.branch_code is not None else ""
    return FILENAME_PATTERN.format(month=charges.month_start.strftime("%Y-%m"), branch=branch)


def monthly_charge_csv_lines(charges: MonthlyCharges) -> Iterator[str]:
    """Yield the file a line at a time, the comment first, then the rows and the totals."""
    yield csv_row([_comment(charges)])
    yield csv_row(HEADINGS)
    for line in charges.lines:
        yield csv_row(
            [
                line.raised_at.date().isoformat(),
                line.rental_reference,
                line.customer_name,
                line.branch_code,
                line.charge_type.value,
                line.description,
                _money(line.amount_ex_vat),
                _money(line.vat_amount),
                _money(line.amount_inc_vat),
                line.status.value,
                line.settled_at.date().isoformat() if line.settled_at is not None else EMPTY,
                str(line.reverses_charge_id) if line.reverses_charge_id is not None else EMPTY,
                line.waiver_reason or EMPTY,
            ]
        )
    totals = charges.totals
    yield csv_row(
        [
            "Totals",
            EMPTY,
            EMPTY,
            EMPTY,
            EMPTY,
            f"{totals.charge_count} charges",
            _money(totals.amount_ex_vat),
            _money(totals.vat_amount),
            _money(totals.amount_inc_vat),
            EMPTY,
            EMPTY,
            EMPTY,
            f"Deposits held {_money(totals.deposit_held)}, released "
            f"{_money(totals.deposit_released)}, forfeited {_money(totals.deposit_forfeited)}",
        ]
    )


def _comment(charges: MonthlyCharges) -> str:
    """Return the comment the file opens with."""
    branch = charges.branch_code or "every branch"
    return (
        f"{COMMENT_MARK} Charges for {charges.month_start.strftime('%B %Y')} at {branch}. "
        "Every amount is a row from the ledger, deposits included."
    )


def _money(value: Decimal) -> str:
    """Return an amount with two decimals and no currency sign."""
    return MONEY_FORMAT.format(value)


__all__ = ["monthly_charge_csv_lines", "monthly_charge_filename"]
