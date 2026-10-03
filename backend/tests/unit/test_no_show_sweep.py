"""The no show half of the lazy sweep, run against ports and nothing else (BR-17, BR-18).

A confirmed booking nobody collected becomes a no show once its branch has
closed on the first day of the hire, the next time the sweep runs. These pin
what one sweep does. It takes only the bookings that are due, a bounded batch
of them and the earliest first day first, releases their units with the reason
`NO_SHOW`, writes an audit event for each with no actor, raises the running
count on the customer and puts the customer on hold at the third no show whose
hire started inside the last twelve months. Running it again finds nothing.

The unit of work here is the in memory double from tests/support, and the
clock stands still until a test moves it. The worked example hire starts on
Monday the ninth of March 2026, and the branch closes at 17:00 in Cape Town,
which is 15:00 UTC.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta
from typing import Final
from uuid import uuid4

import pytest

from app.application.booking.access import RESERVATION_NO_SHOW_ACTION
from app.application.booking.expire_holds import (
    NO_SHOW_SWEEP_BATCH_SIZE,
    SweepCommand,
    SweepResult,
)
from app.application.booking.no_show import CUSTOMER_PUT_ON_HOLD_ACTION
from app.domain.booking import Reservation
from app.domain.enums import AccountStatus, ReleaseReason, ReservationStatus
from app.domain.errors import AccountOnHoldError
from app.domain.period import BookingPeriod
from tests.support.memory import COMMIT
from tests.support.memory_world import BookingDesk, MemoryWorld, build_memory_world, open_desk

ONE_SECOND: Final[timedelta] = timedelta(seconds=1)
ONE_DAY: Final[timedelta] = timedelta(days=1)
# 17:00 in Cape Town on the first day of the worked example hire.
BRANCH_CLOSED_AT: Final[datetime] = datetime(2026, 3, 9, 15, 0, tzinfo=UTC)
LATER_HIRE: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 10), date(2026, 3, 12))
INSIDE_THE_WINDOW: Final[tuple[date, ...]] = (date(2025, 12, 1), date(2026, 2, 2))
OUTSIDE_THE_WINDOW: Final[date] = date(2025, 3, 1)
SMALL_BATCH: Final[int] = 1

_numbers: Final[Iterator[int]] = itertools.count(1)


def sweep_once(
    desk: BookingDesk, no_show_batch_size: int = NO_SHOW_SWEEP_BATCH_SIZE
) -> SweepResult:
    """Run the sweep once and return what it did."""
    return desk.sweep.execute(SweepCommand(no_show_batch_size=no_show_batch_size))


def past_no_show(world: MemoryWorld, first_day: date) -> Reservation:
    """Commit a reservation of the world's customer that was not collected, starting on a day."""
    reservation = Reservation(
        reference=f"TSH-R-25-{next(_numbers):06d}",
        customer_profile_id=world.profile.id,
        branch_id=world.branch.id,
        period=BookingPeriod(first_day, first_day + ONE_DAY),
        status=ReservationStatus.NO_SHOW,
        created_by_user_id=world.customer_account_id,
    )
    world.store.committed.reservations.append(reservation)
    return reservation


