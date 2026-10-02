"""Every way an availability question is refused, and the field each refusal names.

An availability search is refused before any availability SQL runs, so all of
this is proved on the in memory database. What a search answers when it is
accepted depends on the exclusion constraint and on date ranges, and that is
proved against PostgreSQL in tests/integration/test_availability_search.py.

The clock stands still on Monday the second of March 2026, so "in the past"
and "ninety days ahead" are dates the test can name.

The limits are BR-03, at most twenty eight days, BR-04, no start in the past,
and BR-05, no start more than ninety days ahead. They are the limits a booking
is held to, and the search reuses the same `BookingPeriod`, so a period the
search accepts is one a booking would accept.
"""

from __future__ import annotations

from collections.abc import Iterator
from http import HTTPStatus
from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from httpx import Response
from sqlmodel import Session

from app.api.errors import PROBLEM_TYPE_PREFIX, REQUEST_VALIDATION_DETAIL
from tests.support.catalogue import (
    AVAILABILITY_PATH,
    VALIDATION_PROBLEM,
    a_model,
    model_availability_path,
    refused_fields,
    visitor_client,
)
from tests.support.factories import Factory
from tests.support.http import problem_code, problem_of

# The fixed clock says today is the second of March 2026.
TODAY: Final[str] = "2026-03-02"
YESTERDAY: Final[str] = "2026-03-01"
NEXT_WEEK: Final[str] = "2026-03-09"
THREE_DAYS_LATER: Final[str] = "2026-03-12"
# Ninety one days after the second of March, one day past the horizon.
BEYOND_THE_HORIZON: Final[str] = "2026-06-01"
# Twenty nine days after the ninth of March.
TWENTY_NINE_DAYS_LATER: Final[str] = "2026-04-07"
NOT_FOUND_PROBLEM: Final[str] = "not-found"
VALID_PERIOD: Final[dict[str, object]] = {"from": NEXT_WEEK, "to": THREE_DAYS_LATER}

REFUSED_ON_BOTH_ROUTES: Final[list[tuple[dict[str, object], list[str]]]] = [
    ({}, ["query.from", "query.to"]),
    ({"from": NEXT_WEEK}, ["query.to"]),
    ({"from": "banana", "to": THREE_DAYS_LATER}, ["query.from"]),
    ({"from": NEXT_WEEK, "to": "12/03/2026"}, ["query.to"]),
    ({"from": NEXT_WEEK, "to": NEXT_WEEK}, ["query.to"]),
    ({"from": THREE_DAYS_LATER, "to": NEXT_WEEK}, ["query.to"]),
    ({"from": NEXT_WEEK, "to": TWENTY_NINE_DAYS_LATER}, ["query.to"]),
    ({"from": YESTERDAY, "to": NEXT_WEEK}, ["query.from"]),
    ({"from": BEYOND_THE_HORIZON, "to": "2026-06-03"}, ["query.from"]),
]


@pytest.fixture
def visitor(session: Session) -> Iterator[TestClient]:
    """Yield a client with no credential, on the in memory database."""
    with visitor_client(session) as client:
        yield client


@pytest.fixture
def rammer_slug(session: Session, factory: Factory) -> str:
    """Return the slug of a committed model hired for two to five days."""
    model = a_model(factory, name="Trench Rammer", min_hire_days=2, max_hire_days=5)
    session.commit()
    return model.slug


def assert_refused(fields: list[str], response: Response) -> None:
    """Assert that a response is a 422 problem naming exactly these fields."""
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert problem_code(response) == VALIDATION_PROBLEM
    assert sorted(refused_fields(problem_of(response))) == sorted(fields)


