"""Where a machine is free, answered by real PostgreSQL.

FR-03 and FR-04. A unit is free for a period when its status is `AVAILABLE` and
it holds no active allocation whose half open period overlaps the one asked
about (BR-10). The statement that decides it uses `daterange` and the overlap
operator, the same expression the exclusion constraint is built on, so none of
this can be proved on SQLite.

The first class is the acceptance case of US-07 as the design document writes
it. One trench rammer at Bellville is allocated from the third to the fifth of
March, another at Somerset West is free, and a search for the fourth to the
sixth says free at Somerset West and not free at Bellville, with no tag and no
count anywhere in the answer.

Every request goes through HTTP with no credential, on a clock that stands
still on the second of March 2026.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.domain.enums import AssetStatus
from app.domain.period import BookingPeriod
from app.infrastructure.models import Asset, Branch, ProductModel
from tests.support.catalogue import (
    AVAILABILITY_PATH,
    a_model,
    hold_unit,
    model_availability_path,
    visitor_client,
)
from tests.support.factories import ACQUIRED_ON, Factory

pytestmark = pytest.mark.postgres

ALLOCATED: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 3), date(2026, 3, 5))
FOURTH_TO_SIXTH: Final[dict[str, object]] = {"from": "2026-03-04", "to": "2026-03-06"}
# The worked example of the design document, out on the ninth and back on the twelfth.
WORKED_EXAMPLE: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 9), date(2026, 3, 12))
FROM_THE_TWELFTH: Final[dict[str, object]] = {"from": "2026-03-12", "to": "2026-03-14"}
FROM_THE_ELEVENTH: Final[dict[str, object]] = {"from": "2026-03-11", "to": "2026-03-13"}
BRANCH_ANSWER_MEMBERS: Final[set[str]] = {"branchCode", "branchName", "available"}
NEVER_FREE: Final[list[AssetStatus]] = [
    status for status in AssetStatus if status is not AssetStatus.AVAILABLE
]


@dataclass(frozen=True, slots=True)
class Rammers:
    """Two branches and one trench rammer at each."""

    bellville: Branch
    somerset_west: Branch
    model: ProductModel
    bellville_unit: Asset
    somerset_west_unit: Asset


@pytest.fixture
def visitor(postgres_session: Session) -> Iterator[TestClient]:
    """Yield a client with no credential, on the real database."""
    with visitor_client(postgres_session) as client:
        yield client


@pytest.fixture
def rammers(postgres_session: Session, postgres_factory: Factory) -> Rammers:
    """Return two committed branches with one free trench rammer at each."""
    bellville = postgres_factory.branch(code="BLV", name="Bellville")
    somerset_west = postgres_factory.branch(code="SMW", name="Somerset West")
    model = a_model(postgres_factory, name="Trench Rammer", manufacturer="Wacker Neuson")
    built = Rammers(
        bellville=bellville,
        somerset_west=somerset_west,
        model=model,
        bellville_unit=postgres_factory.asset(product_model=model, branch=bellville),
        somerset_west_unit=postgres_factory.asset(product_model=model, branch=somerset_west),
    )
    postgres_session.commit()
    return built


def answers(visitor: TestClient, slug: str, params: dict[str, object]) -> dict[str, bool]:
    """Return whether each branch is available for one model, by branch code."""
    response = visitor.get(model_availability_path(slug), params=params)
    assert response.status_code == status.HTTP_200_OK, response.text
    return {answer["branchCode"]: answer["available"] for answer in response.json()["branches"]}


class TestTheAcceptanceCaseOfUS07:
    """Free at Somerset West, not free at Bellville, and nothing about stock."""

    @pytest.fixture(autouse=True)
    def _bellville_is_allocated(
        self, postgres_session: Session, postgres_factory: Factory, rammers: Rammers
    ) -> None:
        """Hold the Bellville rammer from the third to the fifth of March."""
        hold_unit(postgres_factory, rammers.bellville_unit, ALLOCATED)
        postgres_session.commit()

    def test_the_search_across_the_catalogue_says_where_the_rammer_is_free(
        self, visitor: TestClient, rammers: Rammers
    ) -> None:
        response = visitor.get(AVAILABILITY_PATH, params=FOURTH_TO_SIXTH)

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body.keys() == {"from", "to", "hireDays", "items", "page", "pageSize", "total"}
        assert (body["from"], body["to"], body["hireDays"]) == ("2026-03-04", "2026-03-06", 2)
        assert body["total"] == 1
        (row,) = body["items"]
        assert row.keys() == {"model", "branches"}
        assert row["model"]["sku"] == rammers.model.sku
        assert row["branches"] == [
            {"branchCode": "BLV", "branchName": "Bellville", "available": False},
            {"branchCode": "SMW", "branchName": "Somerset West", "available": True},
        ]

    def test_the_single_model_answer_agrees(self, visitor: TestClient, rammers: Rammers) -> None:
        response = visitor.get(model_availability_path(rammers.model.slug), params=FOURTH_TO_SIXTH)

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "from": "2026-03-04",
            "to": "2026-03-06",
            "hireDays": 2,
            "quantity": 1,
            "branches": [
                {"branchCode": "BLV", "branchName": "Bellville", "available": False},
                {"branchCode": "SMW", "branchName": "Somerset West", "available": True},
            ],
        }

    def test_neither_answer_carries_a_tag_or_a_count(
        self, visitor: TestClient, rammers: Rammers
    ) -> None:
        responses = [
            visitor.get(AVAILABILITY_PATH, params=FOURTH_TO_SIXTH),
            visitor.get(model_availability_path(rammers.model.slug), params=FOURTH_TO_SIXTH),
        ]
        for response in responses:
            assert rammers.bellville_unit.asset_tag not in response.text
            assert rammers.somerset_west_unit.asset_tag not in response.text
        listed = responses[0].json()["items"][0]["branches"]
        single = responses[1].json()["branches"]
        for answer in [*listed, *single]:
            assert answer.keys() == BRANCH_ANSWER_MEMBERS
            assert isinstance(answer["available"], bool)

    def test_neither_answer_may_be_stored_by_a_cache(
        self, visitor: TestClient, rammers: Rammers
    ) -> None:
        listed = visitor.get(AVAILABILITY_PATH, params=FOURTH_TO_SIXTH)
        single = visitor.get(model_availability_path(rammers.model.slug), params=FOURTH_TO_SIXTH)
        assert listed.headers["Cache-Control"] == "no-store"
        assert single.headers["Cache-Control"] == "no-store"


class TestWhatMakesAUnitFree:
    """The status of the unit and its active allocations, together (BR-10)."""

    def test_a_unit_allocated_until_the_twelfth_is_free_for_a_hire_starting_on_the_twelfth(
        self,
        visitor: TestClient,
        postgres_session: Session,
        postgres_factory: Factory,
        rammers: Rammers,
    ) -> None:
        hold_unit(postgres_factory, rammers.bellville_unit, WORKED_EXAMPLE)
        postgres_session.commit()

        assert answers(visitor, rammers.model.slug, FROM_THE_TWELFTH)["BLV"] is True
        assert answers(visitor, rammers.model.slug, FROM_THE_ELEVENTH)["BLV"] is False

    def test_a_hire_that_ends_on_the_day_another_starts_does_not_meet_it(
        self,
        visitor: TestClient,
        postgres_session: Session,
        postgres_factory: Factory,
        rammers: Rammers,
    ) -> None:
        hold_unit(postgres_factory, rammers.bellville_unit, WORKED_EXAMPLE)
        postgres_session.commit()
        until_the_ninth = {"from": "2026-03-06", "to": "2026-03-09"}
        assert answers(visitor, rammers.model.slug, until_the_ninth)["BLV"] is True

    def test_a_released_allocation_does_not_block(
        self,
        visitor: TestClient,
        postgres_session: Session,
        postgres_factory: Factory,
        rammers: Rammers,
    ) -> None:
        hold_unit(postgres_factory, rammers.bellville_unit, ALLOCATED, released=True)
        postgres_session.commit()
        assert answers(visitor, rammers.model.slug, FOURTH_TO_SIXTH)["BLV"] is True

    @pytest.mark.parametrize("unit_status", NEVER_FREE)
    def test_a_unit_that_is_not_available_is_never_free_whatever_its_bookings(
        self,
        visitor: TestClient,
        postgres_session: Session,
        rammers: Rammers,
        unit_status: AssetStatus,
    ) -> None:
        """US-09. The quarantined saw shows no free unit on any future date."""
        rammers.bellville_unit.status = unit_status
        if unit_status is AssetStatus.RETIRED:
            rammers.bellville_unit.retired_on = ACQUIRED_ON
        postgres_session.add(rammers.bellville_unit)
        postgres_session.commit()

        assert answers(visitor, rammers.model.slug, FOURTH_TO_SIXTH) == {"BLV": False, "SMW": True}
        listed = visitor.get(AVAILABILITY_PATH, params=FOURTH_TO_SIXTH).json()["items"][0]
        assert [answer["available"] for answer in listed["branches"]] == [False, True]

    def test_a_branch_with_no_unit_of_the_model_is_listed_and_is_not_free(
        self,
        visitor: TestClient,
        postgres_session: Session,
        postgres_factory: Factory,
        rammers: Rammers,
    ) -> None:
        postgres_factory.branch(code="CBD", name="Cape Town CBD")
        postgres_session.commit()

        assert answers(visitor, rammers.model.slug, FOURTH_TO_SIXTH) == {
            "BLV": True,
            "CBD": False,
            "SMW": True,
        }
        listed = visitor.get(AVAILABILITY_PATH, params=FOURTH_TO_SIXTH).json()["items"][0]
        assert [answer["branchCode"] for answer in listed["branches"]] == ["BLV", "CBD", "SMW"]
        assert [answer["available"] for answer in listed["branches"]] == [True, False, True]

    def test_a_branch_that_is_not_trading_is_not_answered_for(
        self, visitor: TestClient, postgres_session: Session, rammers: Rammers
    ) -> None:
        rammers.somerset_west.is_active = False
        postgres_session.add(rammers.somerset_west)
        postgres_session.commit()
        assert answers(visitor, rammers.model.slug, FOURTH_TO_SIXTH) == {"BLV": True}

    def test_the_last_day_of_the_booking_horizon_is_answered(
        self, visitor: TestClient, rammers: Rammers
    ) -> None:
        """Ninety days after the second of March is the thirty first of May (BR-05)."""
        on_the_horizon = {"from": "2026-05-31", "to": "2026-06-28"}
        assert answers(visitor, rammers.model.slug, on_the_horizon) == {"BLV": True, "SMW": True}


class TestTheQuantityOnTheSingleModel:
    """A branch is available when enough units are free, and the count stays private."""

    @pytest.fixture
    def second_unit(
        self, postgres_session: Session, postgres_factory: Factory, rammers: Rammers
    ) -> Asset:
        """Return a second rammer at Bellville, committed."""
        unit = postgres_factory.asset(product_model=rammers.model, branch=rammers.bellville)
        postgres_session.commit()
        return unit

    @pytest.mark.parametrize(("quantity", "expected"), [(1, True), (2, True), (3, False)])
    def test_two_free_units_satisfy_two_and_not_three(
        self,
        visitor: TestClient,
        rammers: Rammers,
        second_unit: Asset,
        quantity: int,
        expected: bool,
    ) -> None:
        params = {**FOURTH_TO_SIXTH, "quantity": quantity}
        response = visitor.get(model_availability_path(rammers.model.slug), params=params)
        body = response.json()
        assert body["quantity"] == quantity
        assert body["branches"][0] == {
            "branchCode": "BLV",
            "branchName": "Bellville",
            "available": expected,
        }

    def test_a_held_unit_no_longer_counts_towards_the_quantity(
        self,
        visitor: TestClient,
        postgres_session: Session,
        postgres_factory: Factory,
        rammers: Rammers,
        second_unit: Asset,
    ) -> None:
        hold_unit(postgres_factory, second_unit, ALLOCATED)
        postgres_session.commit()
        slug = rammers.model.slug
        assert answers(visitor, slug, {**FOURTH_TO_SIXTH, "quantity": 2})["BLV"] is False
        assert answers(visitor, slug, {**FOURTH_TO_SIXTH, "quantity": 1})["BLV"] is True
