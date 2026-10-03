"""Two returns of one unit at once, and the overdue sweep, on PostgreSQL (BR-29, BR-52).

Two counter assistants take the same unit back at the same instant. Each
request has a connection of its own and a barrier releases both together, so
the two transactions genuinely overlap. The return locks the rental before it
reads its items, so the second waits for the first, then finds the unit back
and is refused with 409. The unit is shelved once, the deposit is settled once
and nobody is answered 500. The race is run more than once.

The sweep moves a hire with a unit out past its due date to OVERDUE, a bounded
batch at a time, earliest due date first, with an audit event that names no
actor, and the next sweep takes what the first left.
"""

from __future__ import annotations

from datetime import date
from typing import Final
from uuid import UUID

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.application.booking.expire_holds import ExpireHoldsAndNoShowsUseCase, SweepCommand
from app.domain.enums import AssetStatus, RentalStatus, UserRole
from app.domain.identity import Actor
from app.infrastructure.models import Asset, AuditEvent, Charge, Rental, UserAccount
from tests.support.booking import opening
from tests.support.booking_api import BookingClient, BookingWorld, build_booking_world
from tests.support.booking_race import application_on, post_bodies_at_once
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.rental_api import item_ids, on_hire, return_body
from tests.support.return_pg import clock_on, out_today

pytestmark = pytest.mark.postgres

ROUNDS: Final[int] = 3
THREE_HIRES: Final[int] = 3
SMALL_BATCH: Final[int] = 2
TWO_DAYS_PAST_DUE: Final[date] = date(2026, 3, 7)


@pytest.fixture
def world(postgres_session: Session, postgres_factory: Factory) -> BookingWorld:
    """Return a committed branch whose shelf holds three units."""
    built = build_booking_world(postgres_factory, asset_count=THREE_HIRES)
    postgres_session.commit()
    return built


@pytest.fixture
def assistants(
    postgres_session: Session, postgres_factory: Factory, world: BookingWorld
) -> list[UserAccount]:
    """Return two committed counter assistants of the world's branch."""
    accounts = [
        postgres_factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch) for _ in range(2)
    ]
    postgres_session.commit()
    return accounts


@pytest.mark.parametrize("round_number", range(ROUNDS))
def test_two_returns_of_one_unit_at_once_take_it_back_once(
    postgres_engine: Engine,
    postgres_session: Session,
    world: BookingWorld,
    assistants: list[UserAccount],
    round_number: int,
) -> None:
    del round_number
    clock = FixedClock()
    first, second = assistants
    with application_on(postgres_engine, clock) as application:
        booking = BookingClient(TestClient(application), clock)
        rental = on_hire(booking, world, first)
        path = f"/api/rentals/{rental['id']}/returns"
        body = return_body(*item_ids(rental))
        responses = post_bodies_at_once(
            application,
            [(path, booking.headers(first), body), (path, booking.headers(second), body)],
        )

    assert sorted(response.status_code for response in responses) == [
        status.HTTP_200_OK,
        status.HTTP_409_CONFLICT,
    ]
    postgres_session.rollback()
    (stored,) = postgres_session.exec(select(Rental)).all()
    assert stored.status is RentalStatus.SETTLED
    releases = postgres_session.exec(
        select(Charge).where(col(Charge.charge_type) == "DEPOSIT_RELEASE")
    ).all()
    assert len(releases) == 1
    returned = postgres_session.exec(
        select(AuditEvent).where(col(AuditEvent.action) == "rental.items_returned")
    ).all()
    assert len(returned) == 1
    assert {asset.status for asset in postgres_session.exec(select(Asset))} == {
        AssetStatus.AVAILABLE
    }


def test_the_sweep_marks_hires_past_due_a_bounded_batch_at_a_time(
    postgres_engine: Engine,
    postgres_session: Session,
    world: BookingWorld,
    assistants: list[UserAccount],
) -> None:
    staff = Actor(
        user_id=assistants[0].id, role=UserRole.COUNTER_STAFF, branch_id=world.branch.id
    )
    rentals: list[UUID] = [out_today(postgres_engine, world, staff, 1) for _ in range(THREE_HIRES)]
    sweep = ExpireHoldsAndNoShowsUseCase(opening(postgres_engine)(), clock_on(TWO_DAYS_PAST_DUE))

    first = sweep.execute(SweepCommand(overdue_batch_size=SMALL_BATCH))
    second = sweep.execute(SweepCommand(overdue_batch_size=SMALL_BATCH))
    third = sweep.execute(SweepCommand(overdue_batch_size=SMALL_BATCH))

    assert (len(first.overdue_references), len(second.overdue_references)) == (SMALL_BATCH, 1)
    assert third.overdue_references == ()
    postgres_session.rollback()
    statuses = {
        rental.id: rental.status
        for rental in postgres_session.exec(select(Rental).where(col(Rental.id).in_(rentals)))
    }
    assert set(statuses.values()) == {RentalStatus.OVERDUE}
    events = postgres_session.exec(
        select(AuditEvent).where(col(AuditEvent.action) == "rental.overdue")
    ).all()
    assert len(events) == THREE_HIRES
    assert {(event.actor_user_id, event.actor_role) for event in events} == {(None, None)}
