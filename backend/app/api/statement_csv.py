"""A customer's statement as a CSV file, written one row at a time (FR-28, C-32).

The file opens with a comment that names the customer, the period and the
totals. Then every hire and every charge is one row, with the deposit figures
the ledger recorded. A hire with no charge still gets a row, so a deposit that
was taken but not yet settled is visible. Every cell goes through `csv_row`,
which stops a spreadsheet from running a description or a note as a formula.

The generator is lazy, so the response streams and never holds the whole file.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import Final

from app.api.csv_cells import csv_row
from app.application.hire.read_models import ChargeDetail
from app.application.hire.statement import Statement, StatementLine

COMMENT_MARK: Final[str] = "#"
MONEY_FORMAT: Final[str] = "{:.2f}"
EMPTY: Final[str] = ""
HEADINGS: Final[tuple[str, ...]] = (
    "Hire reference",
    "Branch",
    "From",
    "Due back",
    "Checked out",
    "Returned",
    "Hire status",
    "Charge date",
    "Charge type",
    "Description",
    "Amount ex VAT",
    "VAT",
    "Amount inc VAT",
    "Charge status",
    "Deposit held",
    "Deposit withheld",
    "Deposit refunded",
    "Balance due",
)
FILENAME_PATTERN: Final[str] = "toolshed-statement-{starts}-{ends}.csv"


def statement_filename(statement: Statement) -> str:
    """Return the name the file is saved under."""
    return FILENAME_PATTERN.format(
        starts=statement.starts_on.isoformat(), ends=statement.ends_on.isoformat()
    )


def statement_csv_lines(statement: Statement) -> Iterator[str]:
    """Yield the statement a line at a time, comment first, then headings, then rows."""
    yield csv_row([_comment(statement)])
    yield csv_row(HEADINGS)
    for line in statement.lines:
        if line.charges:
            for charge in line.charges:
                yield csv_row([*_hire_cells(line), *_charge_cells(charge)])
        else:
            yield csv_row([*_hire_cells(line), *(_empty_charge_cells())])


def _comment(statement: Statement) -> str:
    """Return the comment the file opens with, including the totals."""
    totals = statement.totals
    return (
        f"{COMMENT_MARK} Statement for {statement.customer_name} "
        f"({statement.customer_email}) from {statement.starts_on.isoformat()} up to but not "
        f"including {statement.ends_on.isoformat()}. Hires: {totals.hire_count}. Charges inc "
        f"VAT: {_money(totals.charges_total_inc_vat)}. Deposits held: "
        f"{_money(totals.deposit_held)}. Withheld: {_money(totals.deposit_withheld)}. "
        f"Refunded: {_money(totals.deposit_refunded)}. Balance due: "
        f"{_money(totals.balance_due)}."
    )


def _hire_cells(line: StatementLine) -> list[str]:
    """Return the cells that describe one hire."""
    return [
        line.reference,
        line.branch_code,
        line.starts_on.isoformat(),
        line.due_back_on.isoformat(),
        line.checked_out_at.date().isoformat(),
        line.returned_at.date().isoformat() if line.returned_at is not None else EMPTY,
        line.status.value,
        EMPTY,
        EMPTY,
        EMPTY,
        EMPTY,
        EMPTY,
        EMPTY,
        EMPTY,
        _money(line.deposit_held),
        _money(line.deposit_withheld),
        _money(line.deposit_refunded),
        _money(line.balance_due),
    ]


def _charge_cells(charge: ChargeDetail) -> list[str]:
    """Return the cells that describe one charge."""
    return [
        EMPTY,
        EMPTY,
        EMPTY,
        EMPTY,
        EMPTY,
        EMPTY,
        EMPTY,
        charge.raised_at.date().isoformat(),
        charge.charge_type.value,
        charge.description,
        _money(charge.amount_ex_vat),
        _money(charge.vat_amount),
        _money(charge.amount_inc_vat),
        charge.status.value,
        EMPTY,
        EMPTY,
        EMPTY,
        EMPTY,
    ]


def _empty_charge_cells() -> list[str]:
    """Return the charge columns left empty on a hire with no charges."""
    return [EMPTY] * 7


def _money(value: Decimal) -> str:
    """Return an amount with two decimals and no currency sign."""
    return MONEY_FORMAT.format(value)


__all__ = ["statement_csv_lines", "statement_filename"]
