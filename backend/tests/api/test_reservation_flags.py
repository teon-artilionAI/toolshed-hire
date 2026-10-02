"""`canHold`, `canConfirm` and `canCancel`, for every status and every kind of caller.

The three flags say what the caller may do to a reservation right now. They
are worked out on the server, so a screen never repeats the rules of the
lifecycle. This file reads one reservation in each of the eight statuses as
each of four callers, through HTTP, and pins every cell.

The same table is pinned with no database in tests/unit/test_reservation_views.py.
Here it is read off the real route, the real repository and the real states,
so a flag and the move it promises cannot drift apart. The last class proves
that, by asking for every move a flag offers and every move it does not.

DRAFT, HELD, CONFIRMED, CANCELLED and EXPIRED are reached through the routes.
COLLECTED, RETURNED and NO_SHOW belong to later changes, so those three are
written to the database directly.

These run against the in memory database, and the clock stands still on
Monday the second of March 2026 until a test moves it.
"""

from __future__ import annotations

from datetime import timedelta
from enum import Enum
from typing import Final

import pytest
from fastapi import status
from sqlmodel import Session

from app.domain.enums import ReservationStatus, UserRole
from app.infrastructure.models import UserAccount
from tests.support.booking_api import (
    BookingClient,
    BookingWorld,
    answered,
    build_booking_world,
    force_status,
)
from tests.support.factories import Factory

JUST_PAST_THE_HOLD: Final[timedelta] = timedelta(minutes=30, seconds=1)
HOLD: Final[str] = "canHold"
CONFIRM: Final[str] = "canConfirm"
CANCEL: Final[str] = "canCancel"
FLAGS: Final[tuple[str, ...]] = (HOLD, CONFIRM, CANCEL)
FORCED: Final[frozenset[ReservationStatus]] = frozenset(
    {ReservationStatus.COLLECTED, ReservationStatus.RETURNED, ReservationStatus.NO_SHOW}
)
# What a caller who may act is offered in each status. Every other flag is false.
OFFERED: Final[dict[ReservationStatus, frozenset[str]]] = {
    ReservationStatus.DRAFT: frozenset({HOLD, CANCEL}),
    ReservationStatus.HELD: frozenset({CONFIRM, CANCEL}),
    ReservationStatus.CONFIRMED: frozenset({CANCEL}),
    ReservationStatus.COLLECTED: frozenset(),
    ReservationStatus.RETURNED: frozenset(),
    ReservationStatus.CANCELLED: frozenset(),
    ReservationStatus.NO_SHOW: frozenset(),
    ReservationStatus.EXPIRED: frozenset(),
}


class Caller(str, Enum):
    """The four kinds of caller the table is asked about."""

    OWNER = "the customer who owns it"
    COUNTER_HERE = "counter staff at the branch"
    COUNTER_ELSEWHERE = "counter staff of another branch"
    ADMIN = "an administrator"


MAY_ACT: Final[frozenset[Caller]] = frozenset({Caller.OWNER, Caller.COUNTER_HERE, Caller.ADMIN})
CELLS: Final[list[tuple[ReservationStatus, Caller]]] = [
    (reservation_status, caller) for reservation_status in ReservationStatus for caller in Caller
]


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world whose branch holds two units."""
    built = build_booking_world(factory, asset_count=2)
    session.commit()
    return built


@pytest.fixture
def callers(session: Session, factory: Factory, world: BookingWorld) -> dict[Caller, UserAccount]:
    """Return a committed account for each kind of caller."""
    accounts = {
        Caller.OWNER: world.customer,
        Caller.COUNTER_HERE: factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch),
        Caller.COUNTER_ELSEWHERE: factory.user(
            role=UserRole.COUNTER_STAFF, branch=factory.branch()
        ),
        Caller.ADMIN: factory.user(role=UserRole.ADMIN),
    }
    session.commit()
    return accounts


def a_reservation_in(
    reservation_status: ReservationStatus,
    booking: BookingClient,
    session: Session,
    world: BookingWorld,
) -> str:
    """Bring a reservation of the world's customer to a status, and return its key."""
    customer = world.customer
    if reservation_status is ReservationStatus.DRAFT:
        return str(booking.drafted(world)["id"])
    if reservation_status is ReservationStatus.HELD:
        return str(booking.held(world)["id"])
    if reservation_status is ReservationStatus.CANCELLED:
        held = booking.held(world)
        return str(answered(booking.cancel(customer, held["id"]))["id"])
    if reservation_status is ReservationStatus.EXPIRED:
        held = booking.held(world)
        booking.clock.advance(JUST_PAST_THE_HOLD)
        return str(held["id"])
    confirmed = str(booking.confirmed(world)["id"])
    if reservation_status in FORCED:
        force_status(session, confirmed, reservation_status)
    return confirmed


