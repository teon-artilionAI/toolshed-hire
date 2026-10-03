"""Staff marking a booking as not collected, run against ports and nothing else (BR-17, BR-18).

A member of staff at the counter may mark a confirmed booking as a no show
from the start of the first day of the hire, with a reason. It is the same move
as the sweep's, so the units are released with the reason `NO_SHOW` and the
strike is counted. The audit event names the member of staff and keeps the
reason. These pin that, the refusals, and the third strike arriving this way.

The unit of work is the in memory double from tests/support. The worked
example hire starts on Monday the ninth of March 2026, and the clock is moved
to eight in the morning that day in Cape Town unless a test says otherwise.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Final
from uuid import uuid4

import pytest

from app.application.booking.access import RESERVATION_NO_SHOW_ACTION
from app.application.booking.mark_no_show import (
    NO_SHOW_REASON_MAX_LENGTH,
    REASON_REQUIRED_MESSAGE,
    MarkNoShowCommand,
    MarkNoShowUseCase,
)
from app.application.booking.no_show import CUSTOMER_PUT_ON_HOLD_ACTION
from app.application.booking.read_models import ReservationKey
from app.application.booking.views import ReservationView
from app.application.refusal import refused_parameter_of
from app.domain.booking import Reservation
from app.domain.enums import AccountStatus, ReleaseReason, ReservationStatus, UserRole
from app.domain.errors import BranchScopeError, StateTransitionError, ValidationFailure
from app.domain.identity import Actor
from app.domain.period import BookingPeriod
from app.domain.states.guards import FIRST_DAY_NOT_COME_MESSAGE
from tests.support.memory import InMemoryUnitOfWork
from tests.support.memory_world import BookingDesk, MemoryWorld, build_memory_world, open_desk

REASON: Final[str] = "Nobody came by closing time and the phone went unanswered."
# Eight in the morning in Cape Town on the first day of the hire.
FIRST_MORNING: Final[datetime] = datetime(2026, 3, 9, 6, 0, tzinfo=UTC)
ONE_DAY: Final[timedelta] = timedelta(days=1)
JUST_PAST_THE_HOLD: Final[timedelta] = timedelta(minutes=30, seconds=1)
EARLIER_NO_SHOWS: Final[tuple[date, ...]] = (date(2025, 11, 3), date(2026, 1, 12))


def mark(
    world: MemoryWorld, desk: BookingDesk, view: ReservationView, actor: Actor, reason: str = REASON
) -> ReservationView:
    """Mark a reservation as not collected as `actor`, through the use case."""
    use_case = MarkNoShowUseCase(InMemoryUnitOfWork(world.store), desk.clock)
    return use_case.execute(
        MarkNoShowCommand(actor=actor, key=ReservationKey.of(view.detail.id), reason=reason)
    )


def confirmed_on_the_first_morning(world: MemoryWorld) -> tuple[BookingDesk, ReservationView]:
    """Confirm the worked example hire as the customer, then move to its first morning."""
    desk = open_desk(world)
    confirmed = desk.confirmed()
    desk.clock.instant = FIRST_MORNING
    return desk, confirmed


def earlier_no_show(world: MemoryWorld, first_day: date, number: int) -> None:
    """Commit a reservation of the world's customer that was not collected."""
    world.store.committed.reservations.append(
        Reservation(
            reference=f"TSH-R-25-{number:06d}",
            customer_profile_id=world.profile.id,
            branch_id=world.branch.id,
            period=BookingPeriod(first_day, first_day + ONE_DAY),
            status=ReservationStatus.NO_SHOW,
            created_by_user_id=world.customer_account_id,
        )
    )


