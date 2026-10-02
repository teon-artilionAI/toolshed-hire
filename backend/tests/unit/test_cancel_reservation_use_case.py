"""The use case that cancels a reservation, run against ports and nothing else.

A reservation can be cancelled while it is a draft, on hold or confirmed.
Cancelling lets every unit go in the same transaction, with the reason
`CANCELLED` (BR-14), and nothing is deleted (BR-51). A confirmed booking
cancelled after 17:00 in Cape Town on the day before collection is a late
cancellation, which is counted on the customer's profile and costs nothing
(BR-16).

The hire in these tests starts on Monday the ninth of March 2026. The cutoff
is therefore 17:00 on Sunday the eighth in Cape Town, which is 15:00 UTC.

The unit of work is the in memory double from tests/support.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final

import pytest

from app.application.booking.access import RESERVATION_CANCELLED_ACTION
from app.application.refusal import refused_parameter_of
from app.domain.enums import ReleaseReason, ReservationStatus
from app.domain.errors import (
    AllocationConflictError,
    BranchScopeError,
    NotFound,
    StateTransitionError,
    ValidationFailure,
)
from app.domain.states import HOLD_DURATION
from tests.support.clock import DEFAULT_INSTANT
from tests.support.memory import StoreFault
from tests.support.memory_world import build_memory_world, open_desk

THE_CUTOFF: Final[datetime] = datetime(2026, 3, 8, 15, 0, tzinfo=UTC)
ONE_SECOND: Final[timedelta] = timedelta(seconds=1)
REASON: Final[str] = "The job was moved to next month."
REASON_MAX_LENGTH: Final[int] = 200


class TestCancellingReleasesEveryUnit:
    """The status and the releases change together."""

    def test_a_held_reservation_is_cancelled_and_its_units_let_go(self) -> None:
        world = build_memory_world(asset_count=2)
        desk = open_desk(world)
        held = desk.held(world.draft_command(quantity=2))
        cancelled = desk.cancel.execute(desk.cancellation_of(held))
        assert cancelled.detail.status is ReservationStatus.CANCELLED
        assert cancelled.detail.hold_expires_at is None
        assert cancelled.detail.lines[0].allocated_count == 0
        (line,) = world.stored(held.detail.id).lines
        assert {allocation.release_reason for allocation in line.allocations} == {
            ReleaseReason.CANCELLED
        }
        assert {allocation.released_at for allocation in line.allocations} == {DEFAULT_INSTANT}

    def test_a_confirmed_reservation_is_cancelled_and_its_units_let_go(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        confirmed = desk.confirmed()
        cancelled = desk.cancel.execute(desk.cancellation_of(confirmed))
        assert cancelled.detail.status is ReservationStatus.CANCELLED
        assert not world.stored(confirmed.detail.id).has_active_allocations()

    def test_the_released_unit_can_be_held_by_somebody_else_at_once(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        held = desk.held()
        with pytest.raises(AllocationConflictError):
            desk.held()
        desk.cancel.execute(desk.cancellation_of(held))
        assert desk.held().detail.status is ReservationStatus.HELD

    def test_a_draft_is_cancelled_with_nothing_to_release(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        draft = desk.drafted()
        cancelled = desk.cancel.execute(desk.cancellation_of(draft))
        assert cancelled.detail.status is ReservationStatus.CANCELLED
        assert world.store.committed.allocations == []

    def test_the_cancellation_records_when_and_why(self) -> None:
        desk = open_desk(build_memory_world())
        held = desk.held()
        desk.clock.advance(timedelta(minutes=5))
        cancelled = desk.cancel.execute(desk.cancellation_of(held, reason=f"  {REASON}  "))
        assert cancelled.detail.cancelled_at == DEFAULT_INSTANT + timedelta(minutes=5)
        assert cancelled.detail.cancellation_reason == REASON

    def test_a_blank_reason_is_recorded_as_no_reason(self) -> None:
        desk = open_desk(build_memory_world())
        cancelled = desk.cancel.execute(desk.cancellation_of(desk.held(), reason="   "))
        assert cancelled.detail.cancellation_reason is None

    def test_a_cancelled_reservation_is_still_there_to_be_read(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        held = desk.held()
        desk.cancel.execute(desk.cancellation_of(held))
        again = desk.reads.one(desk.command_for(held))
        assert again.detail.status is ReservationStatus.CANCELLED
        assert len(world.store.committed.reservations) == 1

    def test_the_cancellation_writes_one_audit_event(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        held = desk.held()
        desk.cancel.execute(desk.cancellation_of(held, reason=REASON))
        event = world.store.committed.audit_events[-1]
        assert event.action == RESERVATION_CANCELLED_ACTION
        assert event.before_state is not None
        assert event.before_state["status"] == "HELD"
        assert event.before_state["active_allocation_count"] == 1
        assert event.after_state is not None
        assert event.after_state["status"] == "CANCELLED"
        assert event.after_state["active_allocation_count"] == 0
        assert event.after_state["cancellation_reason"] == REASON
        assert event.after_state["late_cancellation"] is False

    def test_a_cancellation_whose_audit_event_cannot_be_written_releases_nothing(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        held = desk.held()
        world.store.fail_audit = True
        with pytest.raises(StoreFault):
            desk.cancel.execute(desk.cancellation_of(held))
        stored = world.stored(held.detail.id)
        assert stored.status is ReservationStatus.HELD
        assert stored.is_fully_allocated()


class TestALateCancellation:
    """After 17:00 on the day before collection, by the clock in Cape Town (BR-16)."""

    def test_a_confirmed_booking_cancelled_at_five_exactly_is_not_late(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        confirmed = desk.confirmed()
        desk.clock.instant = THE_CUTOFF
        desk.cancel.execute(desk.cancellation_of(confirmed))
        assert world.store.committed.late_cancellations == {}

    def test_a_confirmed_booking_cancelled_a_second_after_five_is_late(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        confirmed = desk.confirmed()
        desk.clock.instant = THE_CUTOFF + ONE_SECOND
        cancelled = desk.cancel.execute(desk.cancellation_of(confirmed))
        assert cancelled.detail.status is ReservationStatus.CANCELLED
        assert world.store.committed.late_cancellations == {world.profile.id: 1}
        event = world.store.committed.audit_events[-1]
        assert event.after_state is not None
        assert event.after_state["late_cancellation"] is True

    def test_a_late_cancellation_is_still_a_cancellation_that_releases_the_units(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        confirmed = desk.confirmed()
        desk.clock.instant = THE_CUTOFF + ONE_SECOND
        desk.cancel.execute(desk.cancellation_of(confirmed))
        assert not world.stored(confirmed.detail.id).has_active_allocations()

    def test_a_hold_cancelled_after_the_cutoff_is_not_counted(self) -> None:
        """Only a confirmed booking can be cancelled late. A hold never got that far."""
        world = build_memory_world()
        desk = open_desk(world)
        desk.clock.instant = THE_CUTOFF + ONE_SECOND
        held = desk.held()
        desk.cancel.execute(desk.cancellation_of(held))
        assert world.store.committed.late_cancellations == {}

    def test_a_cancellation_by_staff_after_the_cutoff_counts_against_the_customer(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        confirmed = desk.confirmed()
        desk.clock.instant = THE_CUTOFF + ONE_SECOND
        desk.cancel.execute(desk.cancellation_of(confirmed, actor=world.assistant()))
        assert world.store.committed.late_cancellations == {world.profile.id: 1}


class TestWhatACancellationIsRefusedFor:
    """The state, the caller and the length of the reason."""

    def test_a_cancelled_reservation_cannot_be_cancelled_again(self) -> None:
        desk = open_desk(build_memory_world())
        held = desk.held()
        desk.cancel.execute(desk.cancellation_of(held))
        with pytest.raises(StateTransitionError) as refusal:
            desk.cancel.execute(desk.cancellation_of(held))
        assert refusal.value.detail == {"from_status": "CANCELLED", "to_status": "CANCELLED"}
        assert refusal.value.message == (
            "This reservation has been cancelled, so it cannot be cancelled."
        )

    def test_a_hold_that_has_run_out_is_expired_and_cannot_be_cancelled(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        held = desk.held()
        desk.clock.advance(HOLD_DURATION + ONE_SECOND)
        with pytest.raises(StateTransitionError) as refusal:
            desk.cancel.execute(desk.cancellation_of(held))
        assert refusal.value.detail == {"from_status": "EXPIRED", "to_status": "CANCELLED"}
        assert world.stored(held.detail.id).status is ReservationStatus.EXPIRED

    def test_somebody_elses_reservation_is_not_found(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        held = desk.held()
        stranger = build_memory_world().customer
        with pytest.raises(NotFound):
            desk.cancel.execute(desk.cancellation_of(held, actor=stranger))
        assert world.stored(held.detail.id).status is ReservationStatus.HELD

    def test_a_counter_assistant_of_another_branch_is_refused(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        held = desk.held()
        with pytest.raises(BranchScopeError):
            desk.cancel.execute(
                desk.cancellation_of(held, actor=world.assistant(at_own_branch=False))
            )
        assert world.stored(held.detail.id).status is ReservationStatus.HELD

    def test_a_reason_longer_than_the_column_names_the_reason(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        held = desk.held()
        with pytest.raises(ValidationFailure) as refusal:
            desk.cancel.execute(
                desk.cancellation_of(held, reason="x" * (REASON_MAX_LENGTH + 1))
            )
        assert refused_parameter_of(refusal.value) == "reason"
        assert refusal.value.message == "Enter at most 200 characters."
        assert world.stored(held.detail.id).status is ReservationStatus.HELD

    def test_a_reason_of_exactly_the_column_width_is_accepted(self) -> None:
        desk = open_desk(build_memory_world())
        cancelled = desk.cancel.execute(
            desk.cancellation_of(desk.held(), reason="x" * REASON_MAX_LENGTH)
        )
        assert cancelled.detail.cancellation_reason == "x" * REASON_MAX_LENGTH