class TestWhatOneSweepMarks:
    """Only confirmed bookings whose branch has closed on the first day."""

    def test_after_closing_on_the_first_day_the_booking_is_marked_and_its_units_released(
        self,
    ) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        confirmed = desk.confirmed()
        desk.clock.instant = BRANCH_CLOSED_AT + ONE_SECOND

        result = sweep_once(desk)

        assert result.no_show_references == (confirmed.detail.reference,)
        assert result.no_show_count == 1
        stored = world.stored(confirmed.detail.id)
        assert stored.status is ReservationStatus.NO_SHOW
        (allocation,) = stored.lines[0].allocations
        assert allocation.release_reason is ReleaseReason.NO_SHOW
        assert allocation.released_at == BRANCH_CLOSED_AT + ONE_SECOND

    @pytest.mark.parametrize(
        "instant",
        [BRANCH_CLOSED_AT - ONE_SECOND, BRANCH_CLOSED_AT],
        ids=["before closing time", "at closing time"],
    )
    def test_until_the_branch_has_closed_the_booking_is_left_alone(
        self, instant: datetime
    ) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        confirmed = desk.confirmed()
        desk.clock.instant = instant
        assert sweep_once(desk).no_show_count == 0
        assert world.stored(confirmed.detail.id).status is ReservationStatus.CONFIRMED

    def test_the_day_after_the_booking_is_marked(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        confirmed = desk.confirmed()
        desk.clock.instant = BRANCH_CLOSED_AT + ONE_DAY - timedelta(hours=10)
        assert sweep_once(desk).no_show_references == (confirmed.detail.reference,)

    def test_a_branch_that_closes_earlier_makes_its_bookings_due_earlier(self) -> None:
        world = build_memory_world()
        world.store.closing_times[world.branch.id] = time(12, 0)
        desk = open_desk(world)
        confirmed = desk.confirmed()
        desk.clock.instant = datetime(2026, 3, 9, 10, 0, 1, tzinfo=UTC)
        assert sweep_once(desk).no_show_references == (confirmed.detail.reference,)

    def test_a_held_booking_and_a_draft_are_never_marked(self) -> None:
        world = build_memory_world(asset_count=2)
        desk = open_desk(world)
        draft = desk.drafted()
        desk.held()
        desk.clock.instant = BRANCH_CLOSED_AT + ONE_DAY
        assert sweep_once(desk).no_show_count == 0
        assert world.stored(draft.detail.id).status is ReservationStatus.DRAFT

    def test_each_no_show_writes_one_audit_event_with_no_actor(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        confirmed = desk.confirmed()
        desk.clock.instant = BRANCH_CLOSED_AT + ONE_SECOND
        sweep_once(desk)
        (event,) = [
            event
            for event in world.store.committed.audit_events
            if event.action == RESERVATION_NO_SHOW_ACTION
        ]
        assert event.entity_id == confirmed.detail.id
        assert (event.actor_user_id, event.actor_role) == (None, None)
        assert event.before_state is not None
        assert event.before_state["status"] == "CONFIRMED"
        assert event.after_state is not None
        assert event.after_state["status"] == "NO_SHOW"
        assert event.after_state["active_allocation_count"] == 0
        assert event.after_state["no_show_reason"] is None

    def test_the_running_count_on_the_customer_goes_up_by_one(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        desk.confirmed()
        desk.clock.instant = BRANCH_CLOSED_AT + ONE_SECOND
        sweep_once(desk)
        assert world.store.committed.no_shows == {world.profile.id: 1}

    def test_a_second_sweep_finds_nothing_left_to_do(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        desk.confirmed()
        desk.clock.instant = BRANCH_CLOSED_AT + ONE_SECOND
        assert sweep_once(desk).no_show_count == 1
        events_after_the_first = len(world.store.committed.audit_events)
        assert sweep_once(desk).no_show_count == 0
        assert len(world.store.committed.audit_events) == events_after_the_first

    def test_a_sweep_with_nothing_due_commits_nothing(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        desk.confirmed()
        commits_before = world.store.journal.count(COMMIT)
        sweep_once(desk)
        assert world.store.journal.count(COMMIT) == commits_before


class TestTheNoShowHalfIsBounded:
    """One call marks at most a batch, earliest first day first."""

    def test_a_sweep_takes_no_more_than_its_batch_and_starts_with_the_earliest(self) -> None:
        world = build_memory_world(asset_count=2)
        desk = open_desk(world)
        later = desk.confirmed(world.draft_command(LATER_HIRE))
        earlier = desk.confirmed()
        desk.clock.instant = BRANCH_CLOSED_AT + 2 * ONE_DAY

        first = sweep_once(desk, SMALL_BATCH)
        second = sweep_once(desk, SMALL_BATCH)

        assert first.no_show_references == (earlier.detail.reference,)
        assert second.no_show_references == (later.detail.reference,)

    def test_the_batch_is_a_named_figure_and_not_unbounded(self) -> None:
        assert 0 < NO_SHOW_SWEEP_BATCH_SIZE <= 100
        assert SweepCommand().no_show_batch_size == NO_SHOW_SWEEP_BATCH_SIZE


class TestThreeStrikes:
    """The third no show inside twelve months puts an account in good standing on hold."""

    def test_the_third_no_show_inside_the_window_puts_the_customer_on_hold(self) -> None:
        world = build_memory_world()
        for first_day in INSIDE_THE_WINDOW:
            past_no_show(world, first_day)
        desk = open_desk(world)
        desk.confirmed()
        desk.clock.instant = BRANCH_CLOSED_AT + ONE_SECOND

        result = sweep_once(desk)

        assert result.customers_put_on_hold == (world.profile.id,)
        assert world.store.committed.account_statuses == {world.profile.id: AccountStatus.ON_HOLD}
        (event,) = [
            event
            for event in world.store.committed.audit_events
            if event.action == CUSTOMER_PUT_ON_HOLD_ACTION
        ]
        assert (event.entity_type, event.entity_id) == ("customer_profile", world.profile.id)
        assert event.actor_user_id is None
        assert event.before_state == {"account_status": "ACTIVE"}
        assert event.after_state is not None
        assert event.after_state["account_status"] == "ON_HOLD"
        assert event.after_state["no_shows_in_twelve_months"] == 3

    def test_two_inside_the_window_and_one_outside_leave_the_customer_in_good_standing(
        self,
    ) -> None:
        world = build_memory_world()
        past_no_show(world, INSIDE_THE_WINDOW[0])
        past_no_show(world, OUTSIDE_THE_WINDOW)
        desk = open_desk(world)
        desk.confirmed()
        desk.clock.instant = BRANCH_CLOSED_AT + ONE_SECOND

        result = sweep_once(desk)

        assert result.no_show_count == 1
        assert result.customers_put_on_hold == ()
        assert world.store.committed.account_statuses == {}
        assert world.store.committed.no_shows == {world.profile.id: 1}

    def test_a_customer_put_on_hold_cannot_book_again(self) -> None:
        world = build_memory_world(asset_count=2)
        for first_day in INSIDE_THE_WINDOW:
            past_no_show(world, first_day)
        desk = open_desk(world)
        desk.confirmed()
        desk.clock.instant = BRANCH_CLOSED_AT + ONE_SECOND
        sweep_once(desk)

        with pytest.raises(AccountOnHoldError) as refused:
            desk.drafted()
        assert "three bookings in the last twelve months" in refused.value.message


class TestTheRecheckUnderTheLock:
    """A booking that changed between being found and being locked is left alone."""

    def test_a_booking_collected_in_the_meantime_is_skipped(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        confirmed = desk.confirmed()
        desk.clock.instant = BRANCH_CLOSED_AT + ONE_SECOND
        collected = world.stored(confirmed.detail.id)
        collected.status = ReservationStatus.COLLECTED
        world.store.stale_no_show_query = True

        assert sweep_once(desk).no_show_count == 0
        assert world.stored(confirmed.detail.id).status is ReservationStatus.COLLECTED

    def test_a_booking_whose_customer_cannot_be_read_is_a_fault_in_the_data(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        confirmed = desk.confirmed()
        world.stored(confirmed.detail.id).customer_profile_id = uuid4()
        desk.clock.instant = BRANCH_CLOSED_AT + ONE_SECOND

        with pytest.raises(LookupError, match="could not be read"):
            sweep_once(desk)
        assert world.stored(confirmed.detail.id).status is ReservationStatus.CONFIRMED
