"""Two checkouts of one reservation at the same moment open one rental, through HTTP.

Two counter assistants, or one with an impatient finger, post the checkout of
one confirmed reservation at the same instant. Each request has a PostgreSQL
connection of its own, and a barrier releases both together, so the two
transactions genuinely overlap.

Exactly one rental is opened. The checkout locks the reservation before it
looks for a rental, so the second request waits for the first, then finds the
rental it committed and answers with it, 200 to the first one's 201, and
writes nothing. Nobody is answered 500, no unit is put on hire twice and no
charge is raised twice. The unique key on the reservation of a rental would
refuse a second one if anything ever got past the lock, and
test_checkout_transaction.py proves that key on its own.

The race is run more than once, because one clean run of a race proves less
than a few.
"""

from __future__ import annotations

from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.domain.enums import AssetStatus, ReservationStatus, UserRole
from app.infrastructure.models import (
    Asset,
    AuditEvent,
    Charge,
    Rental,
    RentalItem,
    Reservation,
    UserAccount,
)
from tests.support.booking_api import BookingClient, BookingWorld, answered, build_booking_world
from tests.support.booking_race import application_on, post_bodies_at_once
from tests.support.checkout_api import checkout_body, checkout_path, confirmed_today, read_checkout
from tests.support.clock import FixedClock
from tests.support.factories import Factory

pytestmark = pytest.mark.postgres

UNITS: Final[int] = 2
ROUNDS: Final[int] = 3
CONTENDERS: Final[int] = 2


@pytest.fixture
def world(postgres_session: Session, postgres_factory: Factory) -> BookingWorld:
    """Return a committed branch whose shelf holds two units."""
    built = build_booking_world(postgres_factory, asset_count=UNITS)
    postgres_session.commit()
    return built


@pytest.fixture
def assistants(
    postgres_session: Session, postgres_factory: Factory, world: BookingWorld
) -> list[UserAccount]:
    """Return two committed counter assistants of the world's branch."""
    accounts = [
        postgres_factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
        for _ in range(CONTENDERS)
    ]
    postgres_session.commit()
    return accounts


@pytest.mark.parametrize("round_number", range(ROUNDS))
def test_two_checkouts_at_once_open_one_rental_and_the_second_is_told_of_it(
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
        reservation = confirmed_today(booking, world, first, quantity=UNITS)
        preview = answered(read_checkout(booking, first, reservation["id"]))
        body = checkout_body(preview)
        path = checkout_path(reservation["id"])
        responses = post_bodies_at_once(
            application,
            [(path, booking.headers(first), body), (path, booking.headers(second), body)],
        )

    assert sorted(response.status_code for response in responses) == [
        status.HTTP_200_OK,
        status.HTTP_201_CREATED,
    ]
    assert len({response.json()["id"] for response in responses}) == 1

    postgres_session.rollback()
    assert len(postgres_session.exec(select(Rental)).all()) == 1
    assert len(postgres_session.exec(select(RentalItem)).all()) == UNITS
    assert len(postgres_session.exec(select(Charge)).all()) == 2
    assert {asset.status for asset in postgres_session.exec(select(Asset))} == {
        AssetStatus.ON_HIRE
    }
    (stored,) = postgres_session.exec(select(Reservation)).all()
    assert stored.status is ReservationStatus.COLLECTED
    opened = postgres_session.exec(
        select(AuditEvent).where(col(AuditEvent.action) == "rental.checked_out")
    ).all()
    assert len(opened) == 1
