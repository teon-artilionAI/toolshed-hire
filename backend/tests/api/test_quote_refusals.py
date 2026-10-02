"""How the quote route refuses, `GET /api/catalogue/models/{slug}/quote`.

A quote is held to the limits of a booking, so it is refused for the reasons
an availability question is refused, and each refusal is a 422 that names the
field. An unknown slug and a model that is not published are the same 404.

What an accepted quote says is in tests/api/test_quote.py.

The clock stands still on Monday the second of March 2026.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.support.catalogue import (
    VALIDATION_PROBLEM,
    a_model,
    a_priced_model,
    model_quote_path,
    refused_fields,
    visitor_client,
)
from tests.support.factories import Factory
from tests.support.http import problem_code, problem_of

YESTERDAY: Final[str] = "2026-03-01"
NINTH: Final[str] = "2026-03-09"
TWELFTH: Final[str] = "2026-03-12"
# Ninety one days after the second of March, one day past the horizon.
BEYOND_THE_HORIZON: Final[str] = "2026-06-01"
# Twenty nine days after the ninth of March.
TWENTY_NINE_DAYS_LATER: Final[str] = "2026-04-07"
NOT_FOUND_PROBLEM: Final[str] = "not-found"
THREE_DAYS: Final[dict[str, object]] = {"from": NINTH, "to": TWELFTH}


@pytest.fixture
def visitor(session: Session) -> Iterator[TestClient]:
    """Yield a client with no credential, on the in memory database."""
    with visitor_client(session) as client:
        yield client


@pytest.fixture
def hammer_slug(session: Session, factory: Factory) -> str:
    """Return the slug of a committed rotary hammer, hired for one to fourteen days."""
    model = a_priced_model(
        factory,
        name="Bosch GBH 2-26 Rotary Hammer",
        daily_rate="280.00",
        weekly_rate="1120.00",
        deposit="1200.00",
        max_hire_days=14,
    )
    session.commit()
    return model.slug


class TestARefusedQuote:
    """Each validation failure is a 422 that names the field, as on the availability routes."""

    @pytest.mark.parametrize(
        ("params", "fields"),
        [
            ({}, ["query.from", "query.to"]),
            ({"from": NINTH}, ["query.to"]),
            ({"to": TWELFTH}, ["query.from"]),
            ({"from": "banana", "to": TWELFTH}, ["query.from"]),
            ({"from": NINTH, "to": "12/03/2026"}, ["query.to"]),
            ({"from": NINTH, "to": NINTH}, ["query.to"]),
            ({"from": TWELFTH, "to": NINTH}, ["query.to"]),
            ({"from": NINTH, "to": TWENTY_NINE_DAYS_LATER}, ["query.to"]),
            ({"from": YESTERDAY, "to": NINTH}, ["query.from"]),
            ({"from": BEYOND_THE_HORIZON, "to": "2026-06-03"}, ["query.from"]),
            ({**THREE_DAYS, "quantity": 0}, ["query.quantity"]),
            ({**THREE_DAYS, "quantity": 11}, ["query.quantity"]),
            ({**THREE_DAYS, "quantity": "many"}, ["query.quantity"]),
            ({"from": NINTH, "to": "2026-03-24"}, ["query.to"]),
        ],
    )
    def test_the_refusal_is_a_422_that_names_the_field(
        self,
        visitor: TestClient,
        hammer_slug: str,
        params: dict[str, object],
        fields: list[str],
    ) -> None:
        response = visitor.get(model_quote_path(hammer_slug), params=params)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert problem_code(response) == VALIDATION_PROBLEM
        assert sorted(refused_fields(problem_of(response))) == sorted(fields)

    def test_a_period_shorter_than_the_model_may_be_hired_for_is_refused(
        self, visitor: TestClient, session: Session, factory: Factory
    ) -> None:
        rammer = a_model(factory, name="Trench Rammer", min_hire_days=2, max_hire_days=5)
        session.commit()
        response = visitor.get(
            model_quote_path(rammer.slug), params={"from": NINTH, "to": "2026-03-10"}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert refused_fields(problem_of(response)) == {
            "query.to": "This tool has to be hired for at least 2 days."
        }

    def test_a_refusal_is_not_stored_by_a_cache_either(
        self, visitor: TestClient, hammer_slug: str
    ) -> None:
        response = visitor.get(model_quote_path(hammer_slug), params={"from": NINTH, "to": NINTH})
        assert "max-age" not in response.headers.get("Cache-Control", "")


class TestAModelNobodyCanSee:
    """An unknown slug and a model that is not published are the same 404."""

    def test_an_unknown_slug_is_404(self, visitor: TestClient) -> None:
        response = visitor.get(model_quote_path("no-such-model"), params=THREE_DAYS)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert problem_code(response) == NOT_FOUND_PROBLEM

    def test_a_model_that_is_not_published_is_404(
        self, visitor: TestClient, session: Session, factory: Factory
    ) -> None:
        draft = a_model(factory, name="Draft Breaker", is_published=False)
        session.commit()
        response = visitor.get(model_quote_path(draft.slug), params=THREE_DAYS)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert problem_code(response) == NOT_FOUND_PROBLEM

    def test_a_bad_period_is_refused_before_the_model_is_looked_for(
        self, visitor: TestClient
    ) -> None:
        response = visitor.get(
            model_quote_path("no-such-model"), params={"from": NINTH, "to": NINTH}
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
