"""Everything the rental routes refuse, and the words each refusal uses.

This asks every route under `/api/rentals`, and `/api/me/rentals`, for every
refusal it can give and pins the status, the problem type and the words, the
way tests/api/test_reservation_refusals.py does for the reservation routes. A
route added under the rentals without a case here fails the guard below.

The cases are in tests/api/rental_return_refusals.py and
tests/api/rental_settlement_refusals.py. They run against the in memory
database, and the clock stands still on Monday the second of March 2026 until
a case moves it.
"""

from __future__ import annotations

from typing import Final

import pytest
from sqlmodel import Session

from app.api.access_policy import declared_routes
from app.domain.enums import UserRole
from app.main import FRAMEWORK_ROUTE_PATHS
from app.main import app as production_app
from tests.api.rental_refusal_cases import RentalRefusal, RentalStage
from tests.api.rental_return_refusals import RETURN_REFUSALS
from tests.api.rental_settlement_refusals import SETTLEMENT_REFUSALS
from tests.api.test_plain_refusals import FORBIDDEN_PATTERNS, sentences_of
from tests.support.booking_api import BookingClient
from tests.support.catalogue import refused_fields
from tests.support.factories import Factory
from tests.support.http import problem_code, problem_of
from tests.support.rental_api import worked_example_world

RENTAL_PATHS: Final[tuple[str, ...]] = ("/api/rentals", "/api/me/rentals")
REFUSALS: Final[list[RentalRefusal]] = [*RETURN_REFUSALS, *SETTLEMENT_REFUSALS]
CASE_IDS: Final[list[str]] = [refusal.name for refusal in REFUSALS]


@pytest.fixture
def stage(booking: BookingClient, session: Session, factory: Factory) -> RentalStage:
    """Return a committed world and the callers the cases are asked by."""
    world = worked_example_world(session, factory, units=2)
    assistant_elsewhere = factory.user(role=UserRole.COUNTER_STAFF, branch=factory.branch())
    administrator = factory.user(role=UserRole.ADMIN)
    session.commit()
    return RentalStage(
        booking=booking,
        world=world,
        assistant_elsewhere=assistant_elsewhere,
        administrator=administrator,
    )


class TestNoSentenceReadsLikeALogLine:
    """No rule identifier and no raw value in anything a caller is shown."""

    @pytest.mark.parametrize("refusal", REFUSALS, ids=CASE_IDS)
    def test_no_detail_and_no_field_message_names_a_rule(
        self, stage: RentalStage, refusal: RentalRefusal
    ) -> None:
        response = refusal.ask(stage)
        assert response.status_code == refusal.status, response.text
        offenders = [
            f"{sentence!r} contains {pattern!r}"
            for sentence in sentences_of(problem_of(response))
            for pattern in FORBIDDEN_PATTERNS
            if pattern in sentence
        ]
        assert offenders == []

    def test_every_rental_route_is_asked_for_a_refusal(self) -> None:
        served = {
            route.name
            for route in declared_routes(production_app, framework_paths=FRAMEWORK_ROUTE_PATHS)
            if route.path.startswith(RENTAL_PATHS)
        }
        assert served == {refusal.route for refusal in REFUSALS}


class TestEachRefusal:
    """The status, the problem type and the exact words."""

    @pytest.mark.parametrize("refusal", REFUSALS, ids=CASE_IDS)
    def test_the_refusal_is_answered_as_the_case_says(
        self, stage: RentalStage, refusal: RentalRefusal
    ) -> None:
        response = refusal.ask(stage)

        assert response.status_code == refusal.status, response.text
        assert problem_code(response) == refusal.code
        body = problem_of(response)
        if refusal.detail is not None:
            assert body["detail"] == refusal.detail
        if refusal.fields is not None:
            assert body["errors"] == {"fields": refusal.fields}
        if refusal.field_names is not None:
            assert refused_fields(body).keys() == refusal.field_names
