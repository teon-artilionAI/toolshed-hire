"""Writing one row of a CSV file so a spreadsheet cannot run any cell of it (C-32).

A spreadsheet treats a cell that begins with `=`, `+`, `-` or `@` as a formula,
and a tab or a carriage return at the front can smuggle one past a check of
the first character. A label typed into the system, a model name for example,
could otherwise become a formula on the owner's machine. Every such cell is
written with a single quote in front, which the spreadsheet shows as text.

The rule is applied to every cell, whatever its column, because C-32 names
the characters and not the columns. The one cell it leaves alone is a plain
decimal number such as `-180.00`, because a spreadsheet can only read that as
a number and never as a formula, and the owner needs negative amounts to add
up. Anything else that starts with a minus sign, `-1+2` for example, is still
escaped.

Quoting, commas inside a cell and the line ending are the standard library's
`csv` module, with the carriage return and line feed RFC 4180 names.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable
from typing import Final

FORMULA_TRIGGERS: Final[tuple[str, ...]] = ("=", "+", "-", "@", "\t", "\r")
ESCAPE_PREFIX: Final[str] = "'"
# A whole cell that is a plain decimal number, which no spreadsheet runs.
PLAIN_NUMBER: Final[re.Pattern[str]] = re.compile(r"-?\d+(\.\d+)?")
LINE_ENDING: Final[str] = "\r\n"


def escaped_cell(cell: str) -> str:
    """Return a cell with a single quote in front when a spreadsheet would read it as a formula."""
    if PLAIN_NUMBER.fullmatch(cell):
        return cell
    return f"{ESCAPE_PREFIX}{cell}" if cell.startswith(FORMULA_TRIGGERS) else cell


def csv_row(cells: Iterable[str]) -> str:
    """Return one line of CSV, every cell escaped and quoted where it needs to be."""
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator=LINE_ENDING).writerow(
        [escaped_cell(cell) for cell in cells]
    )
    return buffer.getvalue()
