"""The force release and the reallocation, run against ports and nothing else (US-32).

An administrator releases one unit of a confirmed booking by hand, with a
reason that goes into the audit event, and the booking is then one short.
Staff at the collection branch give it a replacement through the allocator a
hold uses, all or nothing. These pin what each use case keeps, the audit event
it writes and every refusal, against the in memory unit of work from
tests/support. The world's branch holds three hammers, and the worked example
hire of the ninth to the twelfth of March books two of them.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Final
from uuid import UUID, uuid4

import pytest

from app.application.booking.access import ReservationCommand
from app.application.booking.expire_holds import ExpireHoldsAndNoShowsUseCase
from app.application.booking.force_release import (
    RESERVATION_UNIT_RELEASED_ACTION,
    ForceReleaseCommand,
    ForceReleaseUseCase,
)
from app.application.booking.read_models import ReservationKey
from app.application.booking.reallocate import (
    RESERVATION_REALLOCATED_ACTION,
    ReallocateUseCase,
)
from app.application.booking.views import ReservationView
from app.domain.enums import AssetStatus, ReleaseReason, ReservationStatus, UserRole
from app.domain.errors import (
    AllocationConflictError,
    BranchScopeError,
    NotFound,
    StateTransitionError,
    ValidationFailure,
)
from app.domain.identity import Actor
from tests.support.memory import InMemoryUnitOfWork
from tests.support.memory_world import BookingDesk, MemoryWorld, build_memory_world, open_desk

UNITS: Final[int] = 3
BOOKED: Final[int] = 2
REASON: Final[str] = "The unit is still out with another customer."
ADMINISTRATOR: Final[Actor] = Actor(user_id=uuid4(), role=UserRole.ADMIN)


def confirmed_two(world: MemoryWorld) -> tuple[BookingDesk, ReservationView]:
    """Confirm two of the world's three hammers for the worked example hire."""
    desk = open_desk(world)
    return desk, desk.confirmed(world.draft_command(quantity=BOOKED))


def allocation_ids(world: MemoryWorld, view: ReservationView) -> list[UUID]:
    """Return the keys of the active allocations of a committed reservation."""
    stored = world.stored(view.detail.id)
    return [allocation.id for allocation in stored.lines[0].active_allocations()]


def release(
    world: MemoryWorld, desk: BookingDesk, allocation_id: UUID, reason: str = REASON
) -> ReservationView:
    """Release one allocation by hand as the administrator."""
    use_case = ForceReleaseUseCase(InMemoryUnitOfWork(world.store), desk.clock)
    return use_case.execute(
        ForceReleaseCommand(actor=ADMINISTRATOR, allocation_id=allocation_id, reason=reason)
    )


def reallocate(
    world: MemoryWorld, desk: BookingDesk, view: ReservationView, actor: Actor
) -> ReservationView:
    """Ask for replacement units for a reservation as `actor`."""
    sweep = ExpireHoldsAndNoShowsUseCase(InMemoryUnitOfWork(world.store), desk.clock)
    use_case = ReallocateUseCase(InMemoryUnitOfWork(world.store), desk.clock, sweep)
    return use_case.execute(ReservationCommand(actor=actor, key=ReservationKey.of(view.detail.id)))


def events(world: MemoryWorld, action: str) -> list[dict[str, object]]:
    """Return the after states of the committed audit events of one action."""
    return [
        dict(event.after_state or {})
        for event in world.store.committed.audit_events
        if event.action == action
    ]


