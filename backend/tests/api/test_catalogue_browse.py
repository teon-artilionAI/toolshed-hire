"""The branches, the categories and one model, as a visitor with no account reads them.

FR-02 says the catalogue is browsable without an account. So every request
here carries no credential, and the first thing proved is that each of these
routes says so in its own declaration and is not public by accident.

The shapes are pinned member by member, because the frontend half was written
to the same contract and reads exactly these names. Money is a string with two
decimals and a time of day is `HH:MM`.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import time
from typing import Final

import pytest
from fastapi import status
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.catalogue_deps import CACHE_CONTROL_PUBLIC_VALUE
from app.api.deps import public_access
from app.api.routers import API_PREFIX, availability, branches, catalogue
from app.main import app as production_app
from tests.support.catalogue import (
    AVAILABILITY_PATH,
    BRANCHES_PATH,
    CATEGORIES_PATH,
    MODELS_PATH,
    a_category,
    a_model,
    model_path,
    visitor_client,
)
from tests.support.factories import Factory
from tests.support.http import problem_code
from tests.support.tokens import authorization_header

PUBLIC_ROUTE_TEMPLATES: Final[set[str]] = {
    BRANCHES_PATH,
    CATEGORIES_PATH,
    MODELS_PATH,
    f"{MODELS_PATH}/{{slug}}",
    AVAILABILITY_PATH,
    f"{MODELS_PATH}/{{slug}}/availability",
}
BRANCH_MEMBERS: Final[set[str]] = {
    "code",
    "name",
    "suburb",
    "city",
    "phone",
    "opensAt",
    "closesAt",
}
CATEGORY_MEMBERS: Final[set[str]] = {
    "code",
    "name",
    "slug",
    "description",
    "parentCode",
    "sortOrder",
    "modelCount",
}
SUMMARY_MEMBERS: Final[set[str]] = {
    "sku",
    "slug",
    "name",
    "manufacturer",
    "modelNumber",
    "categoryCode",
    "categoryName",
    "shortDescription",
    "dailyRate",
    "weeklyRate",
    "depositAmount",
    "minHireDays",
    "maxHireDays",
    "imagePath",
}
DETAIL_MEMBERS: Final[set[str]] = SUMMARY_MEMBERS | {"longDescription", "lateFeePerDay"}
NOT_FOUND_PROBLEM: Final[str] = "not-found"
NOT_A_REAL_TOKEN: Final[str] = "not-a-real-token"


@pytest.fixture
def visitor(session: Session) -> Iterator[TestClient]:
    """Yield a client with no credential, on the in memory database."""
    with visitor_client(session) as client:
        yield client


class TestEveryRouteDeclaresThatItIsPublic:
    """Public by declaration, never by omission (BR-41)."""

    def test_the_six_routes_exist_and_each_depends_on_the_public_declaration(self) -> None:
        declared = {
            f"{API_PREFIX}{route.path}"
            for router in (branches.router, catalogue.router, availability.router)
            for route in router.routes
            if isinstance(route, APIRoute)
            and any(dependency.call is public_access for dependency in route.dependant.dependencies)
        }
        assert declared == PUBLIC_ROUTE_TEMPLATES

    def test_none_of_the_three_routers_holds_a_route_without_the_declaration(self) -> None:
        route_count = sum(
            len(router.routes)
            for router in (branches.router, catalogue.router, availability.router)
        )
        assert route_count == len(PUBLIC_ROUTE_TEMPLATES)

    def test_the_openapi_document_describes_all_six(self) -> None:
        assert set(production_app.openapi()["paths"]) >= PUBLIC_ROUTE_TEMPLATES


class TestTheBranchDirectory:
    """`GET /api/branches`."""

    def test_it_lists_the_active_branches_by_name_with_their_hours(
        self, visitor: TestClient, session: Session, factory: Factory
    ) -> None:
        factory.branch(code="SMW", name="Somerset West")
        factory.branch(code="BLV", name="Bellville")
        closed = factory.branch(code="OLD", name="Athlone")
        closed.is_active = False
        session.commit()

        response = visitor.get(BRANCHES_PATH)

        assert response.status_code == status.HTTP_200_OK
        items = response.json()["items"]
        assert [item["code"] for item in items] == ["BLV", "SMW"]
        assert items[0].keys() == BRANCH_MEMBERS
        assert items[0]["opensAt"] == "07:00"
        assert items[0]["closesAt"] == "17:00"

    def test_a_closing_time_with_minutes_keeps_them(
        self, visitor: TestClient, session: Session, factory: Factory
    ) -> None:
        branch = factory.branch(code="CBD")
        branch.closes_at = time(16, 30)
        session.commit()
        assert visitor.get(BRANCHES_PATH).json()["items"][0]["closesAt"] == "16:30"

    def test_it_is_an_empty_list_before_any_branch_exists(self, visitor: TestClient) -> None:
        assert visitor.get(BRANCHES_PATH).json() == {"items": []}


class TestTheCategories:
    """`GET /api/catalogue/categories`."""

    def test_a_parent_comes_before_its_children_and_siblings_sort_by_order_then_name(
        self, visitor: TestClient, session: Session, factory: Factory
    ) -> None:
        access = a_category(factory, name="Access and Lifting", sort_order=60)
        a_category(factory, name="Lifting", sort_order=62, parent=access)
        a_category(factory, name="Ladders", sort_order=61, parent=access)
        a_category(factory, name="Welding", sort_order=100)
        a_category(factory, name="Compaction", sort_order=20)
        a_category(factory, name="Breaking", sort_order=20)
        session.commit()

        items = visitor.get(CATEGORIES_PATH).json()["items"]

        assert [item["name"] for item in items] == [
            "Breaking",
            "Compaction",
            "Access and Lifting",
            "Ladders",
            "Lifting",
            "Welding",
        ]
        assert items[0].keys() == CATEGORY_MEMBERS
        assert items[2]["parentCode"] is None
        assert items[3]["parentCode"] == access.code
        assert items[3]["sortOrder"] == 61

    def test_the_count_is_of_published_models_and_a_parent_includes_its_children(
        self, visitor: TestClient, session: Session, factory: Factory
    ) -> None:
        access = a_category(factory, name="Access and Lifting", sort_order=60)
        ladders = a_category(factory, name="Ladders", sort_order=61, parent=access)
        lifting = a_category(factory, name="Lifting", sort_order=62, parent=access)
        a_model(factory, name="Extension Ladder", category=ladders)
        a_model(factory, name="Scaffold Tower", category=ladders)
        a_model(factory, name="Chain Hoist", category=lifting)
        a_model(factory, name="Draft Trestle", category=ladders, is_published=False)
        session.commit()

        counts = {
            item["name"]: item["modelCount"]
            for item in visitor.get(CATEGORIES_PATH).json()["items"]
        }

        assert counts == {"Access and Lifting": 3, "Ladders": 2, "Lifting": 1}

    def test_an_inactive_category_is_not_listed_and_a_missing_description_is_empty(
        self, visitor: TestClient, session: Session, factory: Factory
    ) -> None:
        a_category(factory, name="Welding", description="Stick and MIG welders.")
        a_category(factory, name="Pumps")
        a_category(factory, name="Discontinued", is_active=False)
        session.commit()

        items = visitor.get(CATEGORIES_PATH).json()["items"]

        assert {item["name"]: item["description"] for item in items} == {
            "Pumps": "",
            "Welding": "Stick and MIG welders.",
        }


class TestOneModel:
    """`GET /api/catalogue/models/{slug}`."""

    def test_the_detail_is_the_summary_plus_the_long_description_and_the_late_fee(
        self, visitor: TestClient, session: Session, factory: Factory
    ) -> None:
        category = a_category(factory, name="Breaking and Drilling")
        model = a_model(factory, name="Rotary Hammer", category=category, daily_rate="280")
        model.long_description = "An 800 W SDS-plus rotary hammer for concrete and masonry."
        session.commit()

        response = visitor.get(model_path(model.slug))

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body.keys() == DETAIL_MEMBERS
        assert body["sku"] == model.sku
        assert body["categoryCode"] == category.code
        assert body["categoryName"] == "Breaking and Drilling"
        assert body["dailyRate"] == "280.00"
        assert body["weeklyRate"] == "740.00"
        assert body["depositAmount"] == "600.00"
        assert body["lateFeePerDay"] == "120.00"
        assert body["minHireDays"] == 1
        assert body["maxHireDays"] == 28
        assert body["imagePath"] is None
        assert body["longDescription"].startswith("An 800 W")

    def test_an_unknown_slug_is_404(self, visitor: TestClient) -> None:
        response = visitor.get(model_path("no-such-model"))
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert problem_code(response) == NOT_FOUND_PROBLEM

    def test_a_model_that_is_not_published_is_404_like_any_unknown_slug(
        self, visitor: TestClient, session: Session, factory: Factory
    ) -> None:
        draft = a_model(factory, name="Draft Breaker", is_published=False)
        session.commit()
        response = visitor.get(model_path(draft.slug))
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert problem_code(response) == NOT_FOUND_PROBLEM


class TestACatalogueResponseMayBeCachedForAMinute:
    """`Cache-Control: public, max-age=60`, unless the request carried a credential."""

    def test_each_catalogue_route_says_so(
        self, visitor: TestClient, session: Session, factory: Factory
    ) -> None:
        model = a_model(factory, name="Rotary Hammer")
        session.commit()
        assert CACHE_CONTROL_PUBLIC_VALUE == "public, max-age=60"
        for path in (BRANCHES_PATH, CATEGORIES_PATH, MODELS_PATH, model_path(model.slug)):
            response = visitor.get(path)
            assert response.status_code == status.HTTP_200_OK
            assert response.headers["Cache-Control"] == CACHE_CONTROL_PUBLIC_VALUE, path

    def test_a_request_that_carried_a_credential_is_never_stored(
        self, visitor: TestClient
    ) -> None:
        response = visitor.get(CATEGORIES_PATH, headers=authorization_header(NOT_A_REAL_TOKEN))
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["Cache-Control"] == "no-store"
