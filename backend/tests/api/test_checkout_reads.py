"""The checkout read and the rental read, through HTTP (FR-17, US-22, BR-26).

Before it hands anything over the counter reads the checkout of a reservation,
which says whether it may go ahead and, when not, why. Once the equipment is
out the counter reads the rental. These pin the shape of both reads, the
refusal the checkout read gives for each reason, who may read what, and that
neither read takes more statements for more units.

The checkout itself is pinned in tests/api/test_checkout.py. These run against
the in memory database, and the clock stands still on Monday the second of
March 2026, which is the first day of the hire every test here books.
"""

from __future__ import annotations

from typing import Final

import pytest
from fastapi import status
from sqlalchemy import Engine
from sqlmodel import Session

from app.domain.enums import UserRole
from app.infrastructure.models import UserAccount
from tests.support.booking_api import (
    FIRST_HIRE,
    BookingClient,
    BookingWorld,
    answered,
    build_booking_world,
    created,
)
from tests.support.checkout_api import (
    CHECKOUT_MEMBERS,
    checked_out,
    confirmed_today,
    read_checkout,
    read_rental,
)
from tests.support.factories import Factory
from tests.support.http import problem_of
from tests.support.statements import recorded_statements

TWO_UNITS: Final[int] = 2
THREE_UNITS: Final[int] = 3
ONE_DEPOSIT: Final[str] = "600.00"


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world whose branch holds three units."""
    built = build_booking_world(factory, asset_count=THREE_UNITS)
    session.commit()
    return built


@pytest.fixture
def assistant(session: Session, factory: Factory, world: BookingWorld) -> UserAccount:
    """Return a committed counter assistant of the world's branch."""
    account = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    session.commit()
    return account


