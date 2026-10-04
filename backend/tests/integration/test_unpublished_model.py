"""A model the administrator hides leaves every public read at once and no booking behind (US-30).

Hiding a product model takes it out of the catalogue, the availability search
and the quote the moment the change commits, because each of them asks for
published models only, and the availability search can only be run here,
where the exclusion constraint's GiST index and `daterange` exist. The counter
books through the same path a customer does, so it cannot book a hidden model
either, and is told so naming the line. A booking made before the model was
hidden is left alone, and it is still checked out at the counter. Publishing
the model again brings it back.

Every request goes through HTTP on the real database, on the still clock of
the booking tests, which stands on Monday the second of March 2026.
"""

from __future__ import annotations

from typing import Final

import pytest
from fastapi import status
from sqlmodel import Session

from app.domain.enums import UserRole
from app.infrastructure.models import UserAccount
from tests.support.admin_catalogue_api import publish
from tests.support.booking_api import BookingClient, BookingWorld, answered, build_booking_world
from tests.support.catalogue import (
    AVAILABILITY_PATH,
    model_availability_path,
    model_path,
    model_quote_path,
)
from tests.support.checkout_api import TODAY_HIRE, checked_out, confirmed_today
from tests.support.factories import Factory
from tests.support.report_api import refused_fields

pytestmark = pytest.mark.postgres

UNITS: Final[int] = 2
PERIOD: Final[dict[str, str]] = {
    "from": TODAY_HIRE.start.isoformat(),
    "to": TODAY_HIRE.end.isoformat(),
}


@pytest.fixture
def world(postgres_session: Session, postgres_factory: Factory) -> BookingWorld:
    """Return a committed branch holding two units of one published model."""
    built = build_booking_world(postgres_factory, asset_count=UNITS)
    postgres_session.commit()
    return built


@pytest.fixture
def assistant(
    postgres_session: Session, postgres_factory: Factory, world: BookingWorld
) -> UserAccount:
    """Return a committed counter assistant of the world's branch."""
    account = postgres_factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    postgres_session.commit()
    return account


@pytest.fixture
def administrator(postgres_session: Session, postgres_factory: Factory) -> UserAccount:
    """Return a committed administrator."""
    account = postgres_factory.user(role=UserRole.ADMIN)
    postgres_session.commit()
    return account


def listed_slugs(booking: BookingClient) -> list[str]:
    """Return the slugs the public availability search lists for the period."""
    page = answered(booking.client.get(AVAILABILITY_PATH, params=PERIOD))
    return [item["model"]["slug"] for item in page["items"]]


def public_statuses(booking: BookingClient, slug: str) -> list[int]:
    """Return what the public model, its availability and its quote answer."""
    return [
        booking.client.get(model_path(slug)).status_code,
        booking.client.get(model_availability_path(slug), params=PERIOD).status_code,
        booking.client.get(model_quote_path(slug), params=PERIOD).status_code,
    ]


def test_a_hidden_model_leaves_every_public_read_and_comes_back_when_published(
    booking: BookingClient, world: BookingWorld, administrator: UserAccount
) -> None:
    slug = world.product_model.slug
    assert listed_slugs(booking) == [slug]
    answered(publish(booking, administrator, world.product_model.id, False))
    assert listed_slugs(booking) == []
    assert public_statuses(booking, slug) == [status.HTTP_404_NOT_FOUND] * 3
    answered(publish(booking, administrator, world.product_model.id, True))
    assert listed_slugs(booking) == [slug]
    assert public_statuses(booking, slug) == [status.HTTP_200_OK] * 3


def test_the_counter_cannot_book_a_hidden_model_and_is_told_which_line(
    booking: BookingClient, world: BookingWorld, assistant: UserAccount, administrator: UserAccount
) -> None:
    answered(publish(booking, administrator, world.product_model.id, False))
    response = booking.create(
        assistant, world.payload(TODAY_HIRE, customer_profile_id=world.profile.id)
    )
    assert refused_fields(response) == {"body.lines.0.modelSlug"}


def test_a_booking_made_before_the_model_was_hidden_is_still_checked_out(
    booking: BookingClient, world: BookingWorld, assistant: UserAccount, administrator: UserAccount
) -> None:
    booked = confirmed_today(booking, world, assistant)
    answered(publish(booking, administrator, world.product_model.id, False))
    assert answered(booking.read(assistant, booked["id"]))["status"] == "CONFIRMED"
    rental = checked_out(booking, assistant, booked["id"])
    assert (rental["reservationId"], rental["status"]) == (booked["id"], "OPEN")
