"""A reallocation on PostgreSQL, through the allocation path of a hold (US-32, BR-07, BR-09).

A booking a force release left short is given a replacement by staff at the
counter, through the locking query, the exclusion constraint and the
translation of its refusal, the way a hold takes its units. These prove on the
real database that the reallocation takes a free unit the constraint accepts
and records it, that a booking short of nothing is answered as it stands, and
that when the only free unit was taken first, whether the locking query saw it
go or a stale list of free units let the insert reach the constraint, the
reallocation is refused with nothing allocated.

The booking is for today, Monday the second of March 2026, to the fifth, at a
branch that holds two units. The release itself is proved in
tests/integration/test_force_release_transaction.py, and the helpers are in
tests/support/admin_pg.py and tests/support/allocation_pg.py.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from app.domain import catalogue
from app.domain.enums import ReservationStatus
from app.domain.errors import AllocationConflictError
from app.domain.identity import Actor
from tests.support.admin_pg import (
    audit_trail,
    committed_administrator,
    committed_world,
    counter_assistant,
    run_reallocation,
    run_release,
)
from tests.support.allocation_pg import (
    database_error_behind,
    domain_units,
    rival_line,
    stale_free_list,
    take_for_the_rival,
    take_out_of_service,
    the_held_allocation,
)
from tests.support.booking import opening
from tests.support.booking_api import BookingWorld
from tests.support.checkout_api import TODAY_HIRE
from tests.support.checkout_pg import confirm_for_today, held_allocations
from tests.support.factories import Factory
from tests.support.pg import EXCLUSION_VIOLATION_SQLSTATE, sqlstate_of

pytestmark = pytest.mark.postgres

UNITS: Final[int] = 2
ONE_UNIT: Final[int] = 1
REALLOCATED: Final[str] = "reservation.reallocated"


@pytest.fixture
def world(postgres_session: Session, postgres_factory: Factory) -> BookingWorld:
    """Return a committed branch holding two units of the factory's model."""
    return committed_world(postgres_session, postgres_factory, UNITS)


@pytest.fixture
def assistant(postgres_session: Session, postgres_factory: Factory, world: BookingWorld) -> Actor:
    """Return a counter assistant of the world's branch, as an actor."""
    return counter_assistant(postgres_session, postgres_factory, world)


@pytest.fixture
def administrator(postgres_session: Session, postgres_factory: Factory) -> Actor:
    """Return a committed administrator, as an actor."""
    return committed_administrator(postgres_session, postgres_factory)


@pytest.fixture
def reservation_id(postgres_engine: Engine, world: BookingWorld, assistant: Actor) -> UUID:
    """Return the key of a booking of one unit for today, confirmed at the counter."""
    return confirm_for_today(postgres_engine, world, assistant, ONE_UNIT)


@pytest.fixture
def units(postgres_engine: Engine, world: BookingWorld) -> dict[UUID, catalogue.Asset]:
    """Return the two units of the world as the domain sees them, by their key."""
    return domain_units(postgres_engine, world)


@pytest.fixture
def rival_line_id(
    postgres_session: Session, postgres_factory: Factory, world: BookingWorld
) -> UUID:
    """Return the line of another booking of the same model, the same days and branch."""
    return rival_line(postgres_session, postgres_factory, world)


class TestAReallocationTakesAFreeUnit:
    """A short booking is topped up through the locking query and the constraint (BR-07)."""

    def test_the_other_unit_is_held_once_the_released_one_is_out_of_service(
        self,
        postgres_engine: Engine,
        administrator: Actor,
        assistant: Actor,
        reservation_id: UUID,
        units: dict[UUID, catalogue.Asset],
    ) -> None:
        released = the_held_allocation(postgres_engine, reservation_id)
        run_release(postgres_engine, administrator, released.id)
        take_out_of_service(postgres_engine, released.asset_id)
        (other,) = [key for key in units if key != released.asset_id]

        view = run_reallocation(postgres_engine, assistant, reservation_id)

        replacement = the_held_allocation(postgres_engine, reservation_id)
        assert (replacement.asset_id, replacement.release_reason) == (other, None)
        assert view.detail.status is ReservationStatus.CONFIRMED
        (event,) = audit_trail(postgres_engine, REALLOCATED)
        assert (event.actor_user_id, event.entity_id) == (assistant.user_id, reservation_id)
        assert (event.after_state or {})["asset_tags"] == [units[other].asset_tag]

    def test_a_booking_short_of_nothing_is_answered_as_it_stands(
        self, postgres_engine: Engine, assistant: Actor, reservation_id: UUID
    ) -> None:
        held = the_held_allocation(postgres_engine, reservation_id)
        run_reallocation(postgres_engine, assistant, reservation_id)
        assert the_held_allocation(postgres_engine, reservation_id).id == held.id
        assert audit_trail(postgres_engine, REALLOCATED) == []


class TestWhenTheOnlyFreeUnitWasTakenFirst:
    """The reallocation is refused and allocates nothing, whichever check sees the loss."""

    def test_the_locking_query_finds_nothing_free(
        self,
        postgres_engine: Engine,
        administrator: Actor,
        assistant: Actor,
        reservation_id: UUID,
        units: dict[UUID, catalogue.Asset],
        rival_line_id: UUID,
    ) -> None:
        released = the_held_allocation(postgres_engine, reservation_id)
        run_release(postgres_engine, administrator, released.id)
        (other,) = [key for key in units if key != released.asset_id]
        take_out_of_service(postgres_engine, other)
        take_for_the_rival(postgres_engine, rival_line_id, units[released.asset_id], TODAY_HIRE)

        with pytest.raises(AllocationConflictError):
            run_reallocation(postgres_engine, assistant, reservation_id)
        assert held_allocations(postgres_engine, reservation_id) == []
        assert audit_trail(postgres_engine, REALLOCATED) == []

    def test_the_exclusion_constraint_refuses_a_unit_a_stale_free_list_offered(
        self,
        postgres_engine: Engine,
        administrator: Actor,
        assistant: Actor,
        reservation_id: UUID,
        units: dict[UUID, catalogue.Asset],
        rival_line_id: UUID,
    ) -> None:
        released = the_held_allocation(postgres_engine, reservation_id)
        run_release(postgres_engine, administrator, released.id)
        unit = units[released.asset_id]
        take_for_the_rival(postgres_engine, rival_line_id, unit, TODAY_HIRE)

        with pytest.raises(AllocationConflictError) as refused:
            run_reallocation(
                postgres_engine,
                assistant,
                reservation_id,
                unit_of_work=opening(postgres_engine, stale_free_list([unit])),
            )
        violation = database_error_behind(refused.value)
        assert sqlstate_of(violation) == EXCLUSION_VIOLATION_SQLSTATE
        assert held_allocations(postgres_engine, reservation_id) == []
        assert audit_trail(postgres_engine, REALLOCATED) == []
