"""A hold is all or nothing, run against ports and nothing else (BR-09, US-12).

A reservation with several lines is given every unit of every line or none of
them. If only two of three units are free, nothing is allocated, the
reservation stays a draft, and the refusal names the model and the dates and
never how many units are left (US-07).

A unit held for one period refuses an overlapping one, and a hire that starts
on the day another ends is fine, because a period is half open (BR-02).

The unit of work is the in memory double from tests/support. The same promise
is proved against real transactions in tests/integration/test_booking_transaction.py.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Final
from uuid import uuid4

import pytest

from app.application.booking.reservation_request import (
    CreateReservationCommand,
    RequestedLine,
)
from app.domain.catalogue import Asset, ProductModel
from app.domain.enums import AssetStatus, ConditionGrade, ReservationStatus
from app.domain.errors import AllocationConflictError
from app.domain.period import BookingPeriod
from tests.support.memory_world import FIRST_HIRE, MemoryWorld, build_memory_world, open_desk

OVERLAPPING_HIRE: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 11), date(2026, 3, 15))
SECOND_MODEL_SLUG: Final[str] = "wacker-plate-compactor"


def add_second_model(world: MemoryWorld, *, asset_count: int) -> ProductModel:
    """Add a second bookable model to a world, with its own units at the same branch."""
    model = ProductModel(
        id=uuid4(),
        sku="TSH-PM-0002",
        name="Wacker Plate Compactor",
        slug=SECOND_MODEL_SLUG,
        daily_rate=world.product_model.daily_rate,
        weekly_rate=world.product_model.weekly_rate,
        deposit_amount=world.product_model.deposit_amount,
        late_fee_per_day=world.product_model.late_fee_per_day,
        replacement_value=world.product_model.replacement_value,
        min_hire_days=world.product_model.min_hire_days,
        max_hire_days=world.product_model.max_hire_days,
    )
    world.store.product_models[model.id] = model
    world.store.assets.extend(
        Asset(
            id=uuid4(),
            asset_tag=f"TSH-CP-{number:04d}",
            product_model_id=model.id,
            branch_id=world.branch.id,
            status=AssetStatus.AVAILABLE,
            condition_grade=ConditionGrade.A,
        )
        for number in range(1, asset_count + 1)
    )
    return model


def two_line_command(
    world: MemoryWorld, *, hammers: int, compactors: int
) -> CreateReservationCommand:
    """Return the command for a draft of both models of a world."""
    return CreateReservationCommand(
        actor=world.customer,
        branch_code=world.branch.code,
        start=FIRST_HIRE.start,
        end=FIRST_HIRE.end,
        lines=(
            RequestedLine(model_slug=world.product_model.slug, quantity=hammers),
            RequestedLine(model_slug=SECOND_MODEL_SLUG, quantity=compactors),
        ),
    )


class TestHoldingIsAllOrNothing:
    """A line that cannot be given all of its units fails the whole hold (BR-09)."""

    def test_two_free_units_of_three_wanted_allocate_nothing(self) -> None:
        world = build_memory_world(asset_count=2)
        desk = open_desk(world)
        draft = desk.drafted(world.draft_command(quantity=3))
        with pytest.raises(AllocationConflictError):
            desk.hold.execute(desk.command_for(draft))
        assert world.store.committed.allocations == []
        assert world.stored(draft.detail.id).status is ReservationStatus.DRAFT

    def test_a_second_line_that_cannot_be_filled_releases_the_first(self) -> None:
        world = build_memory_world(asset_count=2)
        add_second_model(world, asset_count=1)
        desk = open_desk(world)
        draft = desk.drafted(two_line_command(world, hammers=2, compactors=2))
        with pytest.raises(AllocationConflictError):
            desk.hold.execute(desk.command_for(draft))
        assert world.store.committed.allocations == []
        assert world.stored(draft.detail.id).status is ReservationStatus.DRAFT

    def test_both_lines_are_held_when_both_can_be_filled(self) -> None:
        world = build_memory_world(asset_count=2)
        add_second_model(world, asset_count=1)
        desk = open_desk(world)
        draft = desk.drafted(two_line_command(world, hammers=2, compactors=1))
        held = desk.hold.execute(desk.command_for(draft))
        assert [line.allocated_count for line in held.detail.lines] == [2, 1]
        assert len(world.store.committed.allocations) == 3

    def test_the_conflict_names_the_model_and_the_dates_and_never_a_count(self) -> None:
        world = build_memory_world(asset_count=2)
        desk = open_desk(world)
        draft = desk.drafted(world.draft_command(quantity=3))
        with pytest.raises(AllocationConflictError) as refusal:
            desk.hold.execute(desk.command_for(draft))
        assert refusal.value.message == (
            "GBH 2-26 DRE Rotary Hammer is not available at Cape Town CBD from 9 March 2026 "
            "to 12 March 2026. Choose other dates or another branch."
        )
        assert refusal.value.detail == {
            "model_slug": world.product_model.slug,
            "period": FIRST_HIRE.as_postgres_daterange(),
        }

    def test_a_refused_hold_writes_no_audit_event(self) -> None:
        world = build_memory_world(asset_count=1)
        desk = open_desk(world)
        draft = desk.drafted(world.draft_command(quantity=2))
        events_before = len(world.store.committed.audit_events)
        with pytest.raises(AllocationConflictError):
            desk.hold.execute(desk.command_for(draft))
        assert len(world.store.committed.audit_events) == events_before

    def test_a_unit_held_for_an_overlapping_period_cannot_be_held_again(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        desk.held()
        second = desk.drafted(world.draft_command(OVERLAPPING_HIRE))
        with pytest.raises(AllocationConflictError):
            desk.hold.execute(desk.command_for(second))

    def test_a_hire_starting_the_day_the_first_one_ends_can_be_held(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        desk.held()
        adjacent = BookingPeriod(FIRST_HIRE.end, FIRST_HIRE.end + timedelta(days=2))
        held = desk.held(world.draft_command(adjacent))
        assert held.detail.status is ReservationStatus.HELD
