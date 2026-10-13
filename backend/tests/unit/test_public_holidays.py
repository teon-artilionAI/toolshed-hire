"""The public holidays of South Africa, worked out from the Public Holidays Act.

The expected lists are the ones the government publishes at
https://www.gov.za/about-sa/public-holidays, read on 13 October 2026. The 2027
list there leaves out Monday 27 December, although Day of Goodwill falls on a
Sunday that year and section 2(1) of the Act makes the Monday after it a public
holiday. The Act is the authority, so the calendar includes the day and this
test says why.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.domain.public_holidays import (
    EARLIEST_YEAR,
    LATEST_YEAR,
    easter_sunday,
    holiday_on,
    public_holidays,
)

PUBLISHED_2026: dict[date, str] = {
    date(2026, 1, 1): "New Year's Day",
    date(2026, 3, 21): "Human Rights Day",
    date(2026, 4, 3): "Good Friday",
    date(2026, 4, 6): "Family Day",
    date(2026, 4, 27): "Freedom Day",
    date(2026, 5, 1): "Workers' Day",
    date(2026, 6, 16): "Youth Day",
    date(2026, 8, 9): "National Women's Day",
    date(2026, 8, 10): "National Women's Day observed",
    date(2026, 9, 24): "Heritage Day",
    date(2026, 12, 16): "Day of Reconciliation",
    date(2026, 12, 25): "Christmas Day",
    date(2026, 12, 26): "Day of Goodwill",
}

PUBLISHED_2027: dict[date, str] = {
    date(2027, 1, 1): "New Year's Day",
    date(2027, 3, 21): "Human Rights Day",
    date(2027, 3, 22): "Human Rights Day observed",
    date(2027, 3, 26): "Good Friday",
    date(2027, 3, 29): "Family Day",
    date(2027, 4, 27): "Freedom Day",
    date(2027, 5, 1): "Workers' Day",
    date(2027, 6, 16): "Youth Day",
    date(2027, 8, 9): "National Women's Day",
    date(2027, 9, 24): "Heritage Day",
    date(2027, 12, 16): "Day of Reconciliation",
    date(2027, 12, 25): "Christmas Day",
    date(2027, 12, 26): "Day of Goodwill",
}

# Missing from the published 2027 list, required by section 2(1) of the Act.
DAY_OF_GOODWILL_2027_OBSERVED = date(2027, 12, 27)


class TestThePublishedLists:
    """The answers for 2026 and 2027 against the government's list."""

    def test_2026_matches_the_published_list_exactly(self) -> None:
        assert dict(public_holidays(2026)) == PUBLISHED_2026

    def test_2027_matches_the_published_list_and_adds_the_monday_the_act_requires(
        self,
    ) -> None:
        expected = {**PUBLISHED_2027, DAY_OF_GOODWILL_2027_OBSERVED: "Day of Goodwill observed"}

        assert dict(public_holidays(2027)) == expected


class TestTheSundayRule:
    """Section 2(1), a holiday on a Sunday makes the Monday a holiday."""

    def test_a_holiday_on_a_sunday_makes_the_monday_a_holiday(self) -> None:
        assert date(2026, 8, 9).isoweekday() == 7
        assert holiday_on(date(2026, 8, 10)) == "National Women's Day observed"

    def test_a_monday_that_is_already_a_holiday_is_not_doubled(self) -> None:
        # Christmas 2022 fell on a Sunday and the Monday was already Day of
        # Goodwill. The Act adds no third day, so none is invented here.
        holidays = public_holidays(2022)

        assert holidays[date(2022, 12, 26)] == "Day of Goodwill"
        assert date(2022, 12, 27) not in holidays


class TestEaster:
    """Good Friday and Family Day hang on Easter, so Easter has to be right."""

    @pytest.mark.parametrize(
        ("year", "expected"),
        [
            (2024, date(2024, 3, 31)),
            (2025, date(2025, 4, 20)),
            (2026, date(2026, 4, 5)),
            (2027, date(2027, 3, 28)),
            (2038, date(2038, 4, 25)),
        ],
    )
    def test_easter_sunday_falls_where_the_church_calendar_puts_it(
        self, year: int, expected: date
    ) -> None:
        assert easter_sunday(year) == expected


class TestTheAnswer:
    """What a caller gets back, and what it may not ask."""

    def test_an_ordinary_day_is_no_holiday(self) -> None:
        assert holiday_on(date(2026, 10, 14)) is None

    def test_the_answer_cannot_be_changed_by_a_caller(self) -> None:
        holidays = public_holidays(2026)

        with pytest.raises(TypeError):
            holidays[date(2026, 10, 14)] = "Invented"  # type: ignore[index]

    @pytest.mark.parametrize("year", [EARLIEST_YEAR - 1, LATEST_YEAR + 1])
    def test_a_year_no_hire_could_ask_about_is_refused(self, year: int) -> None:
        with pytest.raises(ValueError, match=str(year)):
            public_holidays(year)
