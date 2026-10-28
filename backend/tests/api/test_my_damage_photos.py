"""The photographs of damage on a customer's own hire, and the owner's view of them (#112).

A customer reads the photographs of every report filed against their own hire,
because those are the evidence for what was kept back from the deposit. Another
customer's hire, and a photograph on it, is not found, in the words used for one
that never existed. The owner reads the same photographs on the report when
resolving it. These run against the in memory database on a clock that stands
still on Monday the second of March 2026.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final
from uuid import uuid4

import pytest
from fastapi import status
from sqlmodel import Session

from app.api.damage_photo_deps import get_photo_store
from app.domain.damage_photo import PHOTO_LINK_LIFETIME
from app.domain.enums import UserRole
from app.infrastructure.models import UserAccount
from app.infrastructure.photo_store import SwitchedOffPhotoStore
from app.main import app as production_app
from tests.support.booking_api import BookingClient, BookingWorld, answered, created
from tests.support.damage_api import refusal_of
from tests.support.factories import Factory
from tests.support.http import problem_code
from tests.support.memory_photos import MemoryPhotoStore
from tests.support.photo_api import (
    PHOTO_MEMBERS,
    PNG_TYPE,
    list_photos,
    my_photo_link,
    my_photos,
    photo_link,
    report_on_a_hire,
    upload,
)
from tests.support.photo_files import jpeg_with_gps, png_with_gps
from tests.support.rental_api import on_hire, worked_example_world

TWO_UNITS: Final[int] = 2
NO_SUCH_RENTAL: Final[str] = "We could not find that rental. Check the reference and try again."


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world of two units with the deposit of the worked example."""
    return worked_example_world(session, factory, units=TWO_UNITS)


@pytest.fixture
def assistant(session: Session, factory: Factory, world: BookingWorld) -> UserAccount:
    """Return a committed counter assistant of the world's branch."""
    account = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    session.commit()
    return account


@pytest.fixture
def owner(session: Session, factory: Factory) -> UserAccount:
    """Return the committed administrator who resolves reports."""
    account = factory.user(role=UserRole.ADMIN)
    session.commit()
    return account


@pytest.fixture
def stranger(session: Session, factory: Factory, world: BookingWorld) -> UserAccount:
    """Return another committed customer with a profile of their own."""
    account = factory.user(role=UserRole.CUSTOMER)
    factory.customer_profile(branch=world.branch, account=account)
    session.commit()
    return account


@pytest.fixture
def hire_with_photos(
    booking: BookingClient, world: BookingWorld, assistant: UserAccount
) -> tuple[dict[str, object], dict[str, object], list[dict[str, object]]]:
    """Return the customer's hire, its report and the two photographs attached to it."""
    rental, report = report_on_a_hire(booking, world, assistant)
    first = created(upload(booking, assistant, report["id"], jpeg_with_gps()))
    booking.clock.advance(timedelta(minutes=1))
    second = created(upload(booking, assistant, report["id"], png_with_gps(), PNG_TYPE))
    return rental, report, [first, second]


class TestTheCustomersOwnHire:
    """The customer sees the evidence for the deduction, and a link that expires."""

    def test_the_customer_lists_the_photographs_of_their_hire(
        self,
        booking: BookingClient,
        world: BookingWorld,
        hire_with_photos: tuple[dict[str, object], dict[str, object], list[dict[str, object]]],
    ) -> None:
        rental, report, photos = hire_with_photos

        listed = answered(my_photos(booking, world.customer, rental["id"]))

        assert [item["id"] for item in listed["items"]] == [photo["id"] for photo in photos]
        assert all(set(item) == PHOTO_MEMBERS for item in listed["items"])
        assert {item["damageReportReference"] for item in listed["items"]} == {report["reference"]}

    def test_the_customer_opens_one_through_a_five_minute_link(
        self,
        booking: BookingClient,
        world: BookingWorld,
        hire_with_photos: tuple[dict[str, object], dict[str, object], list[dict[str, object]]],
        photo_store: MemoryPhotoStore,
    ) -> None:
        rental, _, photos = hire_with_photos

        link = answered(my_photo_link(booking, world.customer, rental["id"], photos[1]["id"]))

        expires_at = datetime.fromisoformat(str(link["expiresAt"]))
        assert expires_at - booking.clock.now() == PHOTO_LINK_LIFETIME
        assert "response-content-disposition=attachment" in str(link["url"])
        assert photo_store.links[-1].file_name.endswith(".png")

    def test_a_hire_with_no_report_lists_nothing(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
    ) -> None:
        rental = on_hire(booking, world, assistant)
        assert answered(my_photos(booking, world.customer, rental["id"])) == {"items": []}


