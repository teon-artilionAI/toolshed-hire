"""`POST /api/auth/register` when it is refused, through HTTP and real SQL (BR-45, C-17, C-26).

I want each refusal here to name the field that was wrong, under
`errors.fields`, and to leave nothing behind. No account, no profile and no
message. The three fields a customer must never set for themselves, the
account status, the role and the trade discount, are refused like any other
unknown field, so none of them can reach the database by being sent.

The route is counted twice, for the address that was typed and for the client
address the request came from, and going over either is a 429 with
`Retry-After`. The clock starts on the hour, so the wait is the whole window.

What an accepted registration does is in tests/api/test_register.py.
"""

from __future__ import annotations

from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from httpx import Response
from sqlmodel import Session, SQLModel, select

from app.application.identity.attempts import (
    ACCOUNT_ATTEMPT_WINDOW,
    ACCOUNT_MAIL_WINDOW,
    REGISTER_ATTEMPTS_PER_ADDRESS,
    REGISTER_ATTEMPTS_PER_EMAIL,
)
from app.infrastructure.models import CustomerProfile, UserAccount
from app.infrastructure.notification import FakeEmailGateway
from tests.support.accounts_api import (
    NEW_EMAIL,
    OMITTED,
    REGISTER_PATH,
    REQUEST_VALIDATION_PROBLEM,
    account_client,
    registration_body,
)
from tests.support.clock import FixedClock
from tests.support.http import problem_code, problem_of
from tests.support.sessions import SHARED_REQUEST_ID, TOO_MANY_ATTEMPTS_PROBLEM

RETRY_AFTER_HEADER: Final[str] = "Retry-After"
CLIENT_ADDRESS: Final[str] = "203.0.113.9"
OTHER_CLIENT_ADDRESS: Final[str] = "198.51.100.20"
# Eleven characters, one short of the rule.
SHORT_PASSWORD: Final[str] = "a-too-short"
MAIL_WINDOW_SECONDS: Final[int] = int(ACCOUNT_MAIL_WINDOW.total_seconds())
ATTEMPT_WINDOW_SECONDS: Final[int] = int(ACCOUNT_ATTEMPT_WINDOW.total_seconds())

REFUSED_FIELDS: Final = [
    pytest.param("email", {"email": "not-an-address"}, id="email shape"),
    pytest.param("password", {"password": SHORT_PASSWORD}, id="short password"),
    pytest.param("fullName", {"fullName": OMITTED}, id="missing full name"),
    pytest.param("idDocumentType", {"idDocumentType": "NATIONAL_ID"}, id="document type"),
    pytest.param("idDocumentLast4", {"idDocumentLast4": "50834"}, id="five characters"),
    pytest.param("idDocumentLast4", {"idDocumentLast4": "50-3"}, id="not letters or digits"),
    pytest.param("acceptsPrivacyNotice", {"acceptsPrivacyNotice": False}, id="privacy notice"),
    pytest.param("homeBranchCode", {"homeBranchCode": "ZZZ"}, id="unknown branch"),
    pytest.param("phone", {"phone": "not a phone"}, id="phone shape"),
]
FORBIDDEN_FIELDS: Final = [
    pytest.param("accountStatus", "ACTIVE", id="account status"),
    pytest.param("role", "ADMIN", id="role"),
    pytest.param("tradeDiscountPercent", "25.00", id="trade discount"),
]


def _register(client: TestClient, **overrides: object) -> Response:
    """Post a registration that is accepted unless an override says otherwise."""
    body = registration_body(**overrides)
    return client.post(REGISTER_PATH, json=body, headers=SHARED_REQUEST_ID)


def _rows[Row: SQLModel](session: Session, model: type[Row]) -> list[Row]:
    """Return every row of one table as it is stored now."""
    return list(session.exec(select(model)).all())


def _refused_fields(response: Response) -> set[str]:
    """Return the names a 422 gives under `errors.fields`."""
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert problem_code(response) == REQUEST_VALIDATION_PROBLEM
    errors = problem_of(response)["errors"]
    assert isinstance(errors, dict)
    return set(errors["fields"])


