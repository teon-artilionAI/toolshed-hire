"""The use case that puts a draft on hold, run against ports and nothing else.

Holding is where units are taken, so these tests are about what is taken and
when. Every line is given named units or none is (BR-09, US-12), the hold
lasts thirty minutes (BR-12), and a hold that ran out is lapsed first so its
units can be held here (BR-13). The unit of work is the in memory double from
tests/support, and the clock stands still on the second of March 2026.

That a hold is all or nothing is in test_hold_all_or_nothing.py. The same use
case runs against real transactions in tests/integration/test_booking_transaction.py,
where the exclusion constraint is the one refusing.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Final

import pytest

from app.application.booking.access import RESERVATION_HELD_ACTION, ReservationCommand
from app.application.booking.read_models import ReservationKey
from app.domain.enums import AccountStatus, ReleaseReason, ReservationStatus
from app.domain.errors import (
    AccountOnHoldError,
    AllocationConflictError,
    BranchScopeError,
    NotFound,
    StateTransitionError,
    ValidationFailure,
)
from app.domain.identity import CustomerProfile
from app.domain.states import HOLD_DURATION
from tests.support.clock import DEFAULT_INSTANT
from tests.support.memory_world import FIRST_HIRE, MemoryWorld, build_memory_world, open_desk

JUST_PAST_THE_HOLD: Final[timedelta] = HOLD_DURATION + timedelta(seconds=1)


def on_hold(world: MemoryWorld) -> CustomerProfile:
    """Return the world's customer profile with the account put on hold."""
    return replace(world.profile, account_status=AccountStatus.ON_HOLD)


