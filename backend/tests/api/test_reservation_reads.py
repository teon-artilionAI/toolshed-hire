"""Reading one reservation and a list of them, through HTTP (FR-09, BR-42).

A customer is shown their own reservations and nobody else's. One that is not
theirs is answered 404, never 403, in exactly the words used for a reference
nobody ever issued, and the scope is in the query, so the test also reads the
statements and finds the owner in every lookup. Counter staff and
administrators read any customer's reservation, at any branch.

A list is newest first, can be narrowed by status, and is paged. Only staff
may narrow it to one customer or one branch.

These run against the in memory database, and the clock stands still on
Monday the second of March 2026.
"""

from __future__ import annotations

from typing import Final
from uuid import uuid4

import pytest
from fastapi import status
from sqlalchemy import Engine
from sqlmodel import Session

from app.domain.enums import UserRole
from app.infrastructure.models import UserAccount
from tests.support.booking_api import (
    BookingClient,
    BookingWorld,
    answered,
    build_booking_world,
    reservation_path,
)
from tests.support.factories import Factory
from tests.support.http import problem_code, problem_of
from tests.support.statements import recorded_statements

NOT_FOUND_PROBLEM: Final[str] = "not-found"
AUTHORISATION_PROBLEM: Final[str] = "authorisation-failure"
VALIDATION_PROBLEM: Final[str] = "request-validation-failure"
SHARED_REQUEST_ID: Final[str] = "6f1c2b9e-3d4a-4c5b-8e7f-0a1b2c3d4e5f"
NOT_FOUND_SENTENCE: Final[str] = (
    "We could not find that reservation. Check the reference and try again."
)
PAGE_MEMBERS: Final[frozenset[str]] = frozenset({"items", "page", "pageSize", "total"})
DEFAULT_PAGE_SIZE: Final[int] = 20


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world whose branch holds three units."""
    built = build_booking_world(factory, asset_count=3)
    session.commit()
    return built


@pytest.fixture
def somebody_else(session: Session, factory: Factory, world: BookingWorld) -> UserAccount:
    """Return a second committed customer, with a profile of their own."""
    account = factory.user(role=UserRole.CUSTOMER)
    factory.customer_profile(branch=world.branch, account=account)
    session.commit()
    return account


def references_in(body: dict[str, object]) -> list[str]:
    """Return the references on a page, in the order they were returned."""
    items = body["items"]
    assert isinstance(items, list)
    return [str(item["reference"]) for item in items]


class TestOwnershipIsInTheQuery:
    """Somebody else's reservation is not found, and is never fetched (BR-42)."""

    def test_the_owner_reads_their_own_reservation_by_key_and_by_reference(
        self, booking: BookingClient, world: BookingWorld
    ) -> None:
        draft = booking.drafted(world)
        by_key = answered(booking.read(world.customer, draft["id"]))
        by_reference = answered(booking.read(world.customer, draft["reference"]))
        assert by_key == by_reference == draft

    def test_another_customer_gets_404_and_never_403(
        self, booking: BookingClient, world: BookingWorld, somebody_else: UserAccount
    ) -> None:
        draft = booking.drafted(world)
        response = booking.read(somebody_else, draft["id"])
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert problem_code(response) == NOT_FOUND_PROBLEM
        assert problem_of(response)["detail"] == NOT_FOUND_SENTENCE

    def test_the_answer_is_the_same_as_for_a_reservation_that_does_not_exist(
        self, booking: BookingClient, world: BookingWorld, somebody_else: UserAccount
    ) -> None:
        draft = booking.drafted(world)
        headers = booking.headers(somebody_else, SHARED_REQUEST_ID)
        not_theirs = problem_of(booking.client.get(reservation_path(draft["id"]), headers=headers))
        missing_id = uuid4()
        missing = problem_of(booking.client.get(reservation_path(missing_id), headers=headers))
        # The two documents differ only where they quote the key that was asked for.
        swapped = str(missing).replace(str(missing_id), str(draft["id"]))
        assert swapped == str(not_theirs)

    @pytest.mark.parametrize("move", ["hold", "confirm", "cancellation"])
    def test_another_customer_cannot_move_it_either_and_is_told_the_same(
        self,
        booking: BookingClient,
        world: BookingWorld,
        somebody_else: UserAccount,
        move: str,
    ) -> None:
        draft = booking.drafted(world)
        response = booking.client.post(
            f"{reservation_path(draft['id'])}/{move}", headers=booking.headers(somebody_else)
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert problem_of(response)["detail"] == NOT_FOUND_SENTENCE
        assert answered(booking.read(world.customer, draft["id"]))["status"] == "DRAFT"

    def test_every_lookup_of_the_reservation_carries_the_owner(
        self,
        booking: BookingClient,
        world: BookingWorld,
        somebody_else: UserAccount,
        sqlite_engine: Engine,
    ) -> None:
        draft = booking.drafted(world)
        headers = booking.headers(somebody_else)
        path = reservation_path(draft["id"])
        with recorded_statements(sqlite_engine) as statements:
            booking.client.get(path, headers=headers)
        # The sweep reads the reservation table as well, by expiry and never by key.
        lookups = [sql for sql in statements if "reservation.id =" in sql]
        assert len(lookups) == 1
        assert "JOIN customer_profile" in lookups[0]
        assert "customer_profile.user_account_id" in lookups[0]

    @pytest.mark.parametrize("role", [UserRole.COUNTER_STAFF, UserRole.ADMIN])
    def test_staff_read_any_customers_reservation_at_any_branch(
        self,
        booking: BookingClient,
        session: Session,
        factory: Factory,
        world: BookingWorld,
        role: UserRole,
    ) -> None:
        branch = factory.branch() if role is UserRole.COUNTER_STAFF else None
        member_of_staff = factory.user(role=role, branch=branch)
        session.commit()
        draft = booking.drafted(world)
        assert answered(booking.read(member_of_staff, draft["id"]))["id"] == draft["id"]

    def test_an_anonymous_caller_is_401_before_any_reservation_is_looked_up(
        self, booking: BookingClient, world: BookingWorld
    ) -> None:
        draft = booking.drafted(world)
        response = booking.client.get(reservation_path(draft["id"]))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestListingReservations:
    """GET /api/reservations, newest first, the caller's own unless they are staff."""

    def test_a_list_has_the_shape_of_the_contract(
        self, booking: BookingClient, world: BookingWorld
    ) -> None:
        draft = booking.drafted(world)
        body = answered(booking.listing(world.customer))
        assert body.keys() == PAGE_MEMBERS
        assert body["items"] == [draft]
        assert (body["page"], body["pageSize"], body["total"]) == (1, DEFAULT_PAGE_SIZE, 1)

    def test_a_customer_with_no_reservations_gets_an_empty_page(
        self, booking: BookingClient, world: BookingWorld
    ) -> None:
        body = answered(booking.listing(world.customer))
        assert (body["items"], body["total"]) == ([], 0)

    def test_the_newest_reservation_comes_first(
        self, booking: BookingClient, world: BookingWorld
    ) -> None:
        references = [str(booking.drafted(world)["reference"]) for _ in range(3)]
        assert references_in(answered(booking.listing(world.customer))) == references[::-1]

    def test_a_customer_does_not_see_anybody_elses(
        self, booking: BookingClient, world: BookingWorld, somebody_else: UserAccount
    ) -> None:
        booking.drafted(world)
        assert answered(booking.listing(somebody_else))["total"] == 0

    def test_a_list_can_be_narrowed_to_one_status(
        self, booking: BookingClient, world: BookingWorld
    ) -> None:
        booking.drafted(world)
        held = booking.held(world)
        body = answered(booking.listing(world.customer, status="HELD"))
        assert references_in(body) == [held["reference"]]

    def test_a_list_is_paged(self, booking: BookingClient, world: BookingWorld) -> None:
        references = [str(booking.drafted(world)["reference"]) for _ in range(5)]
        body = answered(booking.listing(world.customer, page=2, pageSize=2))
        assert references_in(body) == [references[2], references[1]]
        assert (body["page"], body["pageSize"], body["total"]) == (2, 2, 5)

    def test_staff_see_everybodys_and_may_narrow_to_one_customer_or_one_branch(
        self,
        booking: BookingClient,
        session: Session,
        factory: Factory,
        world: BookingWorld,
    ) -> None:
        elsewhere = build_booking_world(factory)
        administrator = factory.user(role=UserRole.ADMIN)
        session.commit()
        here = booking.drafted(world)
        there = booking.drafted(elsewhere)

        everything = answered(booking.listing(administrator))
        one_customer = answered(
            booking.listing(administrator, customerProfileId=str(elsewhere.profile.id))
        )
        one_branch = answered(booking.listing(administrator, branch=world.branch.code))

        assert everything["total"] == 2
        assert references_in(one_customer) == [there["reference"]]
        assert references_in(one_branch) == [here["reference"]]

    @pytest.mark.parametrize("filter_name", ["customerProfileId", "branch"])
    def test_a_customer_who_narrows_to_a_customer_or_a_branch_is_refused_with_403(
        self, booking: BookingClient, world: BookingWorld, filter_name: str
    ) -> None:
        value = str(world.profile.id) if filter_name == "customerProfileId" else world.branch.code
        response = booking.listing(world.customer, **{filter_name: value})
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert problem_code(response) == AUTHORISATION_PROBLEM

    @pytest.mark.parametrize(
        ("params", "field", "sentence"),
        [
            ({"status": "PENDING"}, "query.status", "Choose one of the options offered."),
            ({"page": 0}, "query.page", "Enter 1 or more."),
            ({"pageSize": 51}, "query.pageSize", "Enter 50 or less."),
            ({"pageSize": 0}, "query.pageSize", "Enter 1 or more."),
        ],
    )
    def test_a_refused_query_parameter_is_named_in_a_plain_sentence(
        self,
        booking: BookingClient,
        world: BookingWorld,
        params: dict[str, object],
        field: str,
        sentence: str,
    ) -> None:
        response = booking.listing(world.customer, **params)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert problem_code(response) == VALIDATION_PROBLEM
        assert problem_of(response)["errors"] == {"fields": {field: sentence}}

    def test_an_unknown_branch_code_from_staff_names_the_branch(
        self, booking: BookingClient, session: Session, factory: Factory, world: BookingWorld
    ) -> None:
        administrator = factory.user(role=UserRole.ADMIN)
        session.commit()
        response = booking.listing(administrator, branch="XYZ")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert problem_of(response)["errors"] == {
            "fields": {
                "query.branch": (
                    "We do not have a branch with that code. Choose a branch from the list."
                )
            }
        }
