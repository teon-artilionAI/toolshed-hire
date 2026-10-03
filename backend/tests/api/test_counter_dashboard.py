"""The counter's dashboard, through HTTP (FR-16, US-18, BR-43).

A counter assistant opens the dashboard and sees what is due today at their
branch. These pin the shape of the answer, what lands in each list and each
count, the late fee an overdue hire has run up, which branch each caller is
shown, and that reading it runs the sweep first.

These run against the in memory database. The clock stands still on Monday
the second of March 2026 at ten in the morning in Cape Town, and a hire booked
for today is due back on Thursday the fifth.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

import pytest
from fastapi import status
from sqlmodel import Session

from app.domain.enums import AssetStatus, UserRole
from app.infrastructure.models import UserAccount
from tests.support.booking_api import BookingClient, BookingWorld, answered, build_booking_world
from tests.support.checkout_api import checked_out, confirmed_today
from tests.support.counter_api import (
    AFTER_CLOSING,
    COLLECTION_DUE_MEMBERS,
    COUNTS_MEMBERS,
    DASHBOARD_MEMBERS,
    OVERDUE_MEMBERS,
    RETURN_DUE_MEMBERS,
    read_dashboard,
)
from tests.support.factories import Factory
from tests.support.http import problem_code, problem_of

UNITS: Final[int] = 4
# Thursday the fifth, the day a hire booked for today is due back, and two
# days after it, both at ten in the morning in Cape Town.
DUE_DAY: Final[datetime] = datetime(2026, 3, 5, 8, 0, tzinfo=UTC)
TWO_DAYS_LATE: Final[datetime] = datetime(2026, 3, 7, 8, 0, tzinfo=UTC)
NO_COUNTS: Final[dict[str, int]] = {
    "collectionsDue": 0,
    "returnsDue": 0,
    "overdue": 0,
    "onHire": 0,
    "quarantined": 0,
}


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world whose branch holds four units."""
    built = build_booking_world(factory, asset_count=UNITS)
    session.commit()
    return built


@pytest.fixture
def assistant(session: Session, factory: Factory, world: BookingWorld) -> UserAccount:
    """Return a committed counter assistant of the world's branch."""
    account = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    session.commit()
    return account


@pytest.fixture
def administrator(session: Session, factory: Factory) -> UserAccount:
    """Return a committed administrator, who belongs to no branch."""
    account = factory.user(role=UserRole.ADMIN)
    session.commit()
    return account