class TestTheForceRelease:
    """One allocation goes with REALLOCATED, and the reason goes into the audit event."""

    def test_the_booking_is_left_one_unit_short(self) -> None:
        world = build_memory_world(asset_count=UNITS)
        desk, confirmed = confirmed_two(world)
        first = allocation_ids(world, confirmed)[0]
        view = release(world, desk, first)

        (line,) = view.detail.lines
        assert (line.allocated_count, view.detail.status) == (1, ReservationStatus.CONFIRMED)
        (released,) = [a for a in world.store.committed.allocations if a.id == first]
        assert released.release_reason is ReleaseReason.REALLOCATED
        (event,) = events(world, RESERVATION_UNIT_RELEASED_ACTION)
        assert (event["reason"], event["release_reason"], event["units_short"]) == (
            REASON, "REALLOCATED", 1
        )
        assert event["asset_tag"] == world.store.tag_of(released.asset_id)

    def test_an_allocation_that_does_not_exist_is_not_found(self) -> None:
        world = build_memory_world(asset_count=UNITS)
        desk, _confirmed = confirmed_two(world)
        with pytest.raises(NotFound, match="could not find that allocation"):
            release(world, desk, uuid4())

    def test_a_reason_too_short_changes_nothing(self) -> None:
        world = build_memory_world(asset_count=UNITS)
        desk, confirmed = confirmed_two(world)
        with pytest.raises(ValidationFailure):
            release(world, desk, allocation_ids(world, confirmed)[0], reason="gone")
        assert len(allocation_ids(world, confirmed)) == BOOKED
        assert events(world, RESERVATION_UNIT_RELEASED_ACTION) == []

    def test_a_unit_released_twice_is_refused_the_second_time(self) -> None:
        world = build_memory_world(asset_count=UNITS)
        desk, confirmed = confirmed_two(world)
        first = allocation_ids(world, confirmed)[0]
        release(world, desk, first)
        with pytest.raises(StateTransitionError, match="no longer held"):
            release(world, desk, first)
        assert len(events(world, RESERVATION_UNIT_RELEASED_ACTION)) == 1


class TestTheReallocation:
    """Every short line is topped up through the allocator of a hold, all or nothing."""

    def test_staff_of_the_branch_top_the_booking_up_again(self) -> None:
        world = build_memory_world(asset_count=UNITS)
        desk, confirmed = confirmed_two(world)
        first, kept = allocation_ids(world, confirmed)
        release(world, desk, first)
        view = reallocate(world, desk, confirmed, world.assistant())

        (line,) = view.detail.lines
        assert line.allocated_count == BOOKED
        (allocated,) = [
            allocation
            for allocation in world.stored(confirmed.detail.id).lines[0].active_allocations()
            if allocation.id != kept
        ]
        assert allocated.id != first
        (event,) = events(world, RESERVATION_REALLOCATED_ACTION)
        assert event["asset_tags"] == [world.store.tag_of(allocated.asset_id)]

    def test_a_booking_short_of_nothing_writes_no_event(self) -> None:
        world = build_memory_world(asset_count=UNITS)
        desk, confirmed = confirmed_two(world)
        view = reallocate(world, desk, confirmed, world.assistant())
        assert view.detail.lines[0].allocated_count == BOOKED
        assert events(world, RESERVATION_REALLOCATED_ACTION) == []

    def test_no_free_unit_is_a_conflict_and_nothing_is_allocated(self) -> None:
        world = build_memory_world(asset_count=BOOKED)
        desk, confirmed = confirmed_two(world)
        first = allocation_ids(world, confirmed)[0]
        release(world, desk, first)
        (released,) = [a for a in world.store.committed.allocations if a.id == first]
        world.store.assets[:] = [
            replace(unit, status=AssetStatus.QUARANTINED) if unit.id == released.asset_id else unit
            for unit in world.store.assets
        ]
        with pytest.raises(AllocationConflictError, match="is not available at Cape Town CBD"):
            reallocate(world, desk, confirmed, ADMINISTRATOR)
        assert len(allocation_ids(world, confirmed)) == 1

    def test_counter_staff_of_another_branch_are_refused(self) -> None:
        world = build_memory_world(asset_count=UNITS)
        desk, confirmed = confirmed_two(world)
        with pytest.raises(BranchScopeError):
            reallocate(world, desk, confirmed, world.assistant(at_own_branch=False))