def _assert_throttled(response: Response, wait_seconds: int) -> None:
    """Check a response is the 429 of a throttle, with the given wait."""
    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert problem_code(response) == TOO_MANY_ATTEMPTS_PROBLEM
    assert response.headers[RETRY_AFTER_HEADER] == str(wait_seconds)


@pytest.mark.usefixtures("home_branch")
class TestRefusedFields:
    """Each refused field is named under `errors.fields`, and nothing is written."""

    @pytest.mark.parametrize(("field", "override"), REFUSED_FIELDS)
    def test_a_field_that_breaks_its_rule_is_named(
        self,
        account_api: TestClient,
        session: Session,
        email_gateway: FakeEmailGateway,
        field: str,
        override: dict[str, object],
    ) -> None:
        response = _register(account_api, **override)
        assert _refused_fields(response) == {f"body.{field}"}
        assert _rows(session, UserAccount) == []
        assert _rows(session, CustomerProfile) == []
        assert email_gateway.sent == []

    @pytest.mark.parametrize(("field", "value"), FORBIDDEN_FIELDS)
    def test_a_field_a_customer_may_not_set_is_refused_by_name(
        self,
        account_api: TestClient,
        session: Session,
        email_gateway: FakeEmailGateway,
        field: str,
        value: str,
    ) -> None:
        response = _register(account_api, **{field: value})
        assert _refused_fields(response) == {f"body.{field}"}
        assert _rows(session, UserAccount) == []
        assert _rows(session, CustomerProfile) == []
        assert email_gateway.sent == []


@pytest.mark.usefixtures("home_branch")
class TestTheThrottles:
    """Five registrations naming one address an hour, ten from one client address (C-17)."""

    def test_the_sixth_registration_naming_one_address_in_an_hour_is_429(
        self, account_api: TestClient, email_gateway: FakeEmailGateway
    ) -> None:
        for _ in range(REGISTER_ATTEMPTS_PER_EMAIL):
            assert _register(account_api).status_code == status.HTTP_202_ACCEPTED
        _assert_throttled(_register(account_api), MAIL_WINDOW_SECONDS)
        assert len(email_gateway.sent_to(NEW_EMAIL)) == REGISTER_ATTEMPTS_PER_EMAIL

    def test_the_address_is_counted_whatever_its_case(self, account_api: TestClient) -> None:
        for _ in range(REGISTER_ATTEMPTS_PER_EMAIL):
            _register(account_api)
        _assert_throttled(_register(account_api, email=NEW_EMAIL.upper()), MAIL_WINDOW_SECONDS)

    def test_the_eleventh_registration_from_one_client_address_is_429(
        self, session: Session, still_clock: FixedClock, email_gateway: FakeEmailGateway
    ) -> None:
        with account_client(
            session, still_clock, email_gateway, client_address=CLIENT_ADDRESS
        ) as client:
            for number in range(REGISTER_ATTEMPTS_PER_ADDRESS):
                response = _register(client, email=f"person{number}@example.co.za")
                assert response.status_code == status.HTTP_202_ACCEPTED
            throttled = _register(client, email="one.more@example.co.za")
        _assert_throttled(throttled, ATTEMPT_WINDOW_SECONDS)
        assert len(_rows(session, UserAccount)) == REGISTER_ATTEMPTS_PER_ADDRESS

    def test_a_second_client_address_is_not_held_up(
        self, session: Session, still_clock: FixedClock, email_gateway: FakeEmailGateway
    ) -> None:
        with account_client(
            session, still_clock, email_gateway, client_address=CLIENT_ADDRESS
        ) as client:
            for number in range(REGISTER_ATTEMPTS_PER_ADDRESS + 1):
                _register(client, email=f"person{number}@example.co.za")
        with account_client(
            session, still_clock, email_gateway, client_address=OTHER_CLIENT_ADDRESS
        ) as elsewhere:
            response = _register(elsewhere, email="from.elsewhere@example.co.za")
        assert response.status_code == status.HTTP_202_ACCEPTED
