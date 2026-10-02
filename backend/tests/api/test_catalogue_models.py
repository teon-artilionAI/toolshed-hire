"""The list of published models, with its filters, its orders and its pages.

`GET /api/catalogue/models` is the catalogue a visitor browses (FR-02). Only
published models are in it. The category travels as a slug, because it sits in
the address bar, and a parent category brings its children with it.

The refusals are checked for the field they name. The frontend puts the
sentence beside the input, and it finds the input by the name the contract
gives the query parameter, so `query.pageSize` and not `query.page_size`.

The text a visitor typed must never reach the log. The last test reads what the
application really wrote and looks for it.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.support.catalogue import (
    MODELS_PATH,
    VALIDATION_PROBLEM,
    a_category,
    a_model,
    refused_fields,
    visitor_client,
)
from tests.support.factories import Factory
from tests.support.http import problem_code, problem_of
from tests.support.log_capture import LogCapture

MODEL_SEARCH_FINISHED: Final[str] = "catalogue.model_search_finished"
DEFAULT_PAGE_SIZE: Final[int] = 24
SEARCH_TEXT: Final[str] = "wacker"


@pytest.fixture
def visitor(session: Session) -> Iterator[TestClient]:
    """Yield a client with no credential, on the in memory database."""
    with visitor_client(session) as client:
        yield client


@pytest.fixture
def stocked(session: Session, factory: Factory) -> None:
    """Commit five published models in two categories, and one draft."""
    access = a_category(factory, name="Access and Lifting", sort_order=60)
    ladders = a_category(factory, name="Ladders", sort_order=61, parent=access)
    compaction = a_category(factory, name="Compaction", sort_order=20)
    a_model(factory, name="Chain Hoist", category=access, daily_rate="310.00")
    a_model(factory, name="Extension Ladder", category=ladders, daily_rate="95.00")
    a_model(
        factory,
        name="Plate Compactor",
        category=compaction,
        manufacturer="Wacker Neuson",
        model_number="VP1550",
        daily_rate="420.00",
    )
    a_model(
        factory,
        name="Trench Rammer",
        category=compaction,
        manufacturer="Wacker Neuson",
        model_number="BS60-2",
        daily_rate="380.50",
    )
    a_model(factory, name="Scaffold Tower", category=ladders, daily_rate="95.00")
    a_model(factory, name="Unreleased Roller", category=compaction, is_published=False)
    session.commit()


def names_of(response_body: dict[str, object]) -> list[str]:
    """Return the names of the models on a page, in the order they came."""
    items = response_body["items"]
    assert isinstance(items, list)
    return [item["name"] for item in items]


@pytest.mark.usefixtures("stocked")
class TestWhatIsListed:
    """Published models only, a page at a time."""

    def test_the_defaults_are_the_first_page_of_twenty_four_ordered_by_name(
        self, visitor: TestClient
    ) -> None:
        body = visitor.get(MODELS_PATH).json()
        assert body["page"] == 1
        assert body["pageSize"] == DEFAULT_PAGE_SIZE
        assert body["total"] == 5
        assert names_of(body) == [
            "Chain Hoist",
            "Extension Ladder",
            "Plate Compactor",
            "Scaffold Tower",
            "Trench Rammer",
        ]

    def test_a_model_that_is_not_published_is_never_listed(self, visitor: TestClient) -> None:
        assert "Unreleased Roller" not in names_of(visitor.get(MODELS_PATH).json())

    def test_money_is_a_string_with_two_decimals(self, visitor: TestClient) -> None:
        hoist = visitor.get(MODELS_PATH).json()["items"][0]
        assert hoist["dailyRate"] == "310.00"
        assert hoist["weeklyRate"] == "740.00"
        assert hoist["depositAmount"] == "600.00"

    def test_a_page_carries_the_total_of_the_whole_list(self, visitor: TestClient) -> None:
        second = visitor.get(MODELS_PATH, params={"page": 2, "pageSize": 2}).json()
        assert second["page"] == 2
        assert second["pageSize"] == 2
        assert second["total"] == 5
        assert names_of(second) == ["Plate Compactor", "Scaffold Tower"]

    def test_a_page_past_the_end_is_empty_and_still_carries_the_total(
        self, visitor: TestClient
    ) -> None:
        beyond = visitor.get(MODELS_PATH, params={"page": 4, "pageSize": 2}).json()
        assert beyond["items"] == []
        assert beyond["total"] == 5


@pytest.mark.usefixtures("stocked")
class TestTheFilters:
    """A category slug and a free text, alone and together."""

    def test_a_child_category_lists_its_own_models(self, visitor: TestClient) -> None:
        body = visitor.get(MODELS_PATH, params={"category": _slug_of(visitor, "Ladders")}).json()
        assert names_of(body) == ["Extension Ladder", "Scaffold Tower"]
        assert body["total"] == 2

    def test_a_parent_category_includes_the_models_of_its_children(
        self, visitor: TestClient
    ) -> None:
        slug = _slug_of(visitor, "Access and Lifting")
        body = visitor.get(MODELS_PATH, params={"category": slug}).json()
        assert names_of(body) == ["Chain Hoist", "Extension Ladder", "Scaffold Tower"]
        assert body["total"] == 3

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("LADDER", ["Extension Ladder"]),
            ("wacker", ["Plate Compactor", "Trench Rammer"]),
            ("bs60", ["Trench Rammer"]),
            ("no such machine", []),
        ],
    )
    def test_the_text_matches_name_manufacturer_and_model_number_in_any_case(
        self, visitor: TestClient, text: str, expected: list[str]
    ) -> None:
        body = visitor.get(MODELS_PATH, params={"q": text}).json()
        assert names_of(body) == expected
        assert body["total"] == len(expected)

    def test_a_percent_sign_is_matched_as_itself_and_not_as_a_wildcard(
        self, visitor: TestClient
    ) -> None:
        assert visitor.get(MODELS_PATH, params={"q": "%%"}).json()["total"] == 0

    def test_surrounding_spaces_are_not_part_of_the_text(self, visitor: TestClient) -> None:
        body = visitor.get(MODELS_PATH, params={"q": "  rammer  "}).json()
        assert names_of(body) == ["Trench Rammer"]

    def test_the_category_and_the_text_narrow_each_other(self, visitor: TestClient) -> None:
        slug = _slug_of(visitor, "Compaction")
        body = visitor.get(MODELS_PATH, params={"category": slug, "q": "plate"}).json()
        assert names_of(body) == ["Plate Compactor"]


@pytest.mark.usefixtures("stocked")
class TestTheOrders:
    """Three orders, each chosen by name and never by column."""

    def test_by_name(self, visitor: TestClient) -> None:
        body = visitor.get(MODELS_PATH, params={"sort": "name"}).json()
        assert names_of(body) == sorted(names_of(body))

    def test_by_daily_rate_cheapest_first_with_the_name_breaking_a_tie(
        self, visitor: TestClient
    ) -> None:
        body = visitor.get(MODELS_PATH, params={"sort": "dailyRateAsc"}).json()
        assert names_of(body) == [
            "Extension Ladder",
            "Scaffold Tower",
            "Chain Hoist",
            "Trench Rammer",
            "Plate Compactor",
        ]

    def test_by_daily_rate_dearest_first(self, visitor: TestClient) -> None:
        body = visitor.get(MODELS_PATH, params={"sort": "dailyRateDesc"}).json()
        assert names_of(body) == [
            "Plate Compactor",
            "Trench Rammer",
            "Chain Hoist",
            "Extension Ladder",
            "Scaffold Tower",
        ]


class TestARefusedQueryNamesItsField:
    """A 422 problem whose `errors.fields` is keyed by the query parameter."""

    @pytest.mark.parametrize(
        ("params", "field"),
        [
            ({"sort": "daily_rate; DROP TABLE asset"}, "query.sort"),
            ({"sort": "priceAsc"}, "query.sort"),
            ({"category": "no-such-category"}, "query.category"),
            ({"pageSize": 0}, "query.pageSize"),
            ({"pageSize": 51}, "query.pageSize"),
            ({"page": 0}, "query.page"),
            ({"page": "two"}, "query.page"),
            ({"q": "x"}, "query.q"),
            ({"q": "   "}, "query.q"),
        ],
    )
    def test_the_refusal_is_a_422_that_names_the_parameter(
        self, visitor: TestClient, params: dict[str, object], field: str
    ) -> None:
        response = visitor.get(MODELS_PATH, params=params)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert problem_code(response) == VALIDATION_PROBLEM
        assert list(refused_fields(problem_of(response))) == [field]

    def test_an_inactive_category_is_refused_like_an_unknown_one(
        self, visitor: TestClient, session: Session, factory: Factory
    ) -> None:
        retired = a_category(factory, name="Discontinued", is_active=False)
        session.commit()
        response = visitor.get(MODELS_PATH, params={"category": retired.slug})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert list(refused_fields(problem_of(response))) == ["query.category"]

    def test_the_largest_page_size_is_accepted(self, visitor: TestClient) -> None:
        assert visitor.get(MODELS_PATH, params={"pageSize": 50}).status_code == status.HTTP_200_OK


@pytest.mark.usefixtures("stocked")
class TestTheSearchIsLoggedWithoutWhatWasTyped:
    """The filters, the row count and the duration, and only the length of the text."""

    def test_the_finishing_line_carries_the_filters_and_never_the_text(
        self, visitor: TestClient, application_log: LogCapture
    ) -> None:
        visitor.get(MODELS_PATH, params={"q": SEARCH_TEXT, "sort": "dailyRateAsc"})

        line = application_log.only(MODEL_SEARCH_FINISHED)
        assert line["q_length"] == len(SEARCH_TEXT)
        assert line["sort"] == "DAILY_RATE_ASC"
        assert line["page"] == 1
        assert line["page_size"] == DEFAULT_PAGE_SIZE
        assert line["row_count"] == 2
        assert isinstance(line["duration_ms"], float)
        written = " ".join(str(entry) for entry in application_log.application_entries())
        assert SEARCH_TEXT not in written.lower()


def _slug_of(visitor: TestClient, category_name: str) -> str:
    """Return the slug the category list gives a category, as the frontend reads it."""
    items = visitor.get("/api/catalogue/categories").json()["items"]
    return next(str(item["slug"]) for item in items if item["name"] == category_name)
