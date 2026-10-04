"""The day counting of the utilisation report, over half open spans and with no database.

A span is `[begins, ends)`, so two spans that meet on a day share none of it,
and a day two spans both hold is counted once.
"""

from __future__ import annotations

from datetime import date
from typing import Final

import pytest

from app.domain.report_days import (
    DaySpan,
    clipped,
    days_in,
    merged,
    overlap,
    span_or_none,
    without,
)

SEPTEMBER: Final[DaySpan] = DaySpan(date(2026, 9, 1), date(2026, 10, 1))


def days(first: int, after_last: int) -> DaySpan:
    """Return a span of September 2026 from one day of the month up to another."""
    return DaySpan(date(2026, 9, first), date(2026, 9, after_last))


class TestOneSpan:
    """A span holds the days from its first up to but not including its end."""

    def test_a_span_holds_the_days_between_its_ends(self) -> None:
        assert days(2, 9).length == 7

    def test_a_span_that_ends_where_it_begins_holds_nothing(self) -> None:
        assert days(9, 9).length == 0

    def test_a_span_that_ends_before_it_begins_is_refused(self) -> None:
        with pytest.raises(ValueError, match="ends before it begins"):
            days(9, 2)

    def test_a_span_is_cut_to_a_window(self) -> None:
        assert DaySpan(date(2026, 8, 25), date(2026, 9, 4)).clipped_to(SEPTEMBER) == days(1, 4)

    def test_a_span_that_only_meets_the_window_shares_no_day(self) -> None:
        assert DaySpan(date(2026, 8, 25), date(2026, 9, 1)).clipped_to(SEPTEMBER) is None

    def test_an_empty_pair_of_days_is_no_span(self) -> None:
        assert span_or_none(date(2026, 9, 5), date(2026, 9, 5)) is None
        assert span_or_none(date(2026, 9, 5), date(2026, 9, 6)) == days(5, 6)


class TestTheUnion:
    """Overlapping and touching spans are joined, so each day is held once."""

    def test_overlapping_spans_are_joined(self) -> None:
        assert merged([days(5, 12), days(9, 14)]) == (days(5, 14),)

    def test_spans_that_meet_end_to_start_are_joined(self) -> None:
        assert merged([days(9, 14), days(5, 9)]) == (days(5, 14),)

    def test_spans_apart_stay_apart_in_order(self) -> None:
        assert merged([days(20, 22), days(5, 9)]) == (days(5, 9), days(20, 22))

    def test_a_span_inside_another_adds_nothing(self) -> None:
        assert merged([days(5, 20), days(9, 10)]) == (days(5, 20),)

    def test_nothing_and_empty_spans_are_left_out(self) -> None:
        assert merged([None, days(9, 9)]) == ()

    def test_a_day_two_reasons_name_is_counted_once(self) -> None:
        quarantined_at_return = days(9, 14)
        named_by_a_report = days(10, 14)
        assert days_in([quarantined_at_return, named_by_a_report]) == 5

    def test_the_union_is_cut_to_a_window_and_nothing_without_one(self) -> None:
        spans = [DaySpan(date(2026, 8, 28), date(2026, 9, 3)), days(29, 30)]
        assert clipped(spans, SEPTEMBER) == (days(1, 3), days(29, 30))
        assert clipped(spans, None) == ()


class TestOverlapAndDifference:
    """The days in both, and the days in one and not the other."""

    def test_the_overlap_holds_the_days_both_hold(self) -> None:
        assert overlap([days(1, 10), days(20, 25)], [days(5, 22)]) == (days(5, 10), days(20, 22))

    def test_spans_that_only_meet_have_no_overlap(self) -> None:
        assert overlap([days(1, 5)], [days(5, 9)]) == ()

    def test_a_cut_in_the_middle_leaves_both_sides(self) -> None:
        assert without([SEPTEMBER], [days(5, 12)]) == (
            days(1, 5),
            DaySpan(date(2026, 9, 12), date(2026, 10, 1)),
        )

    def test_a_cut_at_an_edge_leaves_one_side(self) -> None:
        assert without([days(1, 11)], [days(5, 11)]) == (days(1, 5),)

    def test_a_cut_that_misses_leaves_the_span_whole(self) -> None:
        assert without([days(1, 5)], [days(5, 9)]) == (days(1, 5),)

    def test_two_cuts_leave_three_pieces(self) -> None:
        assert without([days(1, 21)], [days(3, 5), days(10, 12)]) == (
            days(1, 3),
            days(5, 10),
            days(12, 21),
        )

    def test_a_cut_over_everything_leaves_nothing(self) -> None:
        assert without([days(5, 9)], [days(1, 21)]) == ()
