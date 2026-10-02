"""The BookingPeriod value object, and the half open rule the system rests on.

Every availability answer in Toolshed Hire is an overlap question, and every
overlap question is decided by one comparison. If that comparison is inclusive
at the upper bound then a unit returned on the twelfth cannot be hired out on
the twelfth, the fleet quietly loses a day of utilisation on every hire, and
nothing fails visibly. That is exactly the kind of off by one that reaches
production, so the boundary case is written out here in the vocabulary of the
business rather than left implicit in a range of dates.

The same rule is enforced a second time in the database, by
`daterange(start_date, end_date, '[)')` inside the exclusion constraint. The two
definitions must agree, and tests/integration/test_exclusion_constraint.py
asserts the database half of the same statement.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date, timedelta

import pytest

from app.domain.errors import ValidationFailure
from app.domain.period import (
    BOOKING_HORIZON_RULE,
    DATERANGE_BOUNDS,
    DAYS_IN_A_WEEK,
    MAXIMUM_DAYS_AHEAD,
    MAXIMUM_HIRE_DAYS,
    NO_PAST_START_RULE,
    PERIOD_BOUNDS_RULE,
    RETURN_NOT_AFTER_START_MESSAGE,
    BookingPeriod,
    InvalidBookingPeriod,
    ensure_within_booking_window,
)

# The worked example month. The ninth to the twelfth is a three day hire that
# ends on the twelfth, which is the day the unit comes back and is not charged.
NINTH = date(2026, 3, 9)
TWELFTH = date(2026, 3, 12)
FIFTEENTH = date(2026, 3, 15)

HIRE_ENDING_ON_THE_TWELFTH = BookingPeriod(NINTH, TWELFTH)
HIRE_STARTING_ON_THE_TWELFTH = BookingPeriod(TWELFTH, FIFTEENTH)


class TestHalfOpenBoundary:
    """The rule that a return on the twelfth frees the twelfth."""

    def test_a_hire_ending_on_the_twelfth_does_not_overlap_one_starting_on_the_twelfth(
        self,
    ) -> None:
        assert not HIRE_ENDING_ON_THE_TWELFTH.overlaps(HIRE_STARTING_ON_THE_TWELFTH)

    def test_the_boundary_answer_is_the_same_asked_from_either_side(self) -> None:
        assert not HIRE_STARTING_ON_THE_TWELFTH.overlaps(HIRE_ENDING_ON_THE_TWELFTH)

    def test_the_last_day_actually_held_is_the_day_before_the_end_bound(self) -> None:
        assert HIRE_ENDING_ON_THE_TWELFTH.last_day == date(2026, 3, 11)

    def test_the_end_day_is_not_inside_the_period(self) -> None:
        assert not HIRE_ENDING_ON_THE_TWELFTH.contains(TWELFTH)

    def test_the_start_day_is_inside_the_period(self) -> None:
        assert HIRE_ENDING_ON_THE_TWELFTH.contains(NINTH)

    def test_a_day_in_the_middle_is_inside_the_period(self) -> None:
        assert HIRE_ENDING_ON_THE_TWELFTH.contains(date(2026, 3, 11))

    def test_a_day_before_the_start_is_outside_the_period(self) -> None:
        assert not HIRE_ENDING_ON_THE_TWELFTH.contains(date(2026, 3, 8))

    def test_extending_the_first_hire_by_one_day_makes_the_two_overlap(self) -> None:
        extended = BookingPeriod(NINTH, date(2026, 3, 13))
        assert extended.overlaps(HIRE_STARTING_ON_THE_TWELFTH)

    def test_the_chargeable_day_count_excludes_the_return_day(self) -> None:
        assert HIRE_ENDING_ON_THE_TWELFTH.days == 3


class TestOverlapRelations:
    """Identical, contained, containing, partial and disjoint periods."""

    def test_two_identical_periods_overlap(self) -> None:
        assert HIRE_ENDING_ON_THE_TWELFTH.overlaps(BookingPeriod(NINTH, TWELFTH))

    def test_a_period_wholly_inside_another_overlaps_it(self) -> None:
        contained = BookingPeriod(date(2026, 3, 10), date(2026, 3, 11))
        assert HIRE_ENDING_ON_THE_TWELFTH.overlaps(contained)

    def test_a_period_wholly_containing_another_overlaps_it(self) -> None:
        contained = BookingPeriod(date(2026, 3, 10), date(2026, 3, 11))
        assert contained.overlaps(HIRE_ENDING_ON_THE_TWELFTH)

    def test_a_period_starting_inside_another_and_ending_after_it_overlaps(self) -> None:
        later = BookingPeriod(date(2026, 3, 11), FIFTEENTH)
        assert HIRE_ENDING_ON_THE_TWELFTH.overlaps(later)

    def test_a_period_sharing_only_its_first_day_overlaps(self) -> None:
        later = BookingPeriod(date(2026, 3, 11), date(2026, 3, 12))
        assert HIRE_ENDING_ON_THE_TWELFTH.overlaps(later)

    def test_two_periods_separated_by_a_free_day_do_not_overlap(self) -> None:
        assert not HIRE_ENDING_ON_THE_TWELFTH.overlaps(BookingPeriod(date(2026, 3, 13), FIFTEENTH))

    def test_a_period_wholly_before_another_does_not_overlap_it(self) -> None:
        earlier = BookingPeriod(date(2026, 3, 1), date(2026, 3, 5))
        assert not earlier.overlaps(HIRE_ENDING_ON_THE_TWELFTH)

    @pytest.mark.parametrize(
        ("first", "second"),
        [
            (BookingPeriod(NINTH, TWELFTH), BookingPeriod(TWELFTH, FIFTEENTH)),
            (BookingPeriod(NINTH, TWELFTH), BookingPeriod(NINTH, TWELFTH)),
            (BookingPeriod(NINTH, FIFTEENTH), BookingPeriod(date(2026, 3, 10), TWELFTH)),
            (BookingPeriod(NINTH, TWELFTH), BookingPeriod(date(2026, 3, 20), date(2026, 3, 22))),
        ],
        ids=["adjacent", "identical", "contained", "disjoint"],
    )
    def test_overlap_gives_the_same_answer_whichever_period_is_asked(
        self, first: BookingPeriod, second: BookingPeriod
    ) -> None:
        assert first.overlaps(second) == second.overlaps(first)

    def test_comparing_against_something_that_is_not_a_period_is_refused(self) -> None:
        with pytest.raises(InvalidBookingPeriod, match="Expected a BookingPeriod"):
            HIRE_ENDING_ON_THE_TWELFTH.overlaps(NINTH)  # type: ignore[arg-type]

    def test_testing_containment_of_something_that_is_not_a_date_is_refused(self) -> None:
        with pytest.raises(InvalidBookingPeriod, match="Expected a datetime.date"):
            HIRE_ENDING_ON_THE_TWELFTH.contains("2026-03-10")  # type: ignore[arg-type]


class TestConstruction:
    """No invalid period is allowed to exist, so validation happens at construction."""

    def test_a_reversed_period_is_refused(self) -> None:
        with pytest.raises(InvalidBookingPeriod, match="has to be after the start date"):
            BookingPeriod(TWELFTH, NINTH)

    def test_a_period_that_starts_and_ends_on_the_same_day_is_refused(self) -> None:
        with pytest.raises(InvalidBookingPeriod, match="has to be after the start date"):
            BookingPeriod(TWELFTH, TWELFTH)

    def test_the_refusal_of_an_empty_period_is_a_sentence_and_the_rule_travels_beside_it(
        self,
    ) -> None:
        """The sentence is shown to a customer, so the rule and the dates stay out of it."""
        with pytest.raises(InvalidBookingPeriod) as raised:
            BookingPeriod(TWELFTH, TWELFTH)
        assert str(raised.value) == RETURN_NOT_AFTER_START_MESSAGE
        assert "2026-03-12" not in str(raised.value)
        assert raised.value.rule == PERIOD_BOUNDS_RULE

    def test_a_refusal_that_is_a_mistake_in_the_calling_code_names_no_rule(self) -> None:
        with pytest.raises(InvalidBookingPeriod) as raised:
            BookingPeriod("2026-03-09", TWELFTH)  # type: ignore[arg-type]  # the mistake under test
        assert raised.value.rule is None

    def test_a_period_built_from_something_that_is_not_a_date_is_refused(self) -> None:
        with pytest.raises(InvalidBookingPeriod, match="Both must be datetime.date"):
            BookingPeriod("2026-03-09", TWELFTH)  # type: ignore[arg-type]

    def test_a_one_day_hire_is_the_shortest_period_that_exists(self) -> None:
        assert BookingPeriod(TWELFTH, date(2026, 3, 13)).days == 1

    def test_a_hire_of_exactly_the_maximum_length_is_accepted(self) -> None:
        period = BookingPeriod(NINTH, NINTH + timedelta(days=MAXIMUM_HIRE_DAYS))
        assert period.days == MAXIMUM_HIRE_DAYS

    def test_a_hire_one_day_past_the_maximum_length_is_refused(self) -> None:
        with pytest.raises(
            InvalidBookingPeriod, match=f"can be at most {MAXIMUM_HIRE_DAYS} days"
        ) as raised:
            BookingPeriod(NINTH, NINTH + timedelta(days=MAXIMUM_HIRE_DAYS + 1))
        assert raised.value.rule == PERIOD_BOUNDS_RULE

    def test_a_period_cannot_be_mutated_after_construction(self) -> None:
        with pytest.raises(FrozenInstanceError):
            HIRE_ENDING_ON_THE_TWELFTH.start = TWELFTH  # type: ignore[misc]


class TestWeeksAndDaysLeftOver:
    """What the pricing policy charges by, complete weeks and the days after them."""

    @pytest.mark.parametrize(
        ("days", "whole_weeks", "remainder_days"),
        [(1, 0, 1), (6, 0, 6), (7, 1, 0), (8, 1, 1), (10, 1, 3), (14, 2, 0), (28, 4, 0)],
    )
    def test_a_period_splits_into_complete_weeks_and_the_days_left_over(
        self, days: int, whole_weeks: int, remainder_days: int
    ) -> None:
        period = BookingPeriod(NINTH, NINTH + timedelta(days=days))
        assert (period.whole_weeks, period.remainder_days) == (whole_weeks, remainder_days)

    def test_the_weeks_and_the_days_left_over_account_for_every_day(self) -> None:
        for days in range(1, MAXIMUM_HIRE_DAYS + 1):
            period = BookingPeriod(NINTH, NINTH + timedelta(days=days))
            assert period.whole_weeks * DAYS_IN_A_WEEK + period.remainder_days == period.days


class TestTheBookingWindow:
    """No start in the past and none beyond the horizon, said in plain words."""

    TODAY = date(2026, 3, 2)

    def test_a_hire_that_starts_today_is_inside_the_window(self) -> None:
        ensure_within_booking_window(BookingPeriod(self.TODAY, NINTH), self.TODAY)

    def test_a_hire_that_starts_on_the_last_day_of_the_horizon_is_inside_the_window(self) -> None:
        start = self.TODAY + timedelta(days=MAXIMUM_DAYS_AHEAD)
        ensure_within_booking_window(BookingPeriod(start, start + timedelta(days=1)), self.TODAY)

    def test_a_start_in_the_past_is_refused_in_a_sentence_with_the_rule_beside_it(self) -> None:
        with pytest.raises(ValidationFailure) as raised:
            ensure_within_booking_window(BookingPeriod(date(2026, 3, 1), NINTH), self.TODAY)
        assert raised.value.message == "The hire has to start today or later."
        assert raised.value.rule == NO_PAST_START_RULE
        assert raised.value.detail == {"start_date": "2026-03-01", "today": "2026-03-02"}

    def test_a_start_beyond_the_horizon_is_refused_in_a_sentence_with_the_rule_beside_it(
        self,
    ) -> None:
        start = self.TODAY + timedelta(days=MAXIMUM_DAYS_AHEAD + 1)
        with pytest.raises(ValidationFailure) as raised:
            ensure_within_booking_window(
                BookingPeriod(start, start + timedelta(days=2)), self.TODAY
            )
        assert raised.value.message == "A hire can start at most 90 days from today."
        assert raised.value.rule == BOOKING_HORIZON_RULE
        assert raised.value.detail["days_ahead"] == MAXIMUM_DAYS_AHEAD + 1


class TestPostgresRepresentation:
    """The literal the domain renders must be the literal the constraint builds."""

    def test_the_rendered_range_is_inclusive_of_the_start_and_exclusive_of_the_end(self) -> None:
        assert HIRE_ENDING_ON_THE_TWELFTH.as_postgres_daterange() == "[2026-03-09,2026-03-12)"

    def test_the_rendered_bounds_match_the_bound_specifier_the_migration_uses(self) -> None:
        rendered = HIRE_ENDING_ON_THE_TWELFTH.as_postgres_daterange()
        assert (rendered[0], rendered[-1]) == (DATERANGE_BOUNDS[0], DATERANGE_BOUNDS[1])

    def test_the_string_form_is_the_range_so_a_log_line_reads_as_the_database_does(self) -> None:
        assert str(HIRE_ENDING_ON_THE_TWELFTH) == "[2026-03-09,2026-03-12)"