class TestTheCheckoutRead:
    """GET /api/reservations/{id}/checkout, what the counter needs before it hands over."""

    def test_the_read_has_the_shape_of_the_contract_and_says_it_may_go_ahead(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        reservation = confirmed_today(booking, world, assistant, quantity=TWO_UNITS)
        body = answered(read_checkout(booking, assistant, reservation["id"]))

        assert body.keys() == CHECKOUT_MEMBERS
        assert (body["status"], body["canCheckOut"], body["refusal"], body["rentalId"]) == (
            "CONFIRMED", True, None, None
        )
        assert body["customer"] == {
            "id": str(world.profile.id),
            "displayName": world.profile.display_name,
            "phone": world.profile.contact_phone,
            "idDocumentType": "SA_ID",
            "idDocumentLast4": world.profile.id_document_last4,
            "accountStatus": "ACTIVE",
        }
        assert (body["from"], body["to"], body["hireDays"]) == ("2026-03-02", "2026-03-05", 3)
        assert body["hireTotalIncVat"] == reservation["estimatedTotalIncVat"]
        assert body["depositTotal"] == "1200.00"

    def test_each_unit_carries_its_tag_its_condition_and_its_deposit(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        reservation = confirmed_today(booking, world, assistant, quantity=TWO_UNITS)
        units = answered(read_checkout(booking, assistant, reservation["id"]))["units"]
        assert isinstance(units, list)
        assert [unit["assetTag"] for unit in units] == reservation["lines"][0]["assetTags"]
        assert {unit["modelSlug"] for unit in units} == {world.product_model.slug}
        assert {unit["conditionGrade"] for unit in units} == {"A"}
        assert {unit["depositPerUnit"] for unit in units} == {ONE_DEPOSIT}
        assert {unit["hourMeter"] for unit in units} == {None}

    def test_the_read_answers_by_the_reference_as_well(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        reservation = confirmed_today(booking, world, assistant)
        by_key = answered(read_checkout(booking, assistant, reservation["id"]))
        by_reference = answered(read_checkout(booking, assistant, reservation["reference"]))
        assert by_key == by_reference

    def test_staff_of_another_branch_may_read_it_and_are_told_why_they_may_not_act(
        self, booking: BookingClient, session: Session, factory: Factory, world: BookingWorld
    ) -> None:
        elsewhere = factory.user(role=UserRole.COUNTER_STAFF, branch=factory.branch())
        administrator = factory.user(role=UserRole.ADMIN)
        session.commit()
        reservation = confirmed_today(booking, world, administrator)
        body = answered(read_checkout(booking, elsewhere, reservation["id"]))
        assert body["canCheckOut"] is False
        assert body["refusal"] == (
            "Counter staff can only work on bookings at their own branch. This one is at "
            "another branch."
        )

    def test_a_hold_is_refused_in_the_words_the_checkout_would_use(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        draft = created(
            booking.create(assistant, world.payload(customer_profile_id=world.profile.id))
        )
        answered(booking.hold(assistant, draft["id"]))
        body = answered(read_checkout(booking, assistant, draft["id"]))
        assert body["canCheckOut"] is False
        assert body["refusal"] == "This reservation is on hold, so it cannot be collected."

    def test_a_hire_that_starts_next_week_cannot_be_checked_out_today(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        reservation = confirmed_today(booking, world, assistant, period=FIRST_HIRE)
        body = answered(read_checkout(booking, assistant, reservation["id"]))
        assert body["canCheckOut"] is False
        assert body["refusal"] == (
            "This reservation cannot be collected before the first day of the hire."
        )

    def test_once_it_is_checked_out_the_read_names_the_rental(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        reservation = confirmed_today(booking, world, assistant)
        rental = checked_out(booking, assistant, reservation["id"])
        body = answered(read_checkout(booking, assistant, reservation["id"]))
        assert (body["status"], body["rentalId"], body["canCheckOut"]) == (
            "COLLECTED", rental["id"], False
        )
        assert body["refusal"] == "This reservation has already been checked out."


class TestTheRentalRead:
    """GET /api/rentals/{id}, the rental the counter works with once it has gone out."""

    def test_the_rental_reads_back_by_its_key_and_its_reference(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        reservation = confirmed_today(booking, world, assistant)
        rental = checked_out(booking, assistant, reservation["id"])
        assert answered(read_rental(booking, assistant, rental["id"])) == rental
        assert answered(read_rental(booking, assistant, rental["reference"])) == rental

    def test_a_rental_that_does_not_exist_is_a_404_in_a_plain_sentence(
        self, booking: BookingClient, assistant: UserAccount
    ) -> None:
        response = read_rental(booking, assistant, "TSH-H-26-999999")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert problem_of(response)["detail"] == (
            "We could not find that rental. Check the reference and try again."
        )

    def test_staff_of_another_branch_read_it_and_may_not_record_a_return(
        self, booking: BookingClient, session: Session, factory: Factory, world: BookingWorld,
        assistant: UserAccount,
    ) -> None:
        elsewhere = factory.user(role=UserRole.COUNTER_STAFF, branch=factory.branch())
        session.commit()
        reservation = confirmed_today(booking, world, assistant)
        rental = checked_out(booking, assistant, reservation["id"])
        body = answered(read_rental(booking, elsewhere, rental["id"]))
        assert body["canReturn"] is False
        assert body["items"][0]["assetTag"] == rental["items"][0]["assetTag"]


class TestTheReadsDoNotGrowWithTheUnits:
    """Both reads take a fixed number of statements, however many units the hire has."""

    def test_the_checkout_read_of_two_units_takes_as_many_statements_as_one(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        sqlite_engine: Engine,
    ) -> None:
        one = confirmed_today(booking, world, assistant)
        two = confirmed_today(booking, world, assistant, quantity=TWO_UNITS)
        counts = []
        for reservation in (one, two):
            with recorded_statements(sqlite_engine) as statements:
                answered(read_checkout(booking, assistant, reservation["id"]))
            counts.append(len(statements))
        assert counts[0] == counts[1]

    def test_the_rental_read_of_two_units_takes_as_many_statements_as_one(
        self,
        booking: BookingClient,
        world: BookingWorld,
        assistant: UserAccount,
        sqlite_engine: Engine,
    ) -> None:
        one = checked_out(booking, assistant, confirmed_today(booking, world, assistant)["id"])
        two = checked_out(
            booking,
            assistant,
            confirmed_today(booking, world, assistant, quantity=TWO_UNITS)["id"],
        )
        counts = []
        for rental in (one, two):
            with recorded_statements(sqlite_engine) as statements:
                answered(read_rental(booking, assistant, rental["id"]))
            counts.append(len(statements))
        assert counts[0] == counts[1]


