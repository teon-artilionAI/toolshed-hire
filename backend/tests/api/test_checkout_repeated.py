"""A checkout asked for again, through HTTP.

A second click, a retry over a dropped connection or a second assistant posts
the checkout of a reservation that is already out. The answer is 200 with the
rental the first checkout opened, and nothing more is written. A member of
staff of another branch is still refused, because the branch is checked
before anything else.

Two checkouts that arrive at the same moment are raced on PostgreSQL in
tests/integration/test_checkout_race.py. These run against the in memory
database, and the clock stands still on the first day of the hire.
"""

from __future__ import annotations

from typing import Final

import pytest
from fastapi import status
from sqlmodel import Session, select

from app.domain.enums import UserRole
from app.infrastructure.models import AuditEvent, Charge, Rental, RentalItem, UserAccount
from tests.support.booking_api import (
    BookingClient,
    BookingWorld,
    answered,
    build_booking_world,
    created,
)
from tests.support.checkout_api import (
    check_out,
    checked_out,
    checkout_body,
    confirmed_today,
    read_checkout,
)
from tests.support.factories import Factory
from tests.support.http import problem_of

LOCATION_HEADER: Final[str] = "Location"


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world whose branch holds one unit."""
    built = build_booking_world(factory)
    session.commit()
    return built


@pytest.fixture
def assistant(session: Session, factory: Factory, world: BookingWorld) -> UserAccount:
    """Return a committed counter assistant of the world's branch."""
    account = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    session.commit()
    return account


def counts(session: Session) -> tuple[int, int, int, int]:
    """Return how many rentals, items, charges and audit events are stored."""
    return (
        len(session.exec(select(Rental)).all()),
        len(session.exec(select(RentalItem)).all()),
        len(session.exec(select(Charge)).all()),
        len(session.exec(select(AuditEvent)).all()),
    )


class TestACheckoutAskedForAgain:
    """A second click answers with the rental the first one opened, and writes nothing."""

    def test_the_second_answer_is_200_with_the_same_rental(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        reservation = confirmed_today(booking, world, assistant)
        preview = answered(read_checkout(booking, assistant, reservation["id"]))
        body = checkout_body(preview)
        first = created(check_out(booking, assistant, reservation["id"], body))
        again = check_out(booking, assistant, reservation["id"], body)
        assert again.status_code == status.HTTP_200_OK
        assert again.json() == first
        assert LOCATION_HEADER not in again.headers

    def test_nothing_more_is_written_the_second_time(
        self,
        booking: BookingClient,
        session: Session,
        world: BookingWorld,
        assistant: UserAccount,
    ) -> None:
        reservation = confirmed_today(booking, world, assistant)
        preview = answered(read_checkout(booking, assistant, reservation["id"]))
        created(check_out(booking, assistant, reservation["id"], checkout_body(preview)))
        before = counts(session)
        answered(check_out(booking, assistant, reservation["id"], checkout_body(preview)))
        assert counts(session) == before

    def test_the_answer_does_not_depend_on_the_list_sent_the_second_time(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        reservation = confirmed_today(booking, world, assistant)
        first = checked_out(booking, assistant, reservation["id"])
        unsigned = {"items": [{"allocationId": str(first["id"]), "conditionOut": "C"}],
                    "agreementSigned": False}  # fmt: skip
        again = answered(check_out(booking, assistant, reservation["reference"], unsigned))
        assert again == first

    def test_staff_of_another_branch_are_still_refused_for_a_reservation_already_out(
        self,
        booking: BookingClient,
        session: Session,
        factory: Factory,
        world: BookingWorld,
        assistant: UserAccount,
    ) -> None:
        elsewhere = factory.user(role=UserRole.COUNTER_STAFF, branch=factory.branch())
        session.commit()
        reservation = confirmed_today(booking, world, assistant)
        preview = answered(read_checkout(booking, elsewhere, reservation["id"]))
        checked_out(booking, assistant, reservation["id"])
        response = check_out(booking, elsewhere, reservation["id"], checkout_body(preview))
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert problem_of(response)["detail"] == preview["refusal"]