class TestStaffMarkANoShow:
    """The move, the release of the units and what the audit event keeps."""

    def test_an_assistant_at_the_branch_marks_it_and_the_units_are_released(self) -> None:
        world = build_memory_world()
        desk, confirmed = confirmed_on_the_first_morning(world)

        shown = mark(world, desk, confirmed, world.assistant())

        assert shown.detail.status is ReservationStatus.NO_SHOW
        assert shown.detail.lines[0].allocated_count == 0
        assert (shown.can_hold, shown.can_confirm, shown.can_cancel) == (False, False, False)
        (allocation,) = world.stored(confirmed.detail.id).lines[0].allocations
        assert (allocation.release_reason, allocation.released_at) == (
            ReleaseReason.NO_SHOW,
            FIRST_MORNING,
        )

    def test_the_audit_event_names_the_assistant_and_keeps_the_reason(self) -> None:
        world = build_memory_world()
        desk, confirmed = confirmed_on_the_first_morning(world)
        assistant = world.assistant()

        mark(world, desk, confirmed, assistant, f"  {REASON}  ")

        (event,) = [
            event
            for event in world.store.committed.audit_events
            if event.action == RESERVATION_NO_SHOW_ACTION
        ]
        assert (event.actor_user_id, event.actor_role) == (
            assistant.user_id,
            UserRole.COUNTER_STAFF,
        )
        assert event.after_state is not None
        assert event.after_state["no_show_reason"] == REASON
        assert event.after_state["status"] == "NO_SHOW"

    def test_an_administrator_marks_one_at_any_branch(self) -> None:
        world = build_memory_world()
        desk, confirmed = confirmed_on_the_first_morning(world)
        administrator = Actor(user_id=uuid4(), role=UserRole.ADMIN)
        assert mark(world, desk, confirmed, administrator).detail.status is (
            ReservationStatus.NO_SHOW
        )

    def test_the_strike_is_counted_on_the_customer(self) -> None:
        world = build_memory_world()
        desk, confirmed = confirmed_on_the_first_morning(world)
        mark(world, desk, confirmed, world.assistant())
        assert world.store.committed.no_shows == {world.profile.id: 1}

    def test_the_third_strike_by_hand_puts_the_customer_on_hold(self) -> None:
        world = build_memory_world()
        for number, first_day in enumerate(EARLIER_NO_SHOWS, start=1):
            earlier_no_show(world, first_day, number)
        desk, confirmed = confirmed_on_the_first_morning(world)
        assistant = world.assistant()

        mark(world, desk, confirmed, assistant)

        assert world.store.committed.account_statuses == {world.profile.id: AccountStatus.ON_HOLD}
        (event,) = [
            event
            for event in world.store.committed.audit_events
            if event.action == CUSTOMER_PUT_ON_HOLD_ACTION
        ]
        assert event.actor_user_id == assistant.user_id


class TestWhatIsRefused:
    """Another branch, a booking that is not confirmed or not started, and a bad reason."""

    def test_an_assistant_of_another_branch_is_refused_and_nothing_changes(self) -> None:
        world = build_memory_world()
        desk, confirmed = confirmed_on_the_first_morning(world)
        with pytest.raises(BranchScopeError):
            mark(world, desk, confirmed, world.assistant(at_own_branch=False))
        assert world.stored(confirmed.detail.id).status is ReservationStatus.CONFIRMED

    def test_a_booking_whose_hire_has_not_started_is_refused(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        confirmed = desk.confirmed()
        with pytest.raises(StateTransitionError) as refused:
            mark(world, desk, confirmed, world.assistant())
        assert refused.value.message == FIRST_DAY_NOT_COME_MESSAGE
        assert world.stored(confirmed.detail.id).status is ReservationStatus.CONFIRMED

    def test_a_booking_that_is_only_on_hold_is_refused(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        held = desk.held()
        with pytest.raises(StateTransitionError):
            mark(world, desk, held, world.assistant())

    def test_a_hold_that_ran_out_is_lapsed_first_and_then_refused(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        held = desk.held()
        desk.clock.advance(JUST_PAST_THE_HOLD)
        with pytest.raises(StateTransitionError) as refused:
            mark(world, desk, held, world.assistant())
        assert refused.value.from_status == "EXPIRED"
        assert world.stored(held.detail.id).status is ReservationStatus.EXPIRED

    @pytest.mark.parametrize("reason", ["", "   "], ids=["empty", "blank"])
    def test_a_reason_that_says_nothing_is_refused_by_name(self, reason: str) -> None:
        world = build_memory_world()
        desk, confirmed = confirmed_on_the_first_morning(world)
        with pytest.raises(ValidationFailure) as refused:
            mark(world, desk, confirmed, world.assistant(), reason)
        assert refused_parameter_of(refused.value) == "reason"
        assert refused.value.message == REASON_REQUIRED_MESSAGE

    def test_a_reason_longer_than_the_contract_allows_is_refused_by_name(self) -> None:
        world = build_memory_world()
        desk, confirmed = confirmed_on_the_first_morning(world)
        with pytest.raises(ValidationFailure) as refused:
            mark(world, desk, confirmed, world.assistant(), "x" * (NO_SHOW_REASON_MAX_LENGTH + 1))
        assert refused_parameter_of(refused.value) == "reason"
        assert world.stored(confirmed.detail.id).status is ReservationStatus.CONFIRMED