class TestTheShape:
    """The members the contract gives the dashboard, and nothing else."""

    def test_an_empty_day_has_every_member_and_counts_nothing(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        dashboard = answered(read_dashboard(booking, assistant))
        assert dashboard.keys() == DASHBOARD_MEMBERS
        assert (dashboard["branchCode"], dashboard["branchName"]) == (
            world.branch.code,
            world.branch.name,
        )
        assert dashboard["date"] == "2026-03-02"
        assert dashboard["counts"].keys() == COUNTS_MEMBERS
        assert dashboard["counts"] == NO_COUNTS
        assert (dashboard["collectionsDue"], dashboard["returnsDue"], dashboard["overdue"]) == (
            [],
            [],
            [],
        )

    def test_a_collection_due_today_has_the_shape_of_the_contract(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        reservation = confirmed_today(booking, world, assistant, quantity=2)
        (collection,) = answered(read_dashboard(booking, assistant))["collectionsDue"]
        assert collection.keys() == COLLECTION_DUE_MEMBERS
        assert (collection["reservationId"], collection["reference"]) == (
            reservation["id"],
            reservation["reference"],
        )
        assert (collection["customerName"], collection["customerPhone"]) == (
            world.profile.display_name,
            world.profile.contact_phone,
        )
        assert (collection["from"], collection["to"]) == ("2026-03-02", "2026-03-05")
        assert collection["unitCount"] == 2
        assert collection["summary"] == f"2 x {world.product_model.name}"


class TestWhatIsDue:
    """Collections, returns and overdue hires, each with the true count beside it."""

    def test_a_hire_out_today_is_counted_on_hire_and_is_not_yet_due_back(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        confirmed_today(booking, world, assistant)
        checked_out(booking, assistant, confirmed_today(booking, world, assistant)["id"])
        dashboard = answered(read_dashboard(booking, assistant))
        assert dashboard["counts"] == {**NO_COUNTS, "collectionsDue": 1, "onHire": 1}
        assert dashboard["returnsDue"] == []

    def test_a_hire_due_back_today_is_a_return_with_what_is_still_out(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        rental = checked_out(booking, assistant, confirmed_today(booking, world, assistant)["id"])
        booking.clock.instant = DUE_DAY

        dashboard = answered(read_dashboard(booking, assistant))

        assert dashboard["date"] == "2026-03-05"
        assert dashboard["counts"]["returnsDue"] == 1
        (returning,) = dashboard["returnsDue"]
        assert returning.keys() == RETURN_DUE_MEMBERS
        assert (returning["rentalId"], returning["reference"]) == (
            rental["id"],
            rental["reference"],
        )
        assert returning["dueBackOn"] == "2026-03-05"
        assert (returning["itemsOut"], returning["itemCount"]) == (1, 1)
        assert returning["summary"] == f"1 x {world.product_model.name}"

    def test_an_overdue_hire_says_how_late_it_is_and_what_it_has_run_up(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        rental = checked_out(booking, assistant, confirmed_today(booking, world, assistant)["id"])
        booking.clock.instant = TWO_DAYS_LATE

        dashboard = answered(read_dashboard(booking, assistant))

        assert dashboard["counts"]["overdue"] == 1
        (overdue,) = dashboard["overdue"]
        assert overdue.keys() == OVERDUE_MEMBERS
        assert overdue["rentalId"] == rental["id"]
        assert (overdue["dueBackOn"], overdue["daysOverdue"]) == ("2026-03-05", 2)
        assert (overdue["itemsOut"], overdue["lateFeeAccrued"]) == (1, "240.00")

    def test_a_unit_in_quarantine_is_counted(
        self,
        booking: BookingClient,
        session: Session,
        world: BookingWorld,
        assistant: UserAccount,
    ) -> None:
        unit = world.assets[0]
        unit.status = AssetStatus.QUARANTINED
        session.add(unit)
        session.commit()
        assert answered(read_dashboard(booking, assistant))["counts"]["quarantined"] == 1

    def test_another_branch_is_not_counted(
        self,
        booking: BookingClient,
        factory: Factory,
        session: Session,
        world: BookingWorld,
        assistant: UserAccount,
    ) -> None:
        elsewhere = build_booking_world(factory)
        session.commit()
        other_assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=elsewhere.branch)
        session.commit()
        confirmed_today(booking, elsewhere, other_assistant)
        assert answered(read_dashboard(booking, assistant))["counts"] == NO_COUNTS


class TestReadingRunsTheSweepFirst:
    """A booking nobody collected by closing time is never shown as due."""

    def test_after_closing_a_booking_for_today_is_a_no_show_and_not_a_collection(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        reservation = confirmed_today(booking, world, assistant)
        booking.clock.instant = AFTER_CLOSING

        dashboard = answered(read_dashboard(booking, assistant))

        assert dashboard["collectionsDue"] == []
        assert dashboard["counts"]["collectionsDue"] == 0
        assert answered(booking.read(assistant, reservation["id"]))["status"] == "NO_SHOW"


class TestWhichBranchIsShown:
    """Counter staff see their own branch. An administrator names one (BR-43)."""

    def test_counter_staff_may_name_their_own_branch(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        dashboard = answered(read_dashboard(booking, assistant, branchCode=world.branch.code))
        assert dashboard["branchCode"] == world.branch.code

    def test_counter_staff_who_name_another_branch_are_refused(
        self,
        booking: BookingClient,
        factory: Factory,
        session: Session,
        assistant: UserAccount,
    ) -> None:
        elsewhere = factory.branch(name="Bellville")
        session.commit()
        response = read_dashboard(booking, assistant, branchCode=elsewhere.code)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert problem_code(response) == "branch-scope"
        assert problem_of(response)["detail"] == (
            "Counter staff can only open the dashboard and the diary of their own branch."
        )

    def test_an_administrator_sees_the_branch_named(
        self, booking: BookingClient, world: BookingWorld, administrator: UserAccount
    ) -> None:
        dashboard = answered(read_dashboard(booking, administrator, branchCode=world.branch.code))
        assert dashboard["branchName"] == world.branch.name

    def test_an_administrator_who_names_no_branch_is_told_to_choose_one(
        self, booking: BookingClient, administrator: UserAccount
    ) -> None:
        response = read_dashboard(booking, administrator)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert problem_of(response)["errors"] == {
            "fields": {"query.branchCode": "Choose the branch to show."}
        }

    def test_an_administrator_who_names_a_branch_that_does_not_trade_is_refused(
        self, booking: BookingClient, administrator: UserAccount
    ) -> None:
        response = read_dashboard(booking, administrator, branchCode="ZZZ")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "query.branchCode" in problem_of(response)["errors"]["fields"]

    def test_a_customer_is_refused(self, booking: BookingClient, world: BookingWorld) -> None:
        response = read_dashboard(booking, world.customer)
        assert response.status_code == status.HTTP_403_FORBIDDEN