def offered(body: dict[str, object]) -> set[str]:
    """Return the flags of a reservation that are true."""
    return {flag for flag in FLAGS if body[flag] is True}


class TestTheTableOfStatusesAndCallers:
    """Every status against every kind of caller, read through the route."""

    @pytest.mark.parametrize(
        ("reservation_status", "caller"),
        CELLS,
        ids=[f"{reservation_status.value}/{caller.name}" for reservation_status, caller in CELLS],
    )
    def test_the_flags_are_exactly_what_the_table_says(
        self,
        booking: BookingClient,
        session: Session,
        world: BookingWorld,
        callers: dict[Caller, UserAccount],
        reservation_status: ReservationStatus,
        caller: Caller,
    ) -> None:
        key = a_reservation_in(reservation_status, booking, session, world)

        body = answered(booking.read(callers[caller], key))

        assert body["status"] == reservation_status.value
        expected = OFFERED[reservation_status] if caller in MAY_ACT else frozenset()
        assert offered(body) == expected

    def test_the_table_names_every_status(self) -> None:
        assert set(OFFERED) == set(ReservationStatus)

    def test_an_unverified_customer_is_not_offered_confirm_and_staff_still_are(
        self,
        booking: BookingClient,
        session: Session,
        world: BookingWorld,
        callers: dict[Caller, UserAccount],
    ) -> None:
        key = booking.held(world)["id"]
        world.customer.email_verified_at = None
        session.add(world.customer)
        session.commit()
        assert offered(answered(booking.read(world.customer, key))) == {CANCEL}
        assert offered(answered(booking.read(callers[Caller.COUNTER_HERE], key))) == {
            CONFIRM,
            CANCEL,
        }

    def test_the_flags_in_a_list_are_the_flags_of_each_reservation(
        self, booking: BookingClient, world: BookingWorld
    ) -> None:
        booking.drafted(world)
        booking.held(world)
        items = answered(booking.listing(world.customer))["items"]
        assert isinstance(items, list)
        assert [offered(item) for item in items] == [{CONFIRM, CANCEL}, {HOLD, CANCEL}]


class TestAFlagAndTheMoveItPromisesAgree:
    """A move the flag offers succeeds, and one it does not offer is refused."""

    MOVES: Final[dict[str, str]] = {HOLD: "hold", CONFIRM: "confirm", CANCEL: "cancellation"}
    REACHABLE: Final[tuple[ReservationStatus, ...]] = tuple(
        reservation_status
        for reservation_status in ReservationStatus
        if reservation_status not in FORCED
    )

    @pytest.mark.parametrize("reservation_status", REACHABLE)
    @pytest.mark.parametrize("flag", FLAGS)
    def test_the_owner_can_make_exactly_the_moves_they_were_offered(
        self,
        booking: BookingClient,
        session: Session,
        world: BookingWorld,
        reservation_status: ReservationStatus,
        flag: str,
    ) -> None:
        key = a_reservation_in(reservation_status, booking, session, world)
        was_offered = answered(booking.read(world.customer, key))[flag] is True

        response = booking.client.post(
            f"/api/reservations/{key}/{self.MOVES[flag]}", headers=booking.headers(world.customer)
        )

        if was_offered:
            assert response.status_code == status.HTTP_200_OK, response.text
        else:
            assert response.status_code == status.HTTP_409_CONFLICT, response.text
