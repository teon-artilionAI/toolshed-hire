"""The branch diary, through HTTP (FR-16, US-19, BR-43).

The counter opens the diary of their branch for one to seven days from any
date. These pin the shape of the answer, which reservations count as
collections and which rentals as returns, when the diary offers to mark a
collection as not collected, the limits on the run of days, which branch each
caller is shown, and that reading it runs the sweep first.

These run against the in memory database. The clock stands still on Monday
the second of March 2026 at ten in the morning in Cape Town.
"""

from __future__ import annotations

from typing import Final

import pytest
from fastapi import status
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
from tests.support.checkout_api import TODAY_HIRE, checked_out, confirmed_today
from tests.support.counter_api import (
    AFTER_CLOSING,
    DIARY_COLLECTION_MEMBERS,
    DIARY_DAY_MEMBERS,
    DIARY_MEMBERS,
    DIARY_RETURN_MEMBERS,
    mark_no_show,
    read_diary,
)
from tests.support.factories import Factory
from tests.support.http import problem_code, problem_of

UNITS: Final[int] = 5
NOT_ACCEPTED: Final[str] = "Some of the details were not accepted. Check each one and try again."


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world whose branch holds five units."""
    built = build_booking_world(factory, asset_count=UNITS)
    session.commit()
    return built


@pytest.fixture
def assistant(session: Session, factory: Factory, world: BookingWorld) -> UserAccount:
    """Return a committed counter assistant of the world's branch."""
    account = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
    session.commit()
    return account


def collections_of(diary: dict[str, object]) -> dict[str, dict[str, object]]:
    """Return the collections of the first day of a diary, by reservation key."""
    days = diary["days"]
    assert isinstance(days, list)
    return {collection["reservationId"]: collection for collection in days[0]["collections"]}


