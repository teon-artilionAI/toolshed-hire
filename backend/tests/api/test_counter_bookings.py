"""Booking at the counter through the one reservation path, through HTTP (FR-14, US-21).

There is no second path for a counter booking. Staff use the reservation
routes a customer uses, name the customer, book at their own branch and may
book for today. A confirmation by staff satisfies the verified email rule
(BR-47). Staff see the tags of the units a line holds and a customer never
does. Staff narrow a list by customer, by branch and by status.

A customer's own list leaves out the baskets they abandoned. A reservation
cancelled without ever holding a unit is a draft that was replaced or thrown
away, not a cancelled booking.

These run against the in memory database, and the clock stands still on
Monday the second of March 2026.
"""

from __future__ import annotations

from typing import Final

import pytest
from fastapi import status
from sqlmodel import Session

from app.domain.enums import UserRole
from app.infrastructure.models import UserAccount
from tests.support.booking_api import (
    BookingClient,
    BookingWorld,
    answered,
    build_booking_world,
    created,
)
from tests.support.checkout_api import TODAY_HIRE, confirmed_today
from tests.support.factories import Factory
from tests.support.http import problem_code, problem_of

UNKNOWN_BRANCH: Final[str] = (
    "We do not have a branch with that code. Choose a branch from the list."
)
CHOOSE_THE_CUSTOMER: Final[str] = "Choose the customer this reservation is for."


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world whose branch holds three units."""
    built = build_booking_world(factory, asset_count=3, email_verified=False)
    session.commit()
    return built


@pytest.fixture
def assistant(session: Session, factory: Factory, world: BookingWorld) -> UserAccount:
    """Return a committed counter assistant of the world's branch."""
    account = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    session.commit()
    return account


def references_in(body: dict[str, object]) -> list[str]:
    """Return the references on a page, in the order they were returned."""
    items = body["items"]
    assert isinstance(items, list)
    return [str(item["reference"]) for item in items]


