"""A CSV cell a spreadsheet would run as a formula is written as text (C-32), with no database."""

from __future__ import annotations

import pytest

from app.api.csv_cells import csv_row, escaped_cell


class TestTheEscape:
    """A cell that begins with a formula character gets a single quote in front."""

    @pytest.mark.parametrize(
        "cell",
        ["=SUM(A1:A9)", "+27 21 555 0101", "-1+2", "-A1", "@cmd", "\tleading tab", "\rreturn"],
    )
    def test_a_cell_a_spreadsheet_would_run_is_escaped(self, cell: str) -> None:
        assert escaped_cell(cell) == f"'{cell}"

    @pytest.mark.parametrize(
        "cell", ["TSH-HM-0001", "212.63", "Bosch GBH 2-26", "", "a=b", "-180.00", "-7"]
    )
    def test_any_other_cell_is_left_as_it_is(self, cell: str) -> None:
        assert escaped_cell(cell) == cell


class TestTheRow:
    """A row is quoted where it needs to be and ends the way RFC 4180 says."""

    def test_a_row_ends_with_a_carriage_return_and_a_line_feed(self) -> None:
        assert csv_row(["TSH-HM-0001", "212.63"]) == "TSH-HM-0001,212.63\r\n"

    def test_a_cell_with_a_comma_or_a_quote_is_quoted(self) -> None:
        assert csv_row(['Mixer, 140 L', 'The "big" one']) == '"Mixer, 140 L","The ""big"" one"\r\n'

    def test_every_cell_of_a_row_is_escaped(self) -> None:
        assert csv_row(["=1+1", "-5.00", "-5-5"]) == "'=1+1,-5.00,'-5-5\r\n"
