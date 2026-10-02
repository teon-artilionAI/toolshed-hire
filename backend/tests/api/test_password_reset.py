"""The password reset, through `POST /api/auth/password-reset/*`, HTTP and real SQL (US-04, C-18).

I ask for a reset link and redeem it the way a person does, by reading the
token out of the link in the message the fake gateway kept. The request
answers the same way for an address with an account, an address without one
and a deactivated account, so the answer cannot be used to find out who has
an account here (C-14). Only an active account is sent a link.

Redeeming the link sets the new password, ends every refresh session of the
account and lifts any lock. A link that is unknown, already used or more than
sixty minutes old is refused with one document for all three, and a second
request replaces the link of the first.

The rules are proved without HTTP in tests/unit/test_password_reset_use_cases.py.
This file keeps to what the routes, the messages and the rows can show. The
throttles of both halves are in test_password_reset_throttle.py.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from httpx import Response
from sqlmodel import Session, col, select

from app.domain.account import LOCKOUT_DURATION, MAXIMUM_FAILED_LOGINS
from app.domain.enums import RevokeReason
from app.infrastructure.models import RefreshSession, UserAccount
from app.infrastructure.notification import FakeEmailGateway
from tests.support.accounts_api import (
    NEW_PASSWORD,
    REQUEST_VALIDATION_PROBLEM,
    RESET_COMPLETE_PATH,
    RESET_KEY,
    RESET_LINK_INVALID_PROBLEM,
    RESET_REQUEST_PATH,
    token_from,
)
from tests.support.clock import FixedClock
from tests.support.factories import TEST_PASSWORD, Factory
from tests.support.http import problem_code, problem_of
from tests.support.sessions import (
    REFRESH_PATH,
    SESSION_EXPIRED_PROBLEM,
    SHARED_REQUEST_ID,
    UNKNOWN_EMAIL,
    present,
    refresh_token_of,
    sign_in,
)

# Where a reset link points in the test environment, which sets no FRONTEND_ORIGIN.
RESET_LINK_START: Final[str] = "http://localhost:5173/signin#reset="
RESET_LINK_LIFETIME: Final[timedelta] = timedelta(minutes=60)
ONE_SECOND: Final[timedelta] = timedelta(seconds=1)
# Eleven characters, one short of the twelve the password rule asks for.
SHORT_PASSWORD: Final[str] = "short-pass1"
UNKNOWN_TOKEN: Final[str] = "a-made-up-reset-token-nobody-was-sent"
TOKEN_ENCODING: Final[str] = "utf-8"


@pytest.fixture
def customer(session: Session, factory: Factory) -> UserAccount:
    """Return a committed, active customer account whose password is the test password."""
    account = factory.user()
    session.commit()
    return account


def ask_for_reset(client: TestClient, email: str) -> Response:
    """Ask for a reset link for an address, with the shared request id."""
    return client.post(RESET_REQUEST_PATH, json={"email": email}, headers=SHARED_REQUEST_ID)


def complete_reset(client: TestClient, token: str, new_password: str = NEW_PASSWORD) -> Response:
    """Choose a new password with the token of a reset link, with the shared request id."""
    return client.post(
        RESET_COMPLETE_PATH,
        json={"token": token, "newPassword": new_password},
        headers=SHARED_REQUEST_ID,
    )


def reset_token(client: TestClient, gateway: FakeEmailGateway, email: str) -> str:
    """Ask for a reset link and return the token the message carried."""
    assert ask_for_reset(client, email).status_code == status.HTTP_202_ACCEPTED
    return token_from(gateway, email, RESET_KEY)


def stored(session: Session, account: UserAccount) -> UserAccount:
    """Return the account row as the database now holds it."""
    session.refresh(account)
    return account


def assert_link_refused(response: Response) -> None:
    """Check a completion was refused as a link that is not valid, and said nothing more."""
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert problem_code(response) == RESET_LINK_INVALID_PROBLEM
    problem = problem_of(response)
    assert isinstance(problem["detail"], str)
    assert problem["detail"]
    assert "errors" not in problem


class TestTheRequestSaysNothingAboutTheAddress:
    """202 and the same body whether or not the address has an account (C-14)."""

    def test_a_known_and_an_unknown_address_are_answered_alike(
        self, account_api: TestClient, customer: UserAccount
    ) -> None:
        known = ask_for_reset(account_api, customer.email)
        unknown = ask_for_reset(account_api, UNKNOWN_EMAIL)
        assert known.status_code == status.HTTP_202_ACCEPTED
        assert unknown.status_code == status.HTTP_202_ACCEPTED
        assert known.content == unknown.content
        assert known.json().keys() == {"emailDeliverable"}

    def test_only_the_known_address_is_sent_a_link_and_it_opens_the_sign_in_screen(
        self, account_api: TestClient, email_gateway: FakeEmailGateway, customer: UserAccount
    ) -> None:
        ask_for_reset(account_api, customer.email)
        ask_for_reset(account_api, UNKNOWN_EMAIL)
        (message,) = email_gateway.sent_to(customer.email)
        token = token_from(email_gateway, customer.email, RESET_KEY)
        assert f"{RESET_LINK_START}{token}" in message.text_body
        assert email_gateway.sent_to(UNKNOWN_EMAIL) == []
        assert len(email_gateway.sent) == 1

    def test_the_token_is_stored_as_its_sha256_and_never_as_itself(
        self,
        account_api: TestClient,
        email_gateway: FakeEmailGateway,
        session: Session,
        customer: UserAccount,
        still_clock: FixedClock,
    ) -> None:
        token = reset_token(account_api, email_gateway, customer.email)
        row = stored(session, customer)
        expected_hash = hashlib.sha256(token.encode(TOKEN_ENCODING)).hexdigest()
        assert row.password_reset_token_hash == expected_hash
        assert token not in str(row.model_dump())
        assert row.password_reset_expires_at is not None
        expected_end = still_clock.now() + RESET_LINK_LIFETIME
        assert row.password_reset_expires_at.replace(tzinfo=None) == expected_end.replace(
            tzinfo=None
        )

    def test_a_deactivated_account_is_answered_alike_and_sent_nothing(
        self,
        account_api: TestClient,
        email_gateway: FakeEmailGateway,
        session: Session,
        factory: Factory,
    ) -> None:
        deactivated = factory.user(is_active=False)
        session.commit()
        answered = ask_for_reset(account_api, deactivated.email)
        unknown = ask_for_reset(account_api, UNKNOWN_EMAIL)
        assert answered.status_code == status.HTTP_202_ACCEPTED
        assert answered.content == unknown.content
        assert email_gateway.sent == []
        assert stored(session, deactivated).password_reset_token_hash is None


class TestCompletingTheReset:
    """204, the new password, no session left open and no lock left in place."""

    def test_the_new_password_signs_in_and_the_old_one_is_refused(
        self, account_api: TestClient, email_gateway: FakeEmailGateway, customer: UserAccount
    ) -> None:
        token = reset_token(account_api, email_gateway, customer.email)
        completed = complete_reset(account_api, token)
        assert completed.status_code == status.HTTP_204_NO_CONTENT
        assert completed.content == b""
        assert sign_in(account_api, customer.email, NEW_PASSWORD).status_code == status.HTTP_200_OK
        old = sign_in(account_api, customer.email, TEST_PASSWORD)
        assert old.status_code == status.HTTP_401_UNAUTHORIZED

    def test_every_refresh_session_of_the_account_is_revoked(
        self,
        account_api: TestClient,
        email_gateway: FakeEmailGateway,
        session: Session,
        customer: UserAccount,
    ) -> None:
        old_cookies = [refresh_token_of(sign_in(account_api, customer.email)) for _ in range(2)]
        token = reset_token(account_api, email_gateway, customer.email)
        assert complete_reset(account_api, token).status_code == status.HTTP_204_NO_CONTENT
        session.expire_all()
        rows = session.exec(
            select(RefreshSession).where(col(RefreshSession.user_account_id) == customer.id)
        ).all()
        assert len(rows) == len(old_cookies)
        assert all(row.revoked_at is not None for row in rows)
        assert {row.revoked_reason for row in rows} == {RevokeReason.LOGOUT}
        for old_cookie in old_cookies:
            refused = present(account_api, REFRESH_PATH, old_cookie)
            assert refused.status_code == status.HTTP_401_UNAUTHORIZED
            assert problem_code(refused) == SESSION_EXPIRED_PROBLEM

    def test_it_lifts_a_lockout(
        self,
        account_api: TestClient,
        email_gateway: FakeEmailGateway,
        session: Session,
        customer: UserAccount,
        still_clock: FixedClock,
    ) -> None:
        customer.failed_login_count = MAXIMUM_FAILED_LOGINS
        customer.locked_until = still_clock.now() + LOCKOUT_DURATION
        session.add(customer)
        session.commit()
        token = reset_token(account_api, email_gateway, customer.email)
        assert complete_reset(account_api, token).status_code == status.HTTP_204_NO_CONTENT
        row = stored(session, customer)
        assert row.failed_login_count == 0
        assert row.locked_until is None
        assert sign_in(account_api, customer.email, NEW_PASSWORD).status_code == status.HTTP_200_OK


class TestALinkThatIsNotValid:
    """400 with one document for a link that is unknown, used or out of time."""

    def test_an_unknown_link_is_answered_400(self, account_api: TestClient) -> None:
        assert_link_refused(complete_reset(account_api, UNKNOWN_TOKEN))

    def test_a_used_link_is_answered_400_exactly_as_an_unknown_one(
        self, account_api: TestClient, email_gateway: FakeEmailGateway, customer: UserAccount
    ) -> None:
        token = reset_token(account_api, email_gateway, customer.email)
        assert complete_reset(account_api, token).status_code == status.HTTP_204_NO_CONTENT
        used = complete_reset(account_api, token, "a-third-made-up-passphrase")
        assert_link_refused(used)
        assert used.content == complete_reset(account_api, UNKNOWN_TOKEN).content

    def test_a_link_past_its_sixty_minutes_is_answered_400_exactly_as_an_unknown_one(
        self,
        account_api: TestClient,
        email_gateway: FakeEmailGateway,
        customer: UserAccount,
        still_clock: FixedClock,
    ) -> None:
        token = reset_token(account_api, email_gateway, customer.email)
        still_clock.advance(RESET_LINK_LIFETIME + ONE_SECOND)
        expired = complete_reset(account_api, token)
        assert_link_refused(expired)
        assert expired.content == complete_reset(account_api, UNKNOWN_TOKEN).content

    def test_a_link_is_still_accepted_a_second_before_its_sixty_minutes_are_up(
        self,
        account_api: TestClient,
        email_gateway: FakeEmailGateway,
        customer: UserAccount,
        still_clock: FixedClock,
    ) -> None:
        token = reset_token(account_api, email_gateway, customer.email)
        still_clock.advance(RESET_LINK_LIFETIME - ONE_SECOND)
        assert complete_reset(account_api, token).status_code == status.HTTP_204_NO_CONTENT

    def test_a_password_under_twelve_characters_is_422_and_leaves_the_link_usable(
        self, account_api: TestClient, email_gateway: FakeEmailGateway, customer: UserAccount
    ) -> None:
        token = reset_token(account_api, email_gateway, customer.email)
        refused = complete_reset(account_api, token, SHORT_PASSWORD)
        assert refused.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert problem_code(refused) == REQUEST_VALIDATION_PROBLEM
        errors = problem_of(refused)["errors"]
        assert isinstance(errors, dict)
        assert "body.newPassword" in errors["fields"]
        assert complete_reset(account_api, token).status_code == status.HTTP_204_NO_CONTENT

    def test_a_second_request_replaces_the_first_link(
        self, account_api: TestClient, email_gateway: FakeEmailGateway, customer: UserAccount
    ) -> None:
        first = reset_token(account_api, email_gateway, customer.email)
        second = reset_token(account_api, email_gateway, customer.email)
        assert first != second
        assert_link_refused(complete_reset(account_api, first))
        assert complete_reset(account_api, second).status_code == status.HTTP_204_NO_CONTENT