class TestBookingAtTheCounter:
    """The customer's reservation path, used by staff on the customer's behalf."""

    def test_staff_have_to_name_the_customer(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        response = booking.create(assistant, world.payload(TODAY_HIRE))
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert problem_of(response)["errors"] == {
            "fields": {"body.customerProfileId": CHOOSE_THE_CUSTOMER}
        }

    def test_staff_book_for_today_and_confirm_for_a_customer_whose_address_is_unproved(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        confirmed = confirmed_today(booking, world, assistant)
        assert (confirmed["status"], confirmed["from"]) == ("CONFIRMED", "2026-03-02")

    def test_the_same_customer_could_not_confirm_it_themselves(
        self, booking: BookingClient, world: BookingWorld
    ) -> None:
        draft = created(booking.create(world.customer, world.payload(TODAY_HIRE)))
        held = answered(booking.hold(world.customer, draft["id"]))
        assert held["canConfirm"] is False
        response = booking.confirm(world.customer, draft["id"])
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert problem_code(response) == "email-not-verified"

    def test_counter_staff_cannot_book_at_another_branch(
        self, booking: BookingClient, session: Session, factory: Factory, world: BookingWorld
    ) -> None:
        elsewhere = factory.user(role=UserRole.COUNTER_STAFF, branch=factory.branch())
        session.commit()
        response = booking.create(
            elsewhere, world.payload(TODAY_HIRE, customer_profile_id=world.profile.id)
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert problem_code(response) == "branch-scope"


class TestWhoSeesTheTags:
    """Staff see which units a line holds. A customer never does (US-07)."""

    def test_staff_see_the_tags_and_the_customer_reads_an_empty_list(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        confirmed = confirmed_today(booking, world, assistant, quantity=2)
        staff_line = answered(booking.read(assistant, confirmed["id"]))["lines"][0]
        customer_line = answered(booking.read(world.customer, confirmed["id"]))["lines"][0]
        assert staff_line["assetTags"] == sorted(asset.asset_tag for asset in world.assets[:2])
        assert customer_line["assetTags"] == []
        assert customer_line["allocatedCount"] == staff_line["allocatedCount"] == 2

    def test_no_tag_reaches_the_customers_list_either(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        confirm = confirmed_today(booking, world, assistant)
        response = booking.listing(world.customer)
        assert answered(response)["items"][0]["id"] == confirm["id"]
        assert not any(asset.asset_tag in response.text for asset in world.assets)


class TestTheStaffList:
    """Staff list every branch and narrow by customer, branch and status."""

    def test_staff_narrow_by_branch_code_customer_and_status(
        self, booking: BookingClient, session: Session, factory: Factory, world: BookingWorld,
        assistant: UserAccount,
    ) -> None:
        elsewhere = build_booking_world(factory)
        administrator = factory.user(role=UserRole.ADMIN)
        session.commit()
        here = confirmed_today(booking, world, assistant)
        draft_here = booking.drafted(world)
        there = created(
            booking.create(
                administrator, elsewhere.payload(customer_profile_id=elsewhere.profile.id)
            )
        )

        assert answered(booking.listing(assistant))["total"] == 3
        by_branch = answered(booking.listing(assistant, branchCode=world.branch.code))
        assert references_in(by_branch) == [draft_here["reference"], here["reference"]]
        by_customer = answered(
            booking.listing(assistant, customerProfileId=str(elsewhere.profile.id))
        )
        assert references_in(by_customer) == [there["reference"]]
        by_status = answered(
            booking.listing(assistant, branchCode=world.branch.code, status="CONFIRMED")
        )
        assert references_in(by_status) == [here["reference"]]

    def test_the_earlier_name_of_the_branch_filter_still_works(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        here = confirmed_today(booking, world, assistant)
        body = answered(booking.listing(assistant, branch=world.branch.code))
        assert references_in(body) == [here["reference"]]

    @pytest.mark.parametrize("parameter", ["branchCode", "branch"])
    def test_an_unknown_branch_is_refused_under_the_name_it_was_sent_by(
        self, booking: BookingClient, assistant: UserAccount, parameter: str
    ) -> None:
        response = booking.listing(assistant, **{parameter: "XYZ"})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert problem_of(response)["errors"] == {"fields": {f"query.{parameter}": UNKNOWN_BRANCH}}

    def test_a_customer_who_names_a_branch_code_is_refused_with_403(
        self, booking: BookingClient, world: BookingWorld
    ) -> None:
        response = booking.listing(world.customer, branchCode=world.branch.code)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert problem_code(response) == "authorisation-failure"


class TestAbandonedBaskets:
    """A draft cancelled before it held a unit is not a cancelled booking."""

    def test_a_replaced_basket_is_left_out_of_the_customers_list(
        self, booking: BookingClient, world: BookingWorld
    ) -> None:
        replaced = booking.drafted(world)
        answered(booking.cancel(world.customer, replaced["id"]))
        changed = booking.drafted(world, quantity=2)
        body = answered(booking.listing(world.customer))
        assert references_in(body) == [changed["reference"]]
        assert body["total"] == 1

    def test_a_booking_cancelled_after_it_held_units_stays_in_the_list(
        self, booking: BookingClient, world: BookingWorld
    ) -> None:
        held = booking.held(world)
        answered(booking.cancel(world.customer, held["id"]))
        body = answered(booking.listing(world.customer, status="CANCELLED"))
        assert references_in(body) == [held["reference"]]

    def test_the_abandoned_basket_is_still_read_by_its_key_and_staff_still_list_it(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        abandoned = booking.drafted(world)
        answered(booking.cancel(world.customer, abandoned["id"]))
        assert answered(booking.read(world.customer, abandoned["id"]))["status"] == "CANCELLED"
        staff_list = answered(booking.listing(assistant, customerProfileId=str(world.profile.id)))
        assert references_in(staff_list) == [abandoned["reference"]]

    def test_a_page_of_the_customers_list_is_full_and_its_total_agrees(
        self, booking: BookingClient, world: BookingWorld
    ) -> None:
        kept = [booking.drafted(world)["reference"] for _ in range(2)]
        for _ in range(2):
            answered(booking.cancel(world.customer, booking.drafted(world)["id"]))
        body = answered(booking.listing(world.customer, page=1, pageSize=2))
        assert references_in(body) == kept[::-1]
        assert body["total"] == 2