class TestTheSearchAcrossTheCatalogue:
    """`GET /api/catalogue/availability`."""

    @pytest.mark.parametrize(("params", "fields"), REFUSED_ON_BOTH_ROUTES)
    def test_a_period_a_booking_would_refuse_is_refused(
        self, visitor: TestClient, params: dict[str, object], fields: list[str]
    ) -> None:
        assert_refused(fields, visitor.get(AVAILABILITY_PATH, params=params))

    @pytest.mark.parametrize(
        ("extra", "field"),
        [
            ({"sort": "cheapest"}, "query.sort"),
            ({"category": "no-such-category"}, "query.category"),
            ({"branch": "XYZ"}, "query.branch"),
            ({"pageSize": 0}, "query.pageSize"),
            ({"pageSize": 51}, "query.pageSize"),
            ({"q": "x"}, "query.q"),
        ],
    )
    def test_an_unknown_sort_category_or_branch_and_a_bad_page_size_are_refused(
        self, visitor: TestClient, extra: dict[str, object], field: str
    ) -> None:
        assert_refused([field], visitor.get(AVAILABILITY_PATH, params={**VALID_PERIOD, **extra}))

    def test_a_branch_that_is_no_longer_trading_is_refused_like_an_unknown_one(
        self, visitor: TestClient, session: Session, factory: Factory
    ) -> None:
        closed = factory.branch(code="OLD", name="Athlone")
        closed.is_active = False
        session.commit()
        response = visitor.get(AVAILABILITY_PATH, params={**VALID_PERIOD, "branch": "OLD"})
        assert_refused(["query.branch"], response)

    def test_the_problem_document_has_one_shape_and_the_sentence_sits_under_the_field(
        self, visitor: TestClient
    ) -> None:
        response = visitor.get(AVAILABILITY_PATH, params={"from": NEXT_WEEK, "to": NEXT_WEEK})
        body = problem_of(response)

        assert body.keys() == {
            "type",
            "title",
            "status",
            "detail",
            "instance",
            "errors",
            "requestId",
        }
        assert body["type"] == f"{PROBLEM_TYPE_PREFIX}{VALIDATION_PROBLEM}"
        assert body["title"] == HTTPStatus(status.HTTP_422_UNPROCESSABLE_CONTENT).phrase
        assert body["instance"] == AVAILABILITY_PATH
        assert body["detail"] == REQUEST_VALIDATION_DETAIL
        assert body["errors"] == {
            "fields": {"query.to": "The return date has to be after the start date."}
        }

    def test_a_refusal_is_not_given_a_cache_lifetime(self, visitor: TestClient) -> None:
        response = visitor.get(AVAILABILITY_PATH, params={"from": YESTERDAY, "to": NEXT_WEEK})
        assert "max-age" not in response.headers.get("Cache-Control", "")


class TestTheSingleModel:
    """`GET /api/catalogue/models/{slug}/availability`."""

    @pytest.mark.parametrize(("params", "fields"), REFUSED_ON_BOTH_ROUTES)
    def test_a_period_a_booking_would_refuse_is_refused(
        self, visitor: TestClient, rammer_slug: str, params: dict[str, object], fields: list[str]
    ) -> None:
        assert_refused(fields, visitor.get(model_availability_path(rammer_slug), params=params))

    @pytest.mark.parametrize("quantity", [0, 11, "many"])
    def test_a_quantity_outside_one_to_ten_is_refused(
        self, visitor: TestClient, rammer_slug: str, quantity: object
    ) -> None:
        response = visitor.get(
            model_availability_path(rammer_slug), params={**VALID_PERIOD, "quantity": quantity}
        )
        assert_refused(["query.quantity"], response)

    def test_a_period_longer_than_the_model_may_be_hired_for_is_refused(
        self, visitor: TestClient, rammer_slug: str
    ) -> None:
        response = visitor.get(
            model_availability_path(rammer_slug), params={"from": NEXT_WEEK, "to": "2026-03-15"}
        )
        assert_refused(["query.to"], response)
        message = refused_fields(problem_of(response))["query.to"]
        assert "at most 5 days" in message

    def test_a_period_shorter_than_the_model_may_be_hired_for_is_refused(
        self, visitor: TestClient, rammer_slug: str
    ) -> None:
        response = visitor.get(
            model_availability_path(rammer_slug), params={"from": NEXT_WEEK, "to": "2026-03-10"}
        )
        assert_refused(["query.to"], response)
        message = refused_fields(problem_of(response))["query.to"]
        assert "at least 2 days" in message

    def test_an_unknown_slug_is_404(self, visitor: TestClient) -> None:
        response = visitor.get(model_availability_path("no-such-model"), params=VALID_PERIOD)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert problem_code(response) == NOT_FOUND_PROBLEM

    def test_a_model_that_is_not_published_is_404(
        self, visitor: TestClient, session: Session, factory: Factory
    ) -> None:
        draft = a_model(factory, name="Draft Breaker", is_published=False)
        session.commit()
        response = visitor.get(model_availability_path(draft.slug), params=VALID_PERIOD)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert problem_code(response) == NOT_FOUND_PROBLEM

    def test_a_start_today_is_not_in_the_past(self, visitor: TestClient) -> None:
        """Today is accepted, so the refusal that comes back is the unknown slug."""
        response = visitor.get(
            model_availability_path("no-such-model"), params={"from": TODAY, "to": NEXT_WEEK}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
