"""The rule behind a refusal and the values that were tried, read back from the log.

A refusal tells a customer what to do and names no rule and no raw value, which
tests/api/test_plain_refusals.py holds. Whoever reads the log still wants both.
These tests read the log the application really wrote, through its own handler
and filters, and find the rule and the values there, and they read the response
again to see that neither went out with it.

The booking route is here as well. It is held to the same period and the same
booking window, so it refuses in the same words and logs the same rules.

The clock of the visitor stands still on Monday the second of March 2026. The
booking route runs on the real clock, so its dates are counted from today.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.application.clock import business_day
from tests.support.catalogue import (
    AVAILABILITY_PATH,
    MODELS_PATH,
    model_quote_path,
    visitor_client,
)
from tests.support.factories import Factory
from tests.support.http import booking_payload, future_period, problem_of
from tests.support.log_capture import LogCapture
from tests.support.scenarios import build_allocation_scenario
from tests.support.tokens import authorization_header, mint_access_token

ALLOCATIONS_PATH: Final[str] = "/api/allocations"
VALIDATION_FAILED: Final[str] = "api.request_validation_failed"
DOMAIN_ERROR: Final[str] = "api.domain_error"
RULE_PREFIX: Final[str] = "BR-"

YESTERDAY: Final[str] = "2026-03-01"
NINTH: Final[str] = "2026-03-09"
TWELFTH: Final[str] = "2026-03-12"
TWENTY_NINE_DAYS_LATER: Final[str] = "2026-04-07"
NO_SUCH_MODEL: Final[str] = "no-such-model"


@pytest.fixture
def visitor(session: Session) -> Iterator[TestClient]:
    """Yield a client with no credential, on the in memory database."""
    with visitor_client(session) as client:
        yield client


class TestAReadWritesTheRuleAndTheValuesToTheLog:
    """What was taken out of the sentence is written where it is useful."""

    def test_a_refused_period_logs_its_rule_and_the_dates_and_sends_neither(
        self, visitor: TestClient, application_log: LogCapture
    ) -> None:
        response = visitor.get(
            AVAILABILITY_PATH, params={"from": NINTH, "to": TWENTY_NINE_DAYS_LATER}
        )

        line = application_log.only(VALIDATION_FAILED)
        assert line["rule"] == "BR-03"
        assert line["detail"] == {
            "from": NINTH,
            "to": TWENTY_NINE_DAYS_LATER,
            "hire_days": 29,
            "refused_parameter": "to",
        }
        assert line["fields"] == {"query.to": "A hire can be at most 28 days."}
        assert RULE_PREFIX not in response.text
        assert TWENTY_NINE_DAYS_LATER not in json.dumps(problem_of(response)["errors"])

    def test_a_start_in_the_past_logs_the_rule_the_start_and_the_day_it_is(
        self, visitor: TestClient, application_log: LogCapture
    ) -> None:
        response = visitor.get(AVAILABILITY_PATH, params={"from": YESTERDAY, "to": NINTH})

        line = application_log.only(VALIDATION_FAILED)
        assert line["rule"] == "BR-04"
        assert isinstance(line["detail"], dict)
        assert line["detail"]["start_date"] == YESTERDAY
        assert line["detail"]["today"] == "2026-03-02"
        assert RULE_PREFIX not in response.text

    def test_a_refusal_no_single_rule_stands_behind_logs_no_rule(
        self, visitor: TestClient, application_log: LogCapture
    ) -> None:
        visitor.get(MODELS_PATH, params={"category": "no-such-category"})

        line = application_log.only(VALIDATION_FAILED)
        assert line["rule"] is None
        assert line["detail"] == {"category": "no-such-category", "refused_parameter": "category"}

    def test_a_value_the_framework_refused_logs_the_kind_of_refusal_and_not_the_value(
        self, visitor: TestClient, application_log: LogCapture
    ) -> None:
        visitor.get(MODELS_PATH, params={"q": "x", "sort": "cheapest"})

        line = application_log.only(VALIDATION_FAILED)
        assert line["refused_as"] == {"query.q": "string_too_short", "query.sort": "enum"}
        assert "cheapest" not in json.dumps(line)

    def test_a_model_nobody_can_see_logs_the_slug_that_was_asked_for(
        self, visitor: TestClient, application_log: LogCapture
    ) -> None:
        visitor.get(model_quote_path(NO_SUCH_MODEL), params={"from": NINTH, "to": TWELFTH})

        line = application_log.only(DOMAIN_ERROR)
        assert line["code"] == "not-found"
        assert line["detail"] == {"slug": NO_SUCH_MODEL}
        assert line["rule"] is None


class TestABookingIsRefusedInTheSameWords:
    """The period and the booking window are the same rules, so they say the same thing."""

    @pytest.mark.parametrize(
        ("days_ahead", "hire_days", "sentence", "rule"),
        [
            (7, 29, "A hire can be at most 28 days.", "BR-03"),
            (-1, 3, "The hire has to start today or later.", "BR-04"),
            (91, 3, "A hire can start at most 90 days from today.", "BR-05"),
        ],
    )
    def test_a_booking_for_a_refused_period_says_so_plainly_and_logs_the_rule(
        self,
        client: TestClient,
        session: Session,
        factory: Factory,
        application_log: LogCapture,
        days_ahead: int,
        hire_days: int,
        sentence: str,
        rule: str,
    ) -> None:
        scenario = build_allocation_scenario(factory, future_period())
        session.commit()
        start = business_day(datetime.now(UTC)) + timedelta(days=days_ahead)
        payload = booking_payload(
            product_model_id=scenario.product_model.id,
            branch_id=scenario.branch.id,
            period=future_period(),
        )
        payload["startDate"] = start.isoformat()
        payload["endDate"] = (start + timedelta(days=hire_days)).isoformat()

        response = client.post(
            ALLOCATIONS_PATH,
            json=payload,
            headers=authorization_header(mint_access_token(scenario.customer.id)),
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert problem_of(response)["detail"] == sentence
        assert RULE_PREFIX not in response.text
        assert application_log.only(DOMAIN_ERROR)["rule"] == rule
