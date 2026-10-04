"""The utilisation report as a CSV file, written a row at a time.

The first line is a comment that says these are gross contribution figures
and not profit, names the period and repeats the two definitions. The second
names the columns, which are the columns of the screen. A line for an asset
begins with its tag, model, category, branch and status, a line for a model
with its model and category, a line for a category with its category and a
line for a branch with its code and name, and every line then carries the same
figures. Money is written with two decimals and no currency sign, so a
spreadsheet can add it up, and a utilisation with no serviceable day is an
empty cell.

`report_csv_lines` is a generator, so the response streams one line at a time
and never holds the whole file. Every cell goes through `csv_row`, which
escapes anything a spreadsheet would run (C-32).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from decimal import Decimal
from types import MappingProxyType
from typing import Final

from app.api.csv_cells import csv_row
from app.application.reporting.definitions import (
    GROSS_CONTRIBUTION_DEFINITION,
    NOT_PROFIT_NOTICE,
    UTILISATION_DEFINITION,
)
from app.application.reporting.report_models import GroupBy, ReportLine, UtilisationReport

COMMENT_MARK: Final[str] = "#"
MONEY_FORMAT: Final[str] = "{:.2f}"
NO_VALUE: Final[str] = ""
FILENAME_PATTERN: Final[str] = "toolshed-gross-contribution-{group_by}-{starts}-{ends}.csv"
FIGURE_HEADINGS: Final[tuple[str, ...]] = (
    "Units",
    "Days on hire",
    "Serviceable days",
    "Utilisation percent",
    "Hire revenue ex VAT",
    "Late fees ex VAT",
    "Damage recovery ex VAT",
    "Repair costs",
    "Gross contribution",
)

type CellOf = Callable[[ReportLine], str]

# The columns that say what a line stands for, by grouping, each with its heading.
IDENTITY_COLUMNS: Final[Mapping[GroupBy, tuple[tuple[str, CellOf], ...]]] = MappingProxyType(
    {
        GroupBy.ASSET: (
            ("Asset tag", lambda line: line.key),
            ("Model", lambda line: line.model_name or NO_VALUE),
            ("Category", lambda line: line.category_name or NO_VALUE),
            ("Branch", lambda line: line.branch_code or NO_VALUE),
            ("Status", lambda line: line.status.value if line.status else NO_VALUE),
        ),
        GroupBy.MODEL: (
            ("Model", lambda line: line.label),
            ("Category", lambda line: line.category_name or NO_VALUE),
        ),
        GroupBy.CATEGORY: (("Category", lambda line: line.label),),
        GroupBy.BRANCH: (
            ("Branch code", lambda line: line.key),
            ("Branch", lambda line: line.label),
        ),
    }
)


def report_filename(report: UtilisationReport) -> str:
    """Return the name the file is saved under."""
    return FILENAME_PATTERN.format(
        group_by=report.group_by.value,
        starts=report.starts_on.isoformat(),
        ends=report.ends_on.isoformat(),
    )


def report_csv_lines(report: UtilisationReport) -> Iterator[str]:
    """Yield the file a line at a time, the comment first, then the headings, then every line."""
    columns = IDENTITY_COLUMNS[report.group_by]
    yield csv_row([_comment(report)])
    yield csv_row([*(heading for heading, _cell in columns), *FIGURE_HEADINGS])
    for line in report.lines:
        yield csv_row([*(cell(line) for _heading, cell in columns), *_figures(line)])


def _comment(report: UtilisationReport) -> str:
    """Return the comment the file opens with."""
    return (
        f"{COMMENT_MARK} {NOT_PROFIT_NOTICE} The period is {report.starts_on.isoformat()} up "
        f"to but not including {report.ends_on.isoformat()}. {UTILISATION_DEFINITION} "
        f"{GROSS_CONTRIBUTION_DEFINITION}"
    )


def _figures(line: ReportLine) -> list[str]:
    """Return the figure cells of one line."""
    parts = line.contribution
    return [
        str(line.asset_count),
        str(line.days_on_hire),
        str(line.serviceable_days),
        _decimal(line.utilisation_percent),
        _decimal(parts.hire_revenue.amount),
        _decimal(parts.late_fees.amount),
        _decimal(parts.damage_recovery.amount),
        _decimal(parts.repair_costs.amount),
        _decimal(parts.gross_contribution.amount),
    ]


def _decimal(value: Decimal | None) -> str:
    """Return a figure with two decimals, or an empty cell for none."""
    return MONEY_FORMAT.format(value) if value is not None else NO_VALUE
