"""A customer's list leaves out the baskets they abandoned, on PostgreSQL.

A draft replaced by a changed basket is cancelled, and it never held a unit.
The query of a customer's own list leaves such a reservation out, in the
statement itself, so the count and the page agree and a page is never short.
A booking cancelled after it held units is still a cancelled booking and is
still listed. Staff still see everything.

These run the reservation routes against the real database, where the test of
whether a reservation ever held a unit is an EXISTS over the allocation table,
and the clock stands still on Monday the second of March 2026.
"""

from __future__ import annotations

from typing import Final

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from app.domain.enums import UserRole
from tests.support.booking_api import BookingClient, BookingWorld, answered, build_booking_world
from tests.support.factories import Factory
from tests.support.statements import recorded_statements

pytestmark = pytest.mark.postgres

ABANDONED: Final[int] = 3


@pytest.fixture
def world(postgres_session: Session, postgres_factory: Factory) -> BookingWorld:
    """Return a committed branch holding two units, and a customer."""
    built = build_booking_world(postgres_factory, asset_count=2)
    postgres_session.commit()
    return built


def references_in(body: dict[str, object]) -> list[str]:
    """Return the references on a page, in the order they were returned."""
    items = body["items"]
    assert isinstance(items, list)
    return [str(item["reference"]) for item in items]


def abandon(booking: BookingClient, world: BookingWorld) -> str:
    """Draft a basket and throw it away before it holds anything, and return its reference."""
    draft = booking.drafted(world)
    answered(booking.cancel(world.customer, draft["id"]))
    return str(draft["reference"])


class TestTheCustomersOwnList:
    """Abandoned baskets are not in it, and cancelled bookings are."""

    def test_only_the_basket_that_was_kept_is_listed_and_counted(
        self, booking: BookingClient, world: BookingWorld
    ) -> None:
        for _ in range(ABANDONED):
            abandon(booking, world)
        kept = booking.drafted(world)
        body = answered(booking.listing(world.customer))
        assert references_in(body) == [kept["reference"]]
        assert body["total"] == 1

    def test_a_cancelled_booking_that_held_units_is_still_listed(
        self, booking: BookingClient, world: BookingWorld
    ) -> None:
        abandoned = abandon(booking, world)
        held = booking.held(world)
        answered(booking.cancel(world.customer, held["id"]))
        body = answered(booking.listing(world.customer, status="CANCELLED"))
        assert references_in(body) == [held["reference"]]
        assert abandoned not in references_in(answered(booking.listing(world.customer)))

    def test_a_page_is_full_after_the_abandoned_baskets_are_left_out(
        self, booking: BookingClient, world: BookingWorld
    ) -> None:
        kept = []
        for _ in range(2):
            kept.append(booking.drafted(world)["reference"])
            abandon(booking, world)
        body = answered(booking.listing(world.customer, page=1, pageSize=2))
        assert references_in(body) == kept[::-1]
        assert body["total"] == 2

    def test_the_condition_is_in_the_statement_that_reads_the_page(
        self, booking: BookingClient, world: BookingWorld, postgres_engine: Engine
    ) -> None:
        abandon(booking, world)
        with recorded_statements(postgres_engine) as statements:
            answered(booking.listing(world.customer))
        listing = [sql for sql in statements if "ORDER BY reservation.created_at" in sql]
        assert len(listing) == 1
        assert "EXISTS" in listing[0]
        assert "asset_allocation" in listing[0]


class TestStaff:
    """Staff still see every reservation, an abandoned basket included."""

    def test_staff_list_the_abandoned_basket_of_a_customer(
        self,
        booking: BookingClient,
        postgres_session: Session,
        postgres_factory: Factory,
        world: BookingWorld,
    ) -> None:
        administrator = postgres_factory.user(role=UserRole.ADMIN)
        postgres_session.commit()
        abandoned = abandon(booking, world)
        body = answered(
            booking.listing(administrator, customerProfileId=str(world.profile.id))
        )
        assert references_in(body) == [abandoned]
