"""The asset locator, through HTTP (FR-15, US-10, BR-43).

A counter assistant types part of a tag or of a model name and sees where every
matching unit is, at every branch. These pin the shape of the answer, what a
search matches, the order and the pages, the day a unit on hire is due back,
and the bounds on the text and the page.

These run against the in memory database, and the clock stands still on Monday
the second of March 2026.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pytest
from fastapi import status
from sqlmodel import Session

from app.domain.enums import AssetStatus, UserRole
from app.infrastructure.models import Branch, UserAccount
from tests.support.booking_api import BookingClient, answered, build_booking_world
from tests.support.checkout_api import checked_out, confirmed_today
from tests.support.counter_api import LOCATION_MEMBERS, PAGE_MEMBERS, locate
from tests.support.factories import Factory
from tests.support.http import problem_of

HAMMER: Final[str] = "GBH 2-26 DRE Rotary Hammer"
MIXER: Final[str] = "Concrete Mixer 140L"
CBD_HAMMER: Final[str] = "TSH-DR-0001"
BLV_HAMMER: Final[str] = "TSH-DR-0002"
CBD_MIXER: Final[str] = "TSH-MX-0001"
TOO_LONG: Final[int] = 81


@dataclass(frozen=True, slots=True)
class Fleet:
    """Two branches, a hammer at each and a mixer in quarantine at the first, and two callers."""

    cbd: Branch
    blv: Branch
    assistant: UserAccount
    administrator: UserAccount


@pytest.fixture
def fleet(session: Session, factory: Factory) -> Fleet:
    """Return a committed fleet of three units across two branches."""
    cbd = factory.branch(name="Cape Town CBD")
    blv = factory.branch(name="Bellville")
    hammer = factory.product_model(name=HAMMER)
    mixer = factory.product_model(name=MIXER)
    factory.asset(product_model=hammer, branch=cbd, asset_tag=CBD_HAMMER)
    factory.asset(product_model=hammer, branch=blv, asset_tag=BLV_HAMMER)
    factory.asset(
        product_model=mixer, branch=cbd, asset_tag=CBD_MIXER, status=AssetStatus.QUARANTINED
    )
    assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=cbd)
    administrator = factory.user(role=UserRole.ADMIN)
    session.commit()
    return Fleet(cbd=cbd, blv=blv, assistant=assistant, administrator=administrator)


def tags_of(page: dict[str, object]) -> list[str]:
    """Return the tags of the units on a page, in the order they came."""
    items = page["items"]
    assert isinstance(items, list)
    return [item["assetTag"] for item in items]


class TestWhatASearchFinds:
    """Part of a tag or of a model name, at every branch, in tag order."""

    def test_a_unit_has_the_shape_of_the_contract(
        self, booking: BookingClient, fleet: Fleet
    ) -> None:
        page = answered(locate(booking, fleet.assistant, q=BLV_HAMMER))
        assert page.keys() == PAGE_MEMBERS
        (unit,) = page["items"]
        assert unit.keys() == LOCATION_MEMBERS
        assert (unit["assetTag"], unit["modelName"]) == (BLV_HAMMER, HAMMER)
        assert unit["categoryName"] == "Drilling and Demolition"
        assert (unit["branchCode"], unit["branchName"]) == (fleet.blv.code, fleet.blv.name)
        assert (unit["status"], unit["conditionGrade"]) == ("AVAILABLE", "A")
        assert (unit["dueBackOn"], unit["rentalReference"]) == (None, None)

    def test_part_of_a_tag_finds_the_units_at_every_branch(
        self, booking: BookingClient, fleet: Fleet
    ) -> None:
        page = answered(locate(booking, fleet.assistant, q="dr-000"))
        assert tags_of(page) == [CBD_HAMMER, BLV_HAMMER]
        assert page["total"] == 2

    def test_part_of_a_model_name_finds_its_units_whatever_their_status(
        self, booking: BookingClient, fleet: Fleet
    ) -> None:
        page = answered(locate(booking, fleet.assistant, q="mixer"))
        assert tags_of(page) == [CBD_MIXER]
        assert page["items"][0]["status"] == "QUARANTINED"

    def test_a_unit_matched_by_its_tag_and_its_model_is_listed_once(
        self, booking: BookingClient, fleet: Fleet
    ) -> None:
        """`DR` is in the tag of each hammer and in the name of its model, `GBH 2-26 DRE`."""
        page = answered(locate(booking, fleet.assistant, q="dr"))
        assert tags_of(page) == [CBD_HAMMER, BLV_HAMMER]
        assert page["total"] == 2

    def test_an_administrator_sees_the_same_units(
        self, booking: BookingClient, fleet: Fleet
    ) -> None:
        assert tags_of(answered(locate(booking, fleet.administrator, q="TSH"))) == [
            CBD_HAMMER,
            BLV_HAMMER,
            CBD_MIXER,
        ]

    def test_the_like_wildcards_match_nothing(self, booking: BookingClient, fleet: Fleet) -> None:
        page = answered(locate(booking, fleet.assistant, q="%%"))
        assert (page["items"], page["total"]) == ([], 0)

    def test_a_customer_is_refused(
        self, booking: BookingClient, factory: Factory, session: Session, fleet: Fleet
    ) -> None:
        customer = factory.user(role=UserRole.CUSTOMER)
        session.commit()
        assert locate(booking, customer, q="TSH").status_code == status.HTTP_403_FORBIDDEN


class TestPaging:
    """A page holds what was asked for, and the total counts every match."""

    def test_the_second_page_of_two_holds_the_third_unit(
        self, booking: BookingClient, fleet: Fleet
    ) -> None:
        page = answered(locate(booking, fleet.assistant, q="TSH", page=2, pageSize=2))
        assert tags_of(page) == [CBD_MIXER]
        assert (page["page"], page["pageSize"], page["total"]) == (2, 2, 3)


class TestAUnitOnHire:
    """A unit out on a hire says when it is due back and which rental it is on."""

    def test_the_due_day_and_the_rental_are_given_while_it_is_out(
        self, booking: BookingClient, session: Session, factory: Factory
    ) -> None:
        world = build_booking_world(factory)
        assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
        session.commit()
        tag = world.assets[0].asset_tag
        rental = checked_out(booking, assistant, confirmed_today(booking, world, assistant)["id"])

        (unit,) = answered(locate(booking, assistant, q=tag))["items"]

        assert (unit["status"], unit["dueBackOn"]) == ("ON_HIRE", "2026-03-05")
        assert unit["rentalReference"] == rental["reference"]


class TestTheBounds:
    """Two to eighty characters, and a page of one to fifty."""

    @pytest.mark.parametrize(
        "params",
        [
            {"q": "x"},
            {"q": "  x  "},
            {"q": "x" * TOO_LONG},
            {},
        ],
        ids=["one character", "one character in spaces", "eighty one characters", "no text"],
    )
    def test_a_text_outside_the_bounds_is_refused_by_name(
        self, booking: BookingClient, fleet: Fleet, params: dict[str, object]
    ) -> None:
        response = locate(booking, fleet.assistant, **params)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert set(problem_of(response)["errors"]["fields"]) == {"query.q"}

    @pytest.mark.parametrize(
        ("params", "field"),
        [
            ({"q": "TSH", "pageSize": 51}, "query.pageSize"),
            ({"q": "TSH", "pageSize": 0}, "query.pageSize"),
            ({"q": "TSH", "page": 0}, "query.page"),
        ],
    )
    def test_a_page_outside_the_bounds_is_refused_by_name(
        self, booking: BookingClient, fleet: Fleet, params: dict[str, object], field: str
    ) -> None:
        response = locate(booking, fleet.assistant, **params)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert set(problem_of(response)["errors"]["fields"]) == {field}
