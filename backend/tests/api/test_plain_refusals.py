"""What a refusal says to a customer, and what it says to the log instead.

The sentence of a problem document is put on a customer's screen as it is
written, in `detail` and beside the input for each field. NFR-12 says no
internal identifier reaches the browser. So a sentence names no business rule
and repeats no raw value, and it says what to do.

The first test is the guard. It asks every catalogue, availability and quote
route for every refusal it can give, and it fails if any sentence carries the
mark of a log line. It also checks the route table, so a route added under
`/api/catalogue` without a case here fails it.

The reservation routes are held to the same guard in
tests/api/test_reservation_refusals.py, which reads the forbidden marks from
this file.

The rule and the values that were tried are still wanted, by whoever reads the
log. tests/api/test_refusal_rules_in_the_log.py reads the log the application
really wrote and finds them there.

The clock stands still on Monday the second of March 2026.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from httpx import Response
from sqlmodel import Session

from app.api.access_policy import declared_routes
from app.api.errors import REQUEST_VALIDATION_DETAIL
from app.main import FRAMEWORK_ROUTE_PATHS
from app.main import app as production_app
from tests.support.catalogue import (
    AVAILABILITY_PATH,
    CATEGORIES_PATH,
    MODELS_PATH,
    a_model,
    model_availability_path,
    model_path,
    model_quote_path,
    refused_fields,
    visitor_client,
)
from tests.support.factories import Factory
from tests.support.http import problem_of

# What a sentence must never contain. The first two are how a rule and a
# requirement are named. The last two are how a log line writes a value.
FORBIDDEN_PATTERNS: Final[tuple[str, ...]] = ("BR-", "NFR-", "start=", "end=")
CATALOGUE_PREFIX: Final[str] = "/api/catalogue"

YESTERDAY: Final[str] = "2026-03-01"
NINTH: Final[str] = "2026-03-09"
TWELFTH: Final[str] = "2026-03-12"
BEYOND_THE_HORIZON: Final[str] = "2026-06-01"
TWENTY_NINE_DAYS_LATER: Final[str] = "2026-04-07"
PERIOD: Final[dict[str, object]] = {"from": NINTH, "to": TWELFTH}
NO_SUCH_MODEL: Final[str] = "no-such-model"
RAMMER: Final[str] = "{rammer}"

NEEDED: Final[str] = "This is needed. Please fill it in."
A_VALID_DATE: Final[str] = "Enter a valid date, in the form YYYY-MM-DD."
A_WHOLE_NUMBER: Final[str] = "Enter a whole number."
AN_OPTION: Final[str] = "Choose one of the options offered."
RETURN_AFTER_START: Final[str] = "The return date has to be after the start date."
AT_MOST_28_DAYS: Final[str] = "A hire can be at most 28 days."
TODAY_OR_LATER: Final[str] = "The hire has to start today or later."
WITHIN_90_DAYS: Final[str] = "A hire can start at most 90 days from today."
NO_SUCH_CATEGORY: Final[str] = "We do not have that category. Choose a category from the list."
NO_SUCH_BRANCH: Final[str] = (
    "We do not have a branch with that code. Choose a branch from the list."
)
NO_SUCH_TOOL: Final[str] = "We could not find that tool. Browse the catalogue to choose another."

# The refusals of a period, which the two availability routes and the quote
# route give alike.
PERIOD_REFUSALS: Final[list[tuple[dict[str, object], dict[str, str]]]] = [
    ({}, {"query.from": NEEDED, "query.to": NEEDED}),
    ({"from": "banana", "to": TWELFTH}, {"query.from": A_VALID_DATE}),
    ({"from": NINTH, "to": "12/03/2026"}, {"query.to": A_VALID_DATE}),
    ({"from": NINTH, "to": NINTH}, {"query.to": RETURN_AFTER_START}),
    ({"from": TWELFTH, "to": NINTH}, {"query.to": RETURN_AFTER_START}),
    ({"from": NINTH, "to": TWENTY_NINE_DAYS_LATER}, {"query.to": AT_MOST_28_DAYS}),
    ({"from": YESTERDAY, "to": NINTH}, {"query.from": TODAY_OR_LATER}),
    ({"from": BEYOND_THE_HORIZON, "to": "2026-06-03"}, {"query.from": WITHIN_90_DAYS}),
]
# The refusals of a model search, which the model list and the availability
# search give alike.
SEARCH_REFUSALS: Final[list[tuple[dict[str, object], dict[str, str]]]] = [
    ({"sort": "cheapest"}, {"query.sort": AN_OPTION}),
    ({"category": "no-such-category"}, {"query.category": NO_SUCH_CATEGORY}),
    ({"page": 0}, {"query.page": "Enter 1 or more."}),
    ({"page": "two"}, {"query.page": A_WHOLE_NUMBER}),
    ({"page": 10_001}, {"query.page": "Enter 10000 or less."}),
    ({"pageSize": 0}, {"query.pageSize": "Enter 1 or more."}),
    ({"pageSize": 51}, {"query.pageSize": "Enter 50 or less."}),
    ({"q": "x"}, {"query.q": "Enter at least 2 characters."}),
    ({"q": "x" * 121}, {"query.q": "Enter at most 120 characters."}),
]
# The refusals of one model, which its availability and its quote give alike.
ONE_MODEL_REFUSALS: Final[list[tuple[dict[str, object], dict[str, str]]]] = [
    ({**PERIOD, "quantity": 0}, {"query.quantity": "Enter 1 or more."}),
    ({**PERIOD, "quantity": 11}, {"query.quantity": "Enter 10 or less."}),
    ({**PERIOD, "quantity": "many"}, {"query.quantity": A_WHOLE_NUMBER}),
    (
        {"from": NINTH, "to": "2026-03-15"},
        {"query.to": "This tool can be hired for at most 5 days."},
    ),
    (
        {"from": NINTH, "to": "2026-03-10"},
        {"query.to": "This tool has to be hired for at least 2 days."},
    ),
]


@dataclass(frozen=True, slots=True)
class Refusal:
    """One request a route refuses, and what the refusal is expected to say.

    Attributes:
        route: The path template of the route, as the route table names it.
        slug: The slug to ask about, `RAMMER` for the model the test creates,
            or None for a route that takes none.
        params: The query string.
        status: The status expected.
        fields: The sentence expected beside each refused field. Empty for a
            refusal that names no field.
        detail: The sentence expected in `detail`.

    """

    route: str
    slug: str | None
    params: dict[str, object]
    status: int
    fields: dict[str, str]
    detail: str = REQUEST_VALIDATION_DETAIL


def _refused(
    route: str, slug: str | None, cases: list[tuple[dict[str, object], dict[str, str]]]
) -> list[Refusal]:
    """Return a 422 case for each refused query string of a route."""
    return [
        Refusal(route, slug, params, status.HTTP_422_UNPROCESSABLE_CONTENT, fields)
        for params, fields in cases
    ]


def _not_found(route: str) -> Refusal:
    """Return the 404 case of a route that is asked about a model nobody can see."""
    return Refusal(route, NO_SUCH_MODEL, dict(PERIOD), status.HTTP_404_NOT_FOUND, {}, NO_SUCH_TOOL)


MODEL_ROUTE: Final[str] = f"{MODELS_PATH}/{{slug}}"
MODEL_AVAILABILITY_ROUTE: Final[str] = f"{MODELS_PATH}/{{slug}}/availability"
MODEL_QUOTE_ROUTE: Final[str] = f"{MODELS_PATH}/{{slug}}/quote"

REFUSALS: Final[list[Refusal]] = [
    *_refused(MODELS_PATH, None, SEARCH_REFUSALS),
    _not_found(MODEL_ROUTE),
    *_refused(AVAILABILITY_PATH, None, PERIOD_REFUSALS),
    *_refused(
        AVAILABILITY_PATH,
        None,
        [({**PERIOD, **params}, fields) for params, fields in SEARCH_REFUSALS],
    ),
    *_refused(
        AVAILABILITY_PATH, None, [({**PERIOD, "branch": "XYZ"}, {"query.branch": NO_SUCH_BRANCH})]
    ),
    *_refused(MODEL_AVAILABILITY_ROUTE, RAMMER, PERIOD_REFUSALS + ONE_MODEL_REFUSALS),
    _not_found(MODEL_AVAILABILITY_ROUTE),
    *_refused(MODEL_QUOTE_ROUTE, RAMMER, PERIOD_REFUSALS + ONE_MODEL_REFUSALS),
    _not_found(MODEL_QUOTE_ROUTE),
]
# The category list takes no parameter and reads no single record, so it has
# no refusal of its own to give.
ROUTES_WITH_NO_REFUSAL: Final[frozenset[str]] = frozenset({CATEGORIES_PATH})


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


def ask(visitor: TestClient, refusal: Refusal, rammer_slug: str) -> Response:
    """Make the request a case describes."""
    slug = rammer_slug if refusal.slug == RAMMER else refusal.slug
    path = refusal.route.format(slug=slug) if slug is not None else refusal.route
    return visitor.get(path, params=refusal.params)


def sentences_of(body: dict[str, object]) -> list[str]:
    """Return every sentence of a problem document a screen could show."""
    sentences = [str(body["detail"])]
    errors = body.get("errors")
    if isinstance(errors, dict) and isinstance(errors.get("fields"), dict):
        sentences.extend(str(sentence) for sentence in errors["fields"].values())
    return sentences


class TestNoSentenceReadsLikeALogLine:
    """The guard. No rule identifier and no raw value in anything a customer is shown."""

    def test_no_detail_and_no_field_message_names_a_rule_or_repeats_a_raw_value(
        self, visitor: TestClient, rammer_slug: str
    ) -> None:
        offenders: list[str] = []
        for refusal in REFUSALS:
            response = ask(visitor, refusal, rammer_slug)
            assert response.status_code == refusal.status, (
                f"{refusal.route} with {refusal.params} answered {response.status_code}, so "
                "it gave no refusal for this test to read."
            )
            for sentence in sentences_of(problem_of(response)):
                offenders.extend(
                    f"{refusal.route} {refusal.params}: {sentence!r} contains {pattern!r}"
                    for pattern in FORBIDDEN_PATTERNS
                    if pattern in sentence
                )
        assert offenders == [], (
            "These sentences reach a customer's screen and read like a log line. Put the "
            f"rule and the values in the log instead (NFR-12): {offenders}"
        )

    def test_every_catalogue_availability_and_quote_route_is_asked(self) -> None:
        """A route added under the catalogue has to bring its refusals to this file."""
        served = {
            route.path
            for route in declared_routes(production_app, framework_paths=FRAMEWORK_ROUTE_PATHS)
            if route.path.startswith(CATALOGUE_PREFIX)
        }
        assert served == {refusal.route for refusal in REFUSALS} | ROUTES_WITH_NO_REFUSAL

    @pytest.mark.parametrize("pattern", ["(BR-04)", "NFR-12", "start=2026-10-10 end=2026-11-20"])
    def test_the_guard_would_catch_the_sentences_that_were_seen_in_the_browser(
        self, pattern: str
    ) -> None:
        assert any(forbidden in pattern for forbidden in FORBIDDEN_PATTERNS)


class TestEachRefusalIsAPlainSentence:
    """The exact words, so a change of wording is a change somebody chose to make."""

    @pytest.mark.parametrize(
        "refusal", REFUSALS, ids=[f"{r.route} {json.dumps(r.params)}"[:90] for r in REFUSALS]
    )
    def test_the_refusal_says_what_to_do(
        self, visitor: TestClient, rammer_slug: str, refusal: Refusal
    ) -> None:
        body = problem_of(ask(visitor, refusal, rammer_slug))

        assert body["detail"] == refusal.detail
        if refusal.fields:
            assert refused_fields(body) == refusal.fields
        for sentence in sentences_of(body):
            assert sentence.endswith("."), f"{sentence!r} is not a finished sentence."
            assert not sentence.startswith("Attempted"), f"{sentence!r} reads like a log line."
            assert "Input should" not in sentence, f"{sentence!r} is the framework's wording."

    def test_an_unknown_model_is_the_same_sentence_on_all_three_routes(
        self, visitor: TestClient
    ) -> None:
        details = {
            problem_of(visitor.get(path, params=PERIOD))["detail"]
            for path in (
                model_path(NO_SUCH_MODEL),
                model_availability_path(NO_SUCH_MODEL),
                model_quote_path(NO_SUCH_MODEL),
            )
        }
        assert details == {NO_SUCH_TOOL}
