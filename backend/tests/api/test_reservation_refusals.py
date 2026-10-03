"""Everything the reservation routes refuse, and the words each refusal uses.

The sentence of a problem document is put on a customer's screen as it is
written. So a refusal names no business rule and repeats no raw value
(NFR-12), and it says what to do. This file asks every reservation route for
every refusal it can give and pins the status, the problem type and the words.

The first class is the guard, extended from tests/api/test_plain_refusals.py.
It fails if any sentence carries the mark of a log line, and it checks the
route table, so a route added under `/api/reservations` without a case here
fails it.

A refused field is named under `errors.fields` by where it travelled and its
name on the wire, for example `body.from`. A value the framework refused for
its type keeps the framework's wording, as every request body does. A value a
rule refused carries a plain sentence.

The cases are in tests/api/reservation_create_refusals.py,
tests/api/reservation_move_refusals.py,
tests/api/reservation_checkout_refusals.py and
tests/api/reservation_no_show_refusals.py. These run against the in memory
database, and the clock stands still on Monday the second of March
2026 until a case moves it.
"""

from __future__ import annotations

from typing import Final

import pytest
from fastapi import status
from sqlmodel import Session, select

from app.api.access_policy import declared_routes
from app.domain.enums import UserRole
from app.infrastructure.models import AssetAllocation, AuditEvent, Notification, Reservation
from app.main import FRAMEWORK_ROUTE_PATHS
from app.main import app as production_app
from tests.api.reservation_checkout_refusals import CHECKOUT_REFUSALS
from tests.api.reservation_create_refusals import CREATE_REFUSALS
from tests.api.reservation_move_refusals import MOVE_REFUSALS
from tests.api.reservation_no_show_refusals import NO_SHOW_REFUSALS
from tests.api.reservation_refusal_cases import Refusal, Stage
from tests.api.test_plain_refusals import FORBIDDEN_PATTERNS, sentences_of
from tests.support.booking_api import BookingClient, build_booking_world
from tests.support.catalogue import refused_fields
from tests.support.factories import Factory
from tests.support.http import problem_code, problem_of

RESERVATIONS_PREFIX: Final[str] = "/api/reservations"
REFUSALS: Final[list[Refusal]] = [
    *CREATE_REFUSALS,
    *MOVE_REFUSALS,
    *CHECKOUT_REFUSALS,
    *NO_SHOW_REFUSALS,
]
CASE_IDS: Final[list[str]] = [refusal.name for refusal in REFUSALS]


@pytest.fixture
def stage(booking: BookingClient, session: Session, factory: Factory) -> Stage:
    """Return a committed world and the four callers the cases are asked by."""
    world = build_booking_world(factory, asset_count=2)
    stranger = factory.user(role=UserRole.CUSTOMER)
    factory.customer_profile(branch=world.branch, account=stranger)
    assistant_elsewhere = factory.user(role=UserRole.COUNTER_STAFF, branch=factory.branch())
    administrator = factory.user(role=UserRole.ADMIN)
    session.commit()
    return Stage(
        booking=booking,
        session=session,
        world=world,
        stranger=stranger,
        assistant_elsewhere=assistant_elsewhere,
        administrator=administrator,
    )


class TestNoSentenceReadsLikeALogLine:
    """The guard. No rule identifier and no raw value in anything a customer is shown."""

    @pytest.mark.parametrize("refusal", REFUSALS, ids=CASE_IDS)
    def test_no_detail_and_no_field_message_names_a_rule_or_repeats_a_raw_value(
        self, stage: Stage, refusal: Refusal
    ) -> None:
        response = refusal.ask(stage)
        assert response.status_code == refusal.status, response.text
        offenders = [
            f"{sentence!r} contains {pattern!r}"
            for sentence in sentences_of(problem_of(response))
            for pattern in FORBIDDEN_PATTERNS
            if pattern in sentence
        ]
        assert offenders == [], (
            "These sentences reach a customer's screen and read like a log line. Put the "
            f"rule and the values in the log instead (NFR-12): {offenders}"
        )
        assert not any(pattern in response.text for pattern in FORBIDDEN_PATTERNS)

    def test_every_reservation_route_is_asked_for_a_refusal(self) -> None:
        """A route added under the reservations has to bring its refusals to this file."""
        served = {
            route.name
            for route in declared_routes(production_app, framework_paths=FRAMEWORK_ROUTE_PATHS)
            if route.path.startswith(RESERVATIONS_PREFIX)
        }
        assert served == {refusal.route for refusal in REFUSALS}


class TestEachRefusal:
    """The status, the problem type and the exact words."""

    @pytest.mark.parametrize("refusal", REFUSALS, ids=CASE_IDS)
    def test_the_refusal_is_answered_as_the_case_says(
        self, stage: Stage, refusal: Refusal
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

    @pytest.mark.parametrize(
        "refusal",
        [refusal for refusal in REFUSALS if refusal.detail is not None],
        ids=[refusal.name for refusal in REFUSALS if refusal.detail is not None],
    )
    def test_a_sentence_written_for_a_customer_is_a_finished_plain_one(
        self, stage: Stage, refusal: Refusal
    ) -> None:
        detail = str(problem_of(refusal.ask(stage))["detail"])
        assert detail.endswith("."), f"{detail!r} is not a finished sentence."
        assert not detail.startswith("Attempted"), f"{detail!r} reads like a log line."
        assert "Input should" not in detail, f"{detail!r} is the framework's wording."


class TestARefusalLeavesNothingBehind:
    """A refused create writes no reservation, no event and no notification."""

    @pytest.mark.parametrize(
        "refusal",
        [refusal for refusal in REFUSALS if refusal.route == "POST /api/reservations"],
        ids=[refusal.name for refusal in REFUSALS if refusal.route == "POST /api/reservations"],
    )
    def test_a_refused_draft_is_not_stored(self, stage: Stage, refusal: Refusal) -> None:
        response = refusal.ask(stage)
        assert response.status_code >= status.HTTP_400_BAD_REQUEST
        assert stage.session.exec(select(Reservation)).all() == []
        assert stage.session.exec(select(AuditEvent)).all() == []
        assert stage.session.exec(select(Notification)).all() == []
        assert stage.session.exec(select(AssetAllocation)).all() == []


class TestTheConflictNeverSaysHowManyAreLeft:
    """A customer learns that a model is not available, and never how many units are (US-07)."""

    def test_the_conflict_names_the_model_and_the_dates_and_carries_no_count(
        self, stage: Stage
    ) -> None:
        draft = stage.booking.drafted(stage.world, quantity=3)
        response = stage.booking.hold(stage.world.customer, draft["id"])

        body = problem_of(response)
        assert response.status_code == status.HTTP_409_CONFLICT
        assert stage.world.product_model.name in str(body["detail"])
        assert "9 March 2026" in str(body["detail"])
        assert "12 March 2026" in str(body["detail"])
        assert body["errors"] == {
            "model_slug": stage.world.product_model.slug,
            "period": "[2026-03-09,2026-03-12)",
        }
        assert "quantity" not in response.text

    def test_a_refused_hold_allocates_nothing_and_leaves_the_draft_a_draft(
        self, stage: Stage
    ) -> None:
        draft = stage.booking.drafted(stage.world, quantity=3)
        stage.booking.hold(stage.world.customer, draft["id"])
        assert stage.session.exec(select(AssetAllocation)).all() == []
        (stored,) = stage.session.exec(select(Reservation)).all()
        assert stored.status.value == "DRAFT"
        assert stored.hold_expires_at is None
