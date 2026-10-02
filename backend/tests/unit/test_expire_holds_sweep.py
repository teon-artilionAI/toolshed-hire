"""The lazy sweep that lapses expired holds, run against ports and nothing else.

A hold lasts thirty minutes and nothing wakes up when it runs out (BR-13). The
sweep lapses the holds that are due the next time somebody asks a question
they could spoil. These tests pin what one sweep does. It takes only holds
that have run out, at most one batch of them and the oldest first, it releases
their units with the reason `EXPIRED`, and it writes one audit event for each
with no actor (BR-49). Running it again finds nothing left to do.

The reads run it too, and a read also makes sure of the one reservation it is
about to show, because the batch is bounded. That the availability search runs
it is in tests/unit/test_read_side_rules.py.

Two sweeps racing each other on real row locks are in
tests/integration/test_hold_expiry_sweep.py. The unit of work here is the in
memory double from tests/support, and the clock stands still until a test
moves it.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from app.application.booking.access import RESERVATION_EXPIRED_ACTION
from app.application.booking.expire_holds import (
    HOLD_SWEEP_BATCH_SIZE,
    SweepCommand,
    SweepResult,
)
from app.application.booking.read_reservation import ListReservationsQuery
from app.domain.enums import ReleaseReason, ReservationStatus
from app.domain.states import HOLD_DURATION
from tests.support.clock import DEFAULT_INSTANT
from tests.support.memory import COMMIT
from tests.support.memory_world import BookingDesk, build_memory_world, open_desk

ONE_SECOND: Final[timedelta] = timedelta(seconds=1)
JUST_PAST_THE_HOLD: Final[timedelta] = HOLD_DURATION + ONE_SECOND
SMALL_BATCH: Final[int] = 2


def sweep_once(desk: BookingDesk, batch_size: int = HOLD_SWEEP_BATCH_SIZE) -> SweepResult:
    """Run the sweep once and return what it did."""
    return desk.sweep.execute(SweepCommand(batch_size=batch_size))


class TestWhatOneSweepLapses:
    """Only holds that have run out, with their units released and an event each."""

    def test_a_hold_that_has_run_out_is_expired_and_its_units_released(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        held = desk.held()
        desk.clock.advance(JUST_PAST_THE_HOLD)
        result = sweep_once(desk)
        assert result.expired_references == (held.detail.reference,)
        stored = world.stored(held.detail.id)
        assert stored.status is ReservationStatus.EXPIRED
        assert stored.hold_expires_at is None
        (allocation,) = stored.lines[0].allocations
        assert allocation.release_reason is ReleaseReason.EXPIRED
        assert allocation.released_at == DEFAULT_INSTANT + JUST_PAST_THE_HOLD

    def test_a_hold_that_still_stands_is_left_alone(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        held = desk.held()
        desk.clock.advance(HOLD_DURATION)
        assert sweep_once(desk).expired_count == 0
        assert world.stored(held.detail.id).status is ReservationStatus.HELD

    def test_a_confirmed_reservation_is_never_expired(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        confirmed = desk.confirmed()
        desk.clock.advance(timedelta(days=1))
        assert sweep_once(desk).expired_count == 0
        assert world.stored(confirmed.detail.id).status is ReservationStatus.CONFIRMED

    def test_a_draft_is_never_expired(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        draft = desk.drafted()
        desk.clock.advance(timedelta(days=1))
        assert sweep_once(desk).expired_count == 0
        assert world.stored(draft.detail.id).status is ReservationStatus.DRAFT

    def test_each_lapse_writes_one_audit_event_with_no_actor(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        held = desk.held()
        desk.clock.advance(JUST_PAST_THE_HOLD)
        sweep_once(desk)
        event = world.store.committed.audit_events[-1]
        assert event.action == RESERVATION_EXPIRED_ACTION
        assert event.entity_id == held.detail.id
        assert event.actor_user_id is None
        assert event.actor_role is None
        assert event.before_state is not None
        assert event.before_state["status"] == "HELD"
        assert event.before_state["active_allocation_count"] == 1
        assert event.after_state is not None
        assert event.after_state["status"] == "EXPIRED"
        assert event.after_state["active_allocation_count"] == 0

    def test_a_second_sweep_finds_nothing_left_to_do(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        desk.held()
        desk.clock.advance(JUST_PAST_THE_HOLD)
        assert sweep_once(desk).expired_count == 1
        events_after_the_first = len(world.store.committed.audit_events)
        assert sweep_once(desk).expired_count == 0
        assert len(world.store.committed.audit_events) == events_after_the_first

    def test_a_sweep_with_nothing_due_commits_nothing(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        desk.held()
        commits_before = world.store.journal.count(COMMIT)
        sweep_once(desk)
        assert world.store.journal.count(COMMIT) == commits_before


class TestTheSweepIsBounded:
    """One call takes at most a batch, oldest expiry first."""

    def test_a_sweep_takes_no_more_than_its_batch_and_starts_with_the_oldest(self) -> None:
        world = build_memory_world(asset_count=3)
        desk = open_desk(world)
        references = []
        for _ in range(3):
            references.append(desk.held().detail.reference)
            desk.clock.advance(timedelta(minutes=1))
        desk.clock.advance(JUST_PAST_THE_HOLD)
        result = sweep_once(desk, SMALL_BATCH)
        assert result.expired_references == tuple(references[:SMALL_BATCH])

    def test_the_next_sweep_takes_what_the_first_one_left(self) -> None:
        world = build_memory_world(asset_count=3)
        desk = open_desk(world)
        references = [desk.held().detail.reference for _ in range(3)]
        desk.clock.advance(JUST_PAST_THE_HOLD)
        sweep_once(desk, SMALL_BATCH)
        result = sweep_once(desk, SMALL_BATCH)
        assert result.expired_count == 1
        assert set(result.expired_references) <= set(references)

    def test_the_batch_size_is_a_named_figure_and_not_unbounded(self) -> None:
        assert 0 < HOLD_SWEEP_BATCH_SIZE <= 100
        assert SweepCommand().batch_size == HOLD_SWEEP_BATCH_SIZE


class TestAReadRunsTheSweepFirst:
    """Nothing is shown as held when its hold has already run out."""

    def test_reading_a_reservation_whose_hold_ran_out_shows_it_expired(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        held = desk.held()
        desk.clock.advance(JUST_PAST_THE_HOLD)
        shown = desk.reads.one(desk.command_for(held))
        assert shown.detail.status is ReservationStatus.EXPIRED
        assert shown.detail.lines[0].allocated_count == 0
        assert world.stored(held.detail.id).status is ReservationStatus.EXPIRED

    def test_listing_reservations_lapses_the_holds_that_ran_out(self) -> None:
        world = build_memory_world(asset_count=2)
        desk = open_desk(world)
        desk.held()
        desk.held()
        desk.clock.advance(JUST_PAST_THE_HOLD)
        page = desk.reads.page(ListReservationsQuery(actor=world.customer))
        assert {view.detail.status for view in page.items} == {ReservationStatus.EXPIRED}

    def test_a_read_lapses_the_one_it_shows_even_when_the_batch_did_not_reach_it(self) -> None:
        """A full batch of older holds is due, and the one being read is the newest."""
        world = build_memory_world(asset_count=HOLD_SWEEP_BATCH_SIZE + 1)
        desk = open_desk(world)
        older = [desk.held() for _ in range(HOLD_SWEEP_BATCH_SIZE)]
        desk.clock.advance(ONE_SECOND)
        newest = desk.held()
        desk.clock.advance(JUST_PAST_THE_HOLD)

        shown = desk.reads.one(desk.command_for(newest))

        assert shown.detail.status is ReservationStatus.EXPIRED
        assert world.stored(newest.detail.id).status is ReservationStatus.EXPIRED
        assert {world.stored(view.detail.id).status for view in older} == {
            ReservationStatus.EXPIRED
        }
