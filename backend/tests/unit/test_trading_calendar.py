"""The trading calendar of a branch, and the refusal of a hire on a closed day.

The dates are in October 2026. Saturday the seventeenth is a short day,
Sunday the eighteenth is closed, and the owner closes the branch on Tuesday the
twentieth for a stocktake. Christmas and Day of Goodwill fall on a Friday and a
Saturday, so the next open day after Christmas is Monday the twenty eighth.
"""

from __future__ import annotations

from datetime import date, time

import pytest

from app.domain.errors import ValidationFailure
from app.domain.trading_calendar import (
    CLOSED_DAY_RULE,
    LONGEST_CLOSURE_DAYS,
    OWNER_CLOSURE,
    PUBLIC_HOLIDAY_CLOSURE,
    STANDARD_CLOSES_AT,
    STANDARD_OPENS_AT,
    STANDARD_SATURDAY_CLOSES_AT,
    WEEKLY_CLOSURE,
    BranchCalendar,
    OpeningHours,
    day_in_words,
    ensure_open_on,
)

WEDNESDAY = date(2026, 10, 14)
SATURDAY = date(2026, 10, 17)
SUNDAY = date(2026, 10, 18)
MONDAY = date(2026, 10, 19)
STOCKTAKE = date(2026, 10, 20)
CHRISTMAS = date(2026, 12, 25)
AFTER_THE_HOLIDAYS = date(2026, 12, 28)

CALENDAR = BranchCalendar.standard({STOCKTAKE: "stocktake"})


class TestTheStandardWeek:
    """The hours the design gives every branch."""

    def test_a_weekday_runs_from_seven_to_five(self) -> None:
        assert CALENDAR.hours_on(WEDNESDAY) == OpeningHours(STANDARD_OPENS_AT, STANDARD_CLOSES_AT)

    def test_a_saturday_closes_at_one(self) -> None:
        hours = CALENDAR.hours_on(SATURDAY)

        assert hours is not None
        assert hours.closes == STANDARD_SATURDAY_CLOSES_AT

    def test_a_sunday_is_closed(self) -> None:
        closed = CALENDAR.closed_day(SUNDAY)

        assert closed is not None
        assert closed.kind == WEEKLY_CLOSURE
        assert CALENDAR.hours_on(SUNDAY) is None


class TestHolidaysAndClosures:
    """Public holidays and the owner's closure days close a branch on any weekday."""

    def test_a_public_holiday_is_closed_even_on_a_weekday(self) -> None:
        closed = CALENDAR.closed_day(CHRISTMAS)

        assert closed is not None
        assert (closed.kind, closed.reason) == (PUBLIC_HOLIDAY_CLOSURE, "Christmas Day")

    def test_a_closure_day_is_reported_with_the_owner_s_reason(self) -> None:
        closed = CALENDAR.closed_day(STOCKTAKE)

        assert closed is not None
        assert (closed.kind, closed.reason) == (OWNER_CLOSURE, "stocktake")

    def test_a_closure_on_a_holiday_gives_the_owner_s_reason(self) -> None:
        calendar = BranchCalendar.standard({CHRISTMAS: "annual leave"})

        closed = calendar.closed_day(CHRISTMAS)

        assert closed is not None
        assert closed.reason == "annual leave"


class TestTheNextOpenDay:
    """The day a refusal points the customer to instead."""

    def test_an_open_day_is_its_own_next_open_day(self) -> None:
        assert CALENDAR.next_open_day(WEDNESDAY) == WEDNESDAY

    def test_after_a_sunday_comes_the_monday(self) -> None:
        assert CALENDAR.next_open_day(SUNDAY) == MONDAY

    def test_after_christmas_the_weekend_and_day_of_goodwill_are_skipped(self) -> None:
        assert CALENDAR.next_open_day(CHRISTMAS) == AFTER_THE_HOLIDAYS

    def test_a_branch_with_no_hours_has_no_next_open_day(self) -> None:
        assert BranchCalendar(weekly={}).next_open_day(WEDNESDAY) is None

    def test_the_closed_days_between_two_days_are_listed_in_order(self) -> None:
        closed = CALENDAR.closed_days_between(SATURDAY, STOCKTAKE)

        assert [day.day for day in closed] == [SUNDAY, STOCKTAKE]


class TestTheRefusal:
    """The sentence a customer reads when a hire starts or ends on a closed day."""

    def test_an_open_day_passes(self) -> None:
        ensure_open_on(CALENDAR, WEDNESDAY, collecting=True)

    def test_collecting_on_a_sunday_names_the_monday(self) -> None:
        with pytest.raises(ValidationFailure) as refusal:
            ensure_open_on(CALENDAR, SUNDAY, collecting=True)

        assert refusal.value.message == (
            "The branch is closed on Sundays, so you cannot collect on Sunday 18 October. "
            "The next day it is open is Monday 19 October."
        )
        assert refusal.value.rule == CLOSED_DAY_RULE
        assert refusal.value.detail == {
            "day": "2026-10-18",
            "closure": WEEKLY_CLOSURE,
            "next_open_day": "2026-10-19",
        }

    def test_returning_on_christmas_names_the_holiday(self) -> None:
        with pytest.raises(ValidationFailure) as refusal:
            ensure_open_on(CALENDAR, CHRISTMAS, collecting=False)

        assert refusal.value.message == (
            "Friday 25 December is Christmas Day and the branch is closed, so you cannot "
            "bring equipment back then. The next day it is open is Monday 28 December."
        )

    def test_a_stocktake_names_the_reason(self) -> None:
        with pytest.raises(ValidationFailure, match=r"\(stocktake\)"):
            ensure_open_on(CALENDAR, STOCKTAKE, collecting=True)

    def test_a_branch_that_never_opens_says_to_choose_another(self) -> None:
        with pytest.raises(ValidationFailure, match="Choose another branch") as refusal:
            ensure_open_on(BranchCalendar(weekly={}), WEDNESDAY, collecting=True)

        assert refusal.value.detail["next_open_day"] is None


class TestTheValues:
    """The calendar refuses values that cannot be right, and cannot be changed."""

    def test_hours_that_close_before_they_open_are_refused(self) -> None:
        with pytest.raises(ValueError, match="close after it opens"):
            OpeningHours(time(17, 0), time(7, 0))

    def test_a_weekday_outside_one_to_seven_is_refused(self) -> None:
        with pytest.raises(ValueError, match="numbered 1"):
            BranchCalendar(weekly={0: OpeningHours(time(7, 0), time(17, 0))})

    def test_the_calendar_cannot_be_changed_after_it_is_built(self) -> None:
        with pytest.raises(TypeError):
            CALENDAR.closures[WEDNESDAY] = "invented"  # type: ignore[index]

    def test_a_day_reads_as_a_customer_reads_it(self) -> None:
        assert day_in_words(SUNDAY) == "Sunday 18 October"

    def test_the_search_for_an_open_day_is_bounded(self) -> None:
        assert LONGEST_CLOSURE_DAYS >= 366
