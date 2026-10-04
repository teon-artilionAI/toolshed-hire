"""A force release on PostgreSQL, against the real exclusion constraint (US-32).

An administrator releases one unit of a booking by hand, through the asset
repository, with the reason REALLOCATED and an audit event that keeps the
reason they gave (BR-25, BR-49). The booking is then short of that unit.

These prove on the real database that the release is written with its event,
that an allocation already released is refused, that the released row no
longer counts for the constraint, so another booking can take the unit for
the same days, and that a unit out on hire on its booking cannot be released
at all. How a short booking is given a replacement is in
tests/integration/test_reallocation_transaction.py.

The booking is for today, Monday the second of March 2026, to the fifth, at a
branch that holds two units. The helpers are in tests/support/admin_pg.py and
tests/support/allocation_pg.py.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.domain import catalogue
from app.domain.enums import ReleaseReason, UserRole
from app.domain.errors import StateTransitionError
from app.domain.identity import Actor
from app.infrastructure.models import AssetAllocation
from tests.support.admin_pg import (
    REASON,
    audit_trail,
    committed_administrator,
    committed_world,
    counter_assistant,
    row_of,
    run_release,
)
from tests.support.allocation_pg import (
    domain_units,
    rival_line,
    take_for_the_rival,
    the_held_allocation,
)
from tests.support.booking_api import BookingWorld
from tests.support.checkout_api import TODAY_HIRE
from tests.support.checkout_pg import confirm_for_today, held_allocations, run_checkout
from tests.support.clock import DEFAULT_INSTANT
from tests.support.factories import Factory
from tests.support.pg import EXCLUSION_VIOLATION_SQLSTATE, sqlstate_of

pytestmark = pytest.mark.postgres

UNITS: Final[int] = 2
ONE_UNIT: Final[int] = 1
RELEASED: Final[str] = "reservation.unit_released"


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


class TestTheReleaseIsWrittenWithItsEvent:
    """The allocation is released with REALLOCATED, and the event keeps the reason."""

    def test_the_allocation_is_released_as_reallocated(
        self, postgres_engine: Engine, administrator: Actor, reservation_id: UUID
    ) -> None:
        allocation = the_held_allocation(postgres_engine, reservation_id)
        run_release(postgres_engine, administrator, allocation.id)

        stored = row_of(postgres_engine, AssetAllocation, allocation.id)
        assert (stored["released_at"], stored["release_reason"]) == (
            DEFAULT_INSTANT, ReleaseReason.REALLOCATED
        )
        assert held_allocations(postgres_engine, reservation_id) == []

    def test_the_event_names_the_administrator_the_unit_and_the_reason(
        self,
        postgres_engine: Engine,
        administrator: Actor,
        reservation_id: UUID,
        units: dict[UUID, catalogue.Asset],
    ) -> None:
        allocation = the_held_allocation(postgres_engine, reservation_id)
        run_release(postgres_engine, administrator, allocation.id)

        (event,) = audit_trail(postgres_engine, RELEASED)
        assert (event.entity_type, event.entity_id) == ("reservation", reservation_id)
        assert (event.actor_user_id, event.actor_role) == (administrator.user_id, UserRole.ADMIN)
        assert event.after_state is not None
        assert (event.after_state["reason"], event.after_state["release_reason"]) == (
            REASON, ReleaseReason.REALLOCATED.value
        )
        assert event.after_state["asset_tag"] == units[allocation.asset_id].asset_tag
        assert (event.after_state["units_short"], event.after_state["allocation_id"]) == (
            ONE_UNIT, str(allocation.id)
        )

    def test_an_allocation_released_already_is_refused(
        self, postgres_engine: Engine, administrator: Actor, reservation_id: UUID
    ) -> None:
        allocation = the_held_allocation(postgres_engine, reservation_id)
        run_release(postgres_engine, administrator, allocation.id)
        with pytest.raises(StateTransitionError, match="no longer held"):
            run_release(postgres_engine, administrator, allocation.id)
        assert len(audit_trail(postgres_engine, RELEASED)) == ONE_UNIT


class TestTheReleasedRowNoLongerCounts:
    """A released allocation drops out of the exclusion constraint without being deleted."""

    def test_another_booking_can_take_the_unit_for_the_same_days_once_it_is_released(
        self,
        postgres_engine: Engine,
        postgres_session: Session,
        postgres_factory: Factory,
        world: BookingWorld,
        administrator: Actor,
        reservation_id: UUID,
        units: dict[UUID, catalogue.Asset],
    ) -> None:
        line_id = rival_line(postgres_session, postgres_factory, world)
        allocation = the_held_allocation(postgres_engine, reservation_id)
        unit = units[allocation.asset_id]
        with pytest.raises(IntegrityError) as refused:
            take_for_the_rival(postgres_engine, line_id, unit, TODAY_HIRE)
        assert sqlstate_of(refused.value) == EXCLUSION_VIOLATION_SQLSTATE

        run_release(postgres_engine, administrator, allocation.id)
        taken = take_for_the_rival(postgres_engine, line_id, unit, TODAY_HIRE)
        assert taken.released_at is None
        assert row_of(postgres_engine, AssetAllocation, allocation.id)["released_at"] is not None


class TestAUnitOnHireIsNotReleased:
    """A unit out on hire on its own booking is let go when it comes back, not by hand."""

    def test_the_release_is_refused_and_changes_nothing(
        self,
        postgres_engine: Engine,
        administrator: Actor,
        assistant: Actor,
        reservation_id: UUID,
    ) -> None:
        allocation = the_held_allocation(postgres_engine, reservation_id)
        run_checkout(postgres_engine, assistant, reservation_id)
        before = row_of(postgres_engine, AssetAllocation, allocation.id)

        with pytest.raises(StateTransitionError, match="out on hire"):
            run_release(postgres_engine, administrator, allocation.id)
        assert row_of(postgres_engine, AssetAllocation, allocation.id) == before
        assert audit_trail(postgres_engine, RELEASED) == []