class TestHoldingTakesNamedUnits:
    """A hold gives every line specific tagged units, and starts the thirty minutes."""

    def test_a_held_reservation_is_on_hold_for_thirty_minutes(self) -> None:
        desk = open_desk(build_memory_world())
        held = desk.held()
        assert held.detail.status is ReservationStatus.HELD
        assert held.detail.hold_expires_at == DEFAULT_INSTANT + HOLD_DURATION

    def test_three_units_of_one_model_are_three_specific_assets(self) -> None:
        world = build_memory_world(asset_count=4)
        desk = open_desk(world)
        held = desk.hold.execute(
            desk.command_for(desk.drafted(world.draft_command(quantity=3)))
        )
        (line,) = world.stored(held.detail.id).lines
        assert [allocation.asset_id for allocation in line.active_allocations()] == [
            asset.id for asset in world.assets[:3]
        ]
        assert held.detail.lines[0].allocated_count == 3

    def test_every_allocation_is_at_the_collection_branch_for_the_whole_period(self) -> None:
        world = build_memory_world(asset_count=2)
        desk = open_desk(world)
        held = desk.hold.execute(
            desk.command_for(desk.drafted(world.draft_command(quantity=2)))
        )
        (line,) = world.stored(held.detail.id).lines
        assert {allocation.branch_id for allocation in line.allocations} == {world.branch.id}
        assert {allocation.period for allocation in line.allocations} == {FIRST_HIRE}

    def test_the_hold_writes_one_audit_event_naming_the_units(self) -> None:
        world = build_memory_world(asset_count=2)
        desk = open_desk(world)
        held = desk.hold.execute(
            desk.command_for(desk.drafted(world.draft_command(quantity=2)))
        )
        event = world.store.committed.audit_events[-1]
        assert event.action == RESERVATION_HELD_ACTION
        assert event.entity_id == held.detail.id
        assert event.actor_user_id == world.customer_account_id
        assert event.before_state is not None
        assert event.before_state["status"] == "DRAFT"
        assert event.after_state is not None
        assert event.after_state["status"] == "HELD"
        assert event.after_state["asset_tags"] == ["TSH-DR-0001", "TSH-DR-0002"]

    def test_holding_queues_no_notification(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        desk.held()
        assert world.store.committed.notifications == {}

    def test_the_figures_of_the_draft_are_not_changed_by_holding(self) -> None:
        desk = open_desk(build_memory_world())
        draft = desk.drafted()
        held = desk.hold.execute(desk.command_for(draft))
        assert held.detail.estimated_total_inc_vat == draft.detail.estimated_total_inc_vat
        assert held.detail.lines[0].line_subtotal_ex_vat == (
            draft.detail.lines[0].line_subtotal_ex_vat
        )

    def test_a_counter_assistant_at_the_branch_may_hold_a_customers_draft(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        draft = desk.drafted()
        held = desk.hold.execute(desk.command_for(draft, actor=world.assistant()))
        assert held.detail.status is ReservationStatus.HELD
        assert held.detail.lines[0].asset_tags == ("TSH-DR-0001",)


class TestWhatAHoldIsRefusedFor:
    """The state, the customer, the dates and the caller can each refuse a hold."""

    def test_a_reservation_already_on_hold_cannot_be_held_again(self) -> None:
        world = build_memory_world(asset_count=2)
        desk = open_desk(world)
        held = desk.held()
        with pytest.raises(StateTransitionError) as refusal:
            desk.hold.execute(desk.command_for(held))
        assert refusal.value.detail == {"from_status": "HELD", "to_status": "HELD"}
        assert len(world.store.committed.allocations) == 1

    def test_a_customer_put_on_hold_since_the_draft_cannot_hold_it(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        draft = desk.drafted()
        world.store.profiles[world.customer_account_id] = on_hold(world)
        with pytest.raises(AccountOnHoldError):
            desk.hold.execute(desk.command_for(draft))
        assert world.store.committed.allocations == []

    def test_a_draft_whose_start_has_slipped_into_the_past_cannot_be_held(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        draft = desk.drafted()
        desk.clock.advance(timedelta(days=8))
        with pytest.raises(ValidationFailure) as refusal:
            desk.hold.execute(desk.command_for(draft))
        assert refusal.value.message == "The hire has to start today or later."
        assert refusal.value.rule == "BR-04"
        assert world.store.committed.allocations == []

    def test_somebody_elses_draft_is_not_found(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        draft = desk.drafted()
        stranger = build_memory_world().customer
        with pytest.raises(NotFound) as refusal:
            desk.hold.execute(desk.command_for(draft, actor=stranger))
        assert refusal.value.message == (
            "We could not find that reservation. Check the reference and try again."
        )

    def test_a_reference_nobody_issued_is_not_found_in_the_same_words(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        with pytest.raises(NotFound) as refusal:
            desk.hold.execute(
                ReservationCommand(
                    actor=world.customer, key=ReservationKey.parse("TSH-R-26-999999")
                )
            )
        assert refusal.value.message == (
            "We could not find that reservation. Check the reference and try again."
        )

    def test_a_counter_assistant_of_another_branch_is_refused(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        draft = desk.drafted()
        with pytest.raises(BranchScopeError):
            desk.hold.execute(desk.command_for(draft, actor=world.assistant(at_own_branch=False)))
        assert world.store.committed.allocations == []

    def test_a_draft_can_be_named_by_its_reference(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        draft = desk.drafted()
        held = desk.hold.execute(
            ReservationCommand(
                actor=world.customer, key=ReservationKey.parse(draft.detail.reference.lower())
            )
        )
        assert held.detail.id == draft.detail.id


class TestAnExpiredHoldIsLapsedBeforeUnitsAreLookedFor:
    """A unit somebody stopped wanting half an hour ago is free to be held (BR-13)."""

    def test_the_only_unit_can_be_held_again_once_the_first_hold_has_run_out(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        first = desk.held()
        desk.clock.advance(JUST_PAST_THE_HOLD)
        second = desk.held()
        assert second.detail.status is ReservationStatus.HELD
        lapsed = world.stored(first.detail.id)
        assert lapsed.status is ReservationStatus.EXPIRED
        (released,) = lapsed.lines[0].allocations
        assert released.release_reason is ReleaseReason.EXPIRED

    def test_the_only_unit_cannot_be_held_while_the_first_hold_still_stands(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        desk.held()
        desk.clock.advance(HOLD_DURATION)
        with pytest.raises(AllocationConflictError):
            desk.held()