class TestTheShape:
    """The members the contract gives the diary, and one entry for each day."""

    def test_today_is_shown_when_nothing_else_is_asked(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        diary = answered(read_diary(booking, assistant))
        assert diary.keys() == DIARY_MEMBERS
        assert (diary["branchCode"], diary["branchName"]) == (world.branch.code, world.branch.name)
        (day,) = diary["days"]
        assert day == {"date": "2026-03-02", "collections": [], "returns": []}
        assert day.keys() == DIARY_DAY_MEMBERS

    def test_a_run_of_days_has_one_entry_for_each_day_in_order(
        self, booking: BookingClient, assistant: UserAccount
    ) -> None:
        diary = answered(read_diary(booking, assistant, **{"from": "2026-02-27", "days": 3}))
        assert [day["date"] for day in diary["days"]] == [
            "2026-02-27",
            "2026-02-28",
            "2026-03-01",
        ]

    def test_a_collection_and_a_return_have_the_shape_of_the_contract(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        reservation = confirmed_today(booking, world, assistant, quantity=2)
        rental = checked_out(booking, assistant, reservation["id"])

        today = answered(read_diary(booking, assistant))["days"][0]
        due_back = answered(read_diary(booking, assistant, **{"from": "2026-03-05"}))["days"][0]

        (collection,) = today["collections"]
        assert collection.keys() == DIARY_COLLECTION_MEMBERS
        assert (collection["reservationId"], collection["status"]) == (
            reservation["id"],
            "COLLECTED",
        )
        assert (collection["from"], collection["to"], collection["unitCount"]) == (
            "2026-03-02",
            "2026-03-05",
            2,
        )
        assert collection["summary"] == f"2 x {world.product_model.name}"
        (returning,) = due_back["returns"]
        assert returning.keys() == DIARY_RETURN_MEMBERS
        assert (returning["rentalId"], returning["status"]) == (rental["id"], "OPEN")
        assert (returning["itemsOut"], returning["itemCount"]) == (2, 2)
        assert returning["customerName"] == world.profile.display_name


class TestWhatTheDiaryLists:
    """Collections in four statuses, and the no show button by the rule of the route."""

    def test_a_held_and_a_cancelled_booking_are_not_collections(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        payload = world.payload(TODAY_HIRE, customer_profile_id=world.profile.id)
        held = created(booking.create(assistant, payload))
        answered(booking.hold(assistant, held["id"]))
        cancelled = confirmed_today(booking, world, assistant)
        answered(booking.cancel(assistant, cancelled["id"]))
        assert answered(read_diary(booking, assistant))["days"][0]["collections"] == []

    def test_the_button_is_offered_on_a_confirmed_booking_for_today_and_nowhere_else(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        waiting = confirmed_today(booking, world, assistant)
        collected = confirmed_today(booking, world, assistant)
        checked_out(booking, assistant, collected["id"])
        missed = confirmed_today(booking, world, assistant)
        answered(mark_no_show(booking, assistant, missed["id"]))

        collections = collections_of(answered(read_diary(booking, assistant)))

        assert {key: entry["status"] for key, entry in collections.items()} == {
            waiting["id"]: "CONFIRMED",
            collected["id"]: "COLLECTED",
            missed["id"]: "NO_SHOW",
        }
        assert {key: entry["canMarkNoShow"] for key, entry in collections.items()} == {
            waiting["id"]: True,
            collected["id"]: False,
            missed["id"]: False,
        }

    def test_the_button_is_not_offered_before_the_first_day_of_the_hire(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        next_week = confirmed_today(booking, world, assistant, period=FIRST_HIRE)
        diary = answered(read_diary(booking, assistant, **{"from": "2026-03-09"}))
        (collection,) = diary["days"][0]["collections"]
        assert (collection["reservationId"], collection["status"]) == (
            next_week["id"],
            "CONFIRMED",
        )
        assert collection["canMarkNoShow"] is False

    def test_reading_after_closing_shows_a_booking_nobody_collected_as_a_no_show(
        self, booking: BookingClient, world: BookingWorld, assistant: UserAccount
    ) -> None:
        missed = confirmed_today(booking, world, assistant)
        booking.clock.instant = AFTER_CLOSING
        (collection,) = answered(read_diary(booking, assistant))["days"][0]["collections"]
        assert (collection["reservationId"], collection["status"]) == (missed["id"], "NO_SHOW")
        assert collection["canMarkNoShow"] is False


class TestTheLimitsOfTheRun:
    """One to seven days, and a date that is a date."""

    @pytest.mark.parametrize("days", [0, 8, -1], ids=["none", "eight", "fewer than none"])
    def test_a_run_outside_one_to_seven_days_is_refused_by_name(
        self, booking: BookingClient, assistant: UserAccount, days: int
    ) -> None:
        response = read_diary(booking, assistant, days=days)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        body = problem_of(response)
        assert body["detail"] == NOT_ACCEPTED
        assert set(body["errors"]["fields"]) == {"query.days"}

    def test_seven_days_are_allowed(self, booking: BookingClient, assistant: UserAccount) -> None:
        assert len(answered(read_diary(booking, assistant, days=7))["days"]) == 7

    @pytest.mark.parametrize("first_day", ["tomorrow", "2026-02-30"])
    def test_a_from_that_is_not_a_date_is_refused_by_name(
        self, booking: BookingClient, assistant: UserAccount, first_day: str
    ) -> None:
        response = read_diary(booking, assistant, **{"from": first_day})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert set(problem_of(response)["errors"]["fields"]) == {"query.from"}

    def test_a_run_that_would_end_past_the_last_date_there_is_is_refused(
        self, booking: BookingClient, assistant: UserAccount
    ) -> None:
        response = read_diary(booking, assistant, **{"from": "9999-12-30", "days": 3})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert set(problem_of(response)["errors"]["fields"]) == {"query.from"}


class TestWhichBranchIsShown:
    """The same rule as the dashboard (BR-43)."""

    def test_counter_staff_who_name_another_branch_are_refused(
        self, booking: BookingClient, factory: Factory, session: Session, assistant: UserAccount
    ) -> None:
        elsewhere = factory.branch(name="Somerset West")
        session.commit()
        response = read_diary(booking, assistant, branchCode=elsewhere.code)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert problem_code(response) == "branch-scope"

    def test_an_administrator_names_the_branch(
        self, booking: BookingClient, factory: Factory, session: Session, world: BookingWorld
    ) -> None:
        administrator = factory.user(role=UserRole.ADMIN)
        session.commit()
        missing = read_diary(booking, administrator)
        assert missing.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert set(problem_of(missing)["errors"]["fields"]) == {"query.branchCode"}
        named = answered(read_diary(booking, administrator, branchCode=world.branch.code))
        assert named["branchCode"] == world.branch.code