class TestSomebodyElsesHire:
    """Not found, exactly as a hire that never existed."""

    def test_another_customers_hire_is_not_found(
        self,
        booking: BookingClient,
        stranger: UserAccount,
        hire_with_photos: tuple[dict[str, object], dict[str, object], list[dict[str, object]]],
    ) -> None:
        rental, _, photos = hire_with_photos

        listed = my_photos(booking, stranger, rental["id"])
        opened = my_photo_link(booking, stranger, rental["id"], photos[0]["id"])
        missing = my_photos(booking, stranger, uuid4())

        for response in (listed, opened, missing):
            assert response.status_code == status.HTTP_404_NOT_FOUND, response.text
            assert problem_code(response) == "not-found"
        assert listed.json()["detail"] == missing.json()["detail"] == NO_SUCH_RENTAL

    def test_a_photograph_from_another_hire_is_not_found_on_this_one(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        hire_with_photos: tuple[dict[str, object], dict[str, object], list[dict[str, object]]],
    ) -> None:
        _, _, photos = hire_with_photos
        other_rental, _ = report_on_a_hire(booking, world, assistant)

        response = my_photo_link(booking, world.customer, other_rental["id"], photos[0]["id"])

        assert response.status_code == status.HTTP_404_NOT_FOUND, response.text

    def test_nobody_signed_out_is_answered_401(
        self,
        booking: BookingClient,
        hire_with_photos: tuple[dict[str, object], dict[str, object], list[dict[str, object]]],
    ) -> None:
        rental, _, photos = hire_with_photos
        for response in (
            my_photos(booking, None, rental["id"]),
            my_photo_link(booking, None, rental["id"], photos[0]["id"]),
        ):
            assert response.status_code == status.HTTP_401_UNAUTHORIZED, response.text

    def test_staff_read_through_the_report_and_not_through_the_customers_route(
        self,
        booking: BookingClient,
        assistant: UserAccount,
        hire_with_photos: tuple[dict[str, object], dict[str, object], list[dict[str, object]]],
    ) -> None:
        rental, _, _ = hire_with_photos
        response = my_photos(booking, assistant, rental["id"])
        assert response.status_code == status.HTTP_403_FORBIDDEN, response.text


class TestTheOwnerResolvingTheReport:
    """The owner reads the same photographs on the report before recording the cost."""

    def test_the_owner_lists_and_opens_the_photographs_of_the_report(
        self,
        booking: BookingClient,
        owner: UserAccount,
        hire_with_photos: tuple[dict[str, object], dict[str, object], list[dict[str, object]]],
    ) -> None:
        _, report, photos = hire_with_photos

        listed = answered(list_photos(booking, owner, report["id"]))
        link = answered(photo_link(booking, owner, report["id"], photos[0]["id"]))

        assert [item["id"] for item in listed["items"]] == [photo["id"] for photo in photos]
        assert str(link["url"]).startswith("https://storage.googleapis.com/")


class TestPhotographsSwitchedOff:
    """The customer is told plainly, and the hire itself still reads."""

    def test_both_customer_routes_say_photographs_are_off(
        self,
        booking: BookingClient,
        world: BookingWorld,
        hire_with_photos: tuple[dict[str, object], dict[str, object], list[dict[str, object]]],
    ) -> None:
        rental, _, photos = hire_with_photos
        production_app.dependency_overrides[get_photo_store] = SwitchedOffPhotoStore

        for response in (
            my_photos(booking, world.customer, rental["id"]),
            my_photo_link(booking, world.customer, rental["id"], photos[0]["id"]),
        ):
            assert refusal_of(response, status.HTTP_503_SERVICE_UNAVAILABLE) == (
                "Photographs are not switched on yet."
            )
        mine = answered(
            booking.client.get("/api/me/rentals", headers=booking.headers(world.customer))
        )
        assert mine["total"] == 1
