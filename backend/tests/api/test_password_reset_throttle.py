"""The throttles of the password reset, through HTTP and real SQL (C-17).

A request for a reset link is counted for the address it names, five in an
hour, and for the client address it came from, ten in fifteen minutes. A
completion is counted for the client address, ten in fifteen minutes. One too
many is a 429 with `Retry-After` in seconds, and nothing is looked up, sent or
redeemed for it.

The fixed clock starts on the hour, which is the start of every window, so the
wait is a whole window. A bare test client has no address and counts under one
shared window, so the tests about a client address build a client that has one.
The rest of the reset is in test_password_reset.py.
"""

from __future__ import annotations

from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from httpx import Response
from sqlmodel import Session

from app.application.identity.attempts import (
    ACCOUNT_ATTEMPT_WINDOW,
    ACCOUNT_MAIL_WINDOW,
    RESET_COMPLETIONS_PER_ADDRESS,
    RESET_REQUESTS_PER_ADDRESS,
    RESET_REQUESTS_PER_EMAIL,
)
from app.infrastructure.models import UserAccount
from app.infrastructure.notification import FakeEmailGateway
from tests.support.accounts_api import (
    NEW_PASSWORD,
    RESET_COMPLETE_PATH,
    RESET_KEY,
    RESET_LINK_INVALID_PROBLEM,
    RESET_REQUEST_PATH,
    account_client,
    token_from,
)
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.http import problem_code
from tests.support.sessions import SHARED_REQUEST_ID, TOO_MANY_ATTEMPTS_PROBLEM

RETRY_AFTER_HEADER: Final[str] = "Retry-After"
CLIENT_ADDRESS: Final[str] = "203.0.113.9"
OTHER_CLIENT_ADDRESS: Final[str] = "198.51.100.20"
MAIL_WINDOW_SECONDS: Final[int] = int(ACCOUNT_MAIL_WINDOW.total_seconds())
ATTEMPT_WINDOW_SECONDS: Final[int] = int(ACCOUNT_ATTEMPT_WINDOW.total_seconds())
UNKNOWN_TOKEN: Final[str] = "a-made-up-reset-token-nobody-was-sent"


@pytest.fixture
def customer(session: Session, factory: Factory) -> UserAccount:
    """Return a committed, active customer account."""
    account = factory.user()
    session.commit()
    return account


def ask_for_reset(client: TestClient, email: str) -> Response:
    """Ask for a reset link for an address, with the shared request id."""
    return client.post(RESET_REQUEST_PATH, json={"email": email}, headers=SHARED_REQUEST_ID)


def complete_reset(client: TestClient, token: str) -> Response:
    """Choose a new password with the token of a reset link, with the shared request id."""
    return client.post(
        RESET_COMPLETE_PATH,
        json={"token": token, "newPassword": NEW_PASSWORD},
        headers=SHARED_REQUEST_ID,
    )


def stranger(number: int) -> str:
    """Return an address that has no account, a different one for each number."""
    return f"stranger{number}@example.co.za"


def assert_throttled(response: Response, wait_seconds: int) -> None:
    """Check a response is the 429 of a throttle, with the wait in `Retry-After`."""
    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert problem_code(response) == TOO_MANY_ATTEMPTS_PROBLEM
    assert response.headers[RETRY_AFTER_HEADER] == str(wait_seconds)


class TestTheRequestThrottles:
    """Five requests for one address in an hour and ten from one client in fifteen minutes."""

    def test_the_sixth_request_for_one_address_in_an_hour_is_429_and_sends_nothing(
        self, account_api: TestClient, email_gateway: FakeEmailGateway, customer: UserAccount
    ) -> None:
        for _ in range(RESET_REQUESTS_PER_EMAIL):
            accepted = ask_for_reset(account_api, customer.email)
            assert accepted.status_code == status.HTTP_202_ACCEPTED
        assert_throttled(ask_for_reset(account_api, customer.email), MAIL_WINDOW_SECONDS)
        assert len(email_gateway.sent_to(customer.email)) == RESET_REQUESTS_PER_EMAIL

    def test_the_address_is_counted_whatever_its_case(
        self, account_api: TestClient, customer: UserAccount
    ) -> None:
        for _ in range(RESET_REQUESTS_PER_EMAIL):
            ask_for_reset(account_api, customer.email)
        throttled = ask_for_reset(account_api, customer.email.upper())
        assert_throttled(throttled, MAIL_WINDOW_SECONDS)

    def test_the_eleventh_request_from_one_client_address_is_429(
        self, session: Session, still_clock: FixedClock, email_gateway: FakeEmailGateway
    ) -> None:
        with account_client(
            session, still_clock, email_gateway, client_address=CLIENT_ADDRESS
        ) as client:
            for number in range(RESET_REQUESTS_PER_ADDRESS):
                accepted = ask_for_reset(client, stranger(number))
                assert accepted.status_code == status.HTTP_202_ACCEPTED
            throttled = ask_for_reset(client, "one.more@example.co.za")
        assert_throttled(throttled, ATTEMPT_WINDOW_SECONDS)

    def test_a_second_client_address_is_not_held_up(
        self, session: Session, still_clock: FixedClock, email_gateway: FakeEmailGateway
    ) -> None:
        with account_client(
            session, still_clock, email_gateway, client_address=CLIENT_ADDRESS
        ) as client:
            for number in range(RESET_REQUESTS_PER_ADDRESS + 1):
                ask_for_reset(client, stranger(number))
        with account_client(
            session, still_clock, email_gateway, client_address=OTHER_CLIENT_ADDRESS
        ) as elsewhere:
            response = ask_for_reset(elsewhere, "from.elsewhere@example.co.za")
        assert response.status_code == status.HTTP_202_ACCEPTED


class TestTheCompletionThrottle:
    """Ten completions from one client address in fifteen minutes, and then a wait."""

    def test_the_eleventh_completion_from_one_client_address_is_429_even_with_a_good_link(
        self,
        session: Session,
        still_clock: FixedClock,
        email_gateway: FakeEmailGateway,
        customer: UserAccount,
    ) -> None:
        with account_client(
            session, still_clock, email_gateway, client_address=CLIENT_ADDRESS
        ) as client:
            assert ask_for_reset(client, customer.email).status_code == status.HTTP_202_ACCEPTED
            token = token_from(email_gateway, customer.email, RESET_KEY)
            for number in range(RESET_COMPLETIONS_PER_ADDRESS):
                refused = complete_reset(client, f"{UNKNOWN_TOKEN}-{number}")
                assert problem_code(refused) == RESET_LINK_INVALID_PROBLEM
            throttled = complete_reset(client, token)
        assert_throttled(throttled, ATTEMPT_WINDOW_SECONDS)
        session.refresh(customer)
        assert customer.password_reset_token_hash is not None

    def test_the_wait_ends_with_the_window(
        self,
        session: Session,
        still_clock: FixedClock,
        email_gateway: FakeEmailGateway,
        customer: UserAccount,
    ) -> None:
        with account_client(
            session, still_clock, email_gateway, client_address=CLIENT_ADDRESS
        ) as client:
            ask_for_reset(client, customer.email)
            token = token_from(email_gateway, customer.email, RESET_KEY)
            for number in range(RESET_COMPLETIONS_PER_ADDRESS + 1):
                complete_reset(client, f"{UNKNOWN_TOKEN}-{number}")
            still_clock.advance(ACCOUNT_ATTEMPT_WINDOW)
            completed = complete_reset(client, token)
        assert completed.status_code == status.HTTP_204_NO_CONTENT
