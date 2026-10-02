"""Putting a draft on hold, which is the move from DRAFT to HELD (BR-12).

This is the move that takes units off the market, so it has the most guards.
The dates are checked first, and no unit is asked for until they pass. The
allocator is then asked for the units of every line, and they are attached to
the lines only when every line was given exactly its quantity, at the
collection branch and for the hire period. A hold that is refused at any point
therefore leaves the draft holding nothing at all, which is what lets the
customer try again or abandon the basket.

The other eight legal moves are in test_reservation_states.py.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Final
from uuid import UUID, uuid4

import pytest

from app.domain.booking import Reservation
from app.domain.enums import ReservationStatus
from app.domain.errors import AllocationConflictError, ValidationFailure
from app.domain.period import BookingPeriod
from app.domain.states import HOLD_DURATION
from tests.support.reservations import (
    CATALOGUE,
    HAMMER,
    HIRE,
    MIXER,
    NINTH,
    NO_UNIT_FREE_MESSAGE,
    NOW,
    ONE_DAY,
    ONE_LINE,
    REFERENCE,
    TODAY,
    TWELFTH,
    TWO_LINES,
    FakeAllocator,
    a_draft,
    refused_and_untouched,
)

THIRTY_MINUTES: Final[timedelta] = timedelta(minutes=30)
HORIZON_DAYS: Final[int] = 90
HIRE_DAYS: Final[int] = 3
ANOTHER_PERIOD: Final[BookingPeriod] = BookingPeriod(NINTH + ONE_DAY, TWELFTH)
ANOTHER_BRANCH: Final[UUID] = uuid4()


def assert_holds_nothing(reservation: Reservation) -> None:
    """Assert that the reservation is still a draft, with no hold and no unit on any line."""
    assert reservation.status is ReservationStatus.DRAFT
    assert reservation.hold_expires_at is None
    assert not reservation.has_active_allocations()
    assert [line.allocations for line in reservation.lines] == [[] for _ in reservation.lines]


class TestADraftThatGoesOnHold:
    """Every line takes its units and the thirty minutes start."""

    def test_every_line_takes_its_units_and_the_hold_runs_for_thirty_minutes(self) -> None:
        reservation, allocator = a_draft(*TWO_LINES), FakeAllocator()
        reservation.hold(now=NOW, today=TODAY, models=CATALOGUE, allocator=allocator)
        assert reservation.status is ReservationStatus.HELD
        assert reservation.hold_expires_at == NOW + THIRTY_MINUTES
        assert allocator.asked_for == [line.id for line in reservation.lines]
        assert [len(line.active_allocations()) for line in reservation.lines] == [2, 1]
        assert reservation.is_fully_allocated()
        assert THIRTY_MINUTES == HOLD_DURATION

    @pytest.mark.parametrize(
        "days_ahead", [0, HORIZON_DAYS], ids=["starts today", "starts on the last day allowed"]
    )
    def test_a_hire_that_starts_inside_the_booking_window_is_held(self, days_ahead: int) -> None:
        reservation = a_draft(*ONE_LINE)
        today = NINTH - timedelta(days=days_ahead)
        reservation.hold(now=NOW, today=today, models=CATALOGUE, allocator=FakeAllocator())
        assert reservation.status is ReservationStatus.HELD

    def test_a_hire_of_exactly_the_shortest_and_the_longest_a_model_allows_is_held(self) -> None:
        reservation = a_draft(*ONE_LINE)
        models = {HAMMER.id: replace(HAMMER, min_hire_days=HIRE_DAYS, max_hire_days=HIRE_DAYS)}
        reservation.hold(now=NOW, today=TODAY, models=models, allocator=FakeAllocator())
        assert reservation.status is ReservationStatus.HELD


class TestAHoldRefusedByItsDates:
    """A date guard that fails stops the hold before a single unit is asked for."""

    @pytest.mark.parametrize(
        ("days_ahead", "rule"),
        [(-1, "BR-04"), (HORIZON_DAYS + 1, "BR-05")],
        ids=["started yesterday", "starts a day past the horizon"],
    )
    def test_a_hire_that_starts_outside_the_booking_window_takes_no_unit(
        self, days_ahead: int, rule: str
    ) -> None:
        reservation, allocator = a_draft(*ONE_LINE), FakeAllocator()
        today = NINTH - timedelta(days=days_ahead)
        with refused_and_untouched(reservation, ValidationFailure) as refused:
            reservation.hold(now=NOW, today=today, models=CATALOGUE, allocator=allocator)
        assert refused.value.rule == rule
        assert allocator.asked_for == []

    @pytest.mark.parametrize(
        ("shortest", "longest", "sentence"),
        [
            (4, 28, "GBH 2-26 DRE Rotary Hammer has to be hired for at least 4 days."),
            (1, 2, "GBH 2-26 DRE Rotary Hammer can be hired for at most 2 days."),
        ],
        ids=["a day too short", "a day too long"],
    )
    def test_a_hire_outside_the_limits_of_a_model_takes_no_unit(
        self, shortest: int, longest: int, sentence: str
    ) -> None:
        reservation, allocator = a_draft(*ONE_LINE), FakeAllocator()
        models = {HAMMER.id: replace(HAMMER, min_hire_days=shortest, max_hire_days=longest)}
        with refused_and_untouched(reservation, ValidationFailure) as refused:
            reservation.hold(now=NOW, today=TODAY, models=models, allocator=allocator)
        assert (refused.value.message, refused.value.rule) == (sentence, "BR-03")
        assert allocator.asked_for == []

    def test_the_limits_of_the_last_model_are_checked_before_the_first_unit_is_taken(self) -> None:
        reservation, allocator = a_draft(*TWO_LINES), FakeAllocator()
        models = {**CATALOGUE, MIXER.id: replace(MIXER, min_hire_days=HIRE_DAYS + 1)}
        with refused_and_untouched(reservation, ValidationFailure):
            reservation.hold(now=NOW, today=TODAY, models=models, allocator=allocator)
        assert allocator.asked_for == []

    def test_a_reservation_with_no_lines_cannot_be_held(self) -> None:
        reservation, allocator = a_draft(), FakeAllocator()
        with refused_and_untouched(reservation, ValidationFailure) as refused:
            reservation.hold(now=NOW, today=TODAY, models=CATALOGUE, allocator=allocator)
        assert refused.value.message == "Add at least one tool before you reserve."
        assert refused.value.detail == {"reference": REFERENCE}


class TestAHoldRefusedByItsUnits:
    """A hold that cannot have every unit keeps none of them."""

    @pytest.mark.parametrize(
        "allocator",
        [
            FakeAllocator(surplus=-1),
            FakeAllocator(surplus=1),
            FakeAllocator(branch_id=ANOTHER_BRANCH),
            FakeAllocator(period=ANOTHER_PERIOD),
        ],
        ids=["a unit short", "a unit too many", "units at another branch", "another period"],
    )
    def test_a_hold_that_was_not_given_exactly_its_units_is_a_conflict_and_keeps_none(
        self, allocator: FakeAllocator
    ) -> None:
        reservation = a_draft(*TWO_LINES)
        with refused_and_untouched(reservation, AllocationConflictError) as refused:
            reservation.hold(now=NOW, today=TODAY, models=CATALOGUE, allocator=allocator)
        assert refused.value.detail == {
            "branch_id": str(reservation.branch_id),
            "period": HIRE.as_postgres_daterange(),
        }
        assert allocator.asked_for == [line.id for line in reservation.lines]
        assert_holds_nothing(reservation)

    @pytest.mark.parametrize(
        "lines_served", [0, 1], ids=["no unit for line one", "units for line one and none for two"]
    )
    def test_a_conflict_the_allocator_raises_stops_the_hold_and_keeps_no_unit(
        self, lines_served: int
    ) -> None:
        reservation, allocator = a_draft(*TWO_LINES), FakeAllocator(serves=lines_served)
        with refused_and_untouched(reservation, AllocationConflictError) as refused:
            reservation.hold(now=NOW, today=TODAY, models=CATALOGUE, allocator=allocator)
        assert refused.value.message == NO_UNIT_FREE_MESSAGE
        assert allocator.asked_for == [line.id for line in reservation.lines][: lines_served + 1]
        assert_holds_nothing(reservation)

    def test_a_refused_hold_can_still_be_abandoned_as_a_draft(self) -> None:
        reservation = a_draft(*TWO_LINES)
        with pytest.raises(AllocationConflictError):
            reservation.hold(
                now=NOW, today=TODAY, models=CATALOGUE, allocator=FakeAllocator(surplus=-1)
            )
        reservation.cancel(now=NOW, reason=None, by_owner_or_staff=True)
        assert reservation.status is ReservationStatus.CANCELLED
