"""The verification link and the request to send it again, through HTTP (US-02, BR-47, C-18).

I read every token here out of the link in the message a person would have
been sent, as they would. A token that is still in time proves the address
once, and `GET /api/me` then says so. A token that is unknown, already used or
a day old is answered 400 in the same bytes for all three, so the answer does
not say which it was. Presenting a token is counted per client address, before
the token is looked at.

Asking for the link again is for any signed in account. It sends a new link
that replaces the old one, sends nothing for an address that is already
verified while answering in the same bytes, and is counted per account.
"""

from __future__ import annotations

from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from httpx import Response
from sqlmodel import Session, col, select

from app.application.identity.attempts import (
    ACCOUNT_ATTEMPT_WINDOW,
    ACCOUNT_MAIL_WINDOW,
    VERIFICATION_ATTEMPTS_PER_ADDRESS,
    VERIFICATION_RESENDS_PER_ACCOUNT,
)
from app.application.identity.email_verification import EMAIL_VERIFIED_ACTION
from app.domain.account_tokens import EMAIL_VERIFICATION_LIFETIME, hash_account_token
from app.domain.enums import UserRole
from app.infrastructure.models import AuditEvent, UserAccount
from app.infrastructure.notification import FakeEmailGateway
from tests.support.accounts_api import (
    NEW_EMAIL,
    REGISTER_PATH,
    REQUEST_VALIDATION_PROBLEM,
    RESEND_PATH,
    VERIFICATION_LINK_INVALID_PROBLEM,
    VERIFY_KEY,
    VERIFY_PATH,
    account_client,
    registration_body,
    token_from,
)
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.http import problem_code, problem_of
from tests.support.sessions import ME_PATH, SHARED_REQUEST_ID, TOO_MANY_ATTEMPTS_PROBLEM
from tests.support.tokens import authorization_header, mint_access_token

RETRY_AFTER_HEADER: Final[str] = "Retry-After"
CLIENT_ADDRESS: Final[str] = "203.0.113.9"
LATE_EMAIL: Final[str] = "opened.the.message.late@example.co.za"
UNKNOWN_TOKEN: Final[str] = "a-made-up-token-nobody-was-ever-sent"
DELIVERABLE: Final[dict[str, bool]] = {"emailDeliverable": True}
MAIL_WINDOW_SECONDS: Final[int] = int(ACCOUNT_MAIL_WINDOW.total_seconds())
ATTEMPT_WINDOW_SECONDS: Final[int] = int(ACCOUNT_ATTEMPT_WINDOW.total_seconds())
MISSING_TOKEN_BODIES: Final = [
    pytest.param({}, id="missing"),
    pytest.param({"token": ""}, id="empty"),
]


def _registered_token(
    client: TestClient, gateway: FakeEmailGateway, email: str = NEW_EMAIL
) -> str:
    """Register a customer and return the token of the link they were sent."""
    body = registration_body(email=email)
    response = client.post(REGISTER_PATH, json=body, headers=SHARED_REQUEST_ID)
    assert response.status_code == status.HTTP_202_ACCEPTED
    return token_from(gateway, email, VERIFY_KEY)


def _verify(client: TestClient, token: str) -> Response:
    """Present a verification token, with the shared request id."""
    return client.post(VERIFY_PATH, json={"token": token}, headers=SHARED_REQUEST_ID)


def _signed_in(account: UserAccount, clock: FixedClock) -> dict[str, str]:
    """Return the headers of a request by this account, signed in at the time of the clock."""
    access_token = mint_access_token(
        account.id, role=account.role, branch_id=account.branch_id, issued_at=clock.now()
    )
    return {**SHARED_REQUEST_ID, **authorization_header(access_token)}


def _resend(client: TestClient, account: UserAccount, clock: FixedClock) -> Response:
    """Ask for the link again, signed in as this account."""
    return client.post(RESEND_PATH, headers=_signed_in(account, clock))


def _new_customer(session: Session) -> UserAccount:
    """Return the account of the customer who registered, as it is stored now."""
    return session.exec(select(UserAccount).where(col(UserAccount.email) == NEW_EMAIL)).one()


def _assert_link_invalid(response: Response) -> None:
    """Check a response is the 400 of a link that is not valid."""
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert problem_code(response) == VERIFICATION_LINK_INVALID_PROBLEM


def _assert_throttled(response: Response, wait_seconds: int) -> None:
    """Check a response is the 429 of a throttle, with the given wait."""
    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert problem_code(response) == TOO_MANY_ATTEMPTS_PROBLEM
    assert response.headers[RETRY_AFTER_HEADER] == str(wait_seconds)


@pytest.mark.usefixtures("home_branch")
class TestPresentingALink:
    """204 once for a token in time, and one 400 for every other token."""

    def test_a_valid_token_is_answered_204_and_the_address_is_then_verified(
        self,
        account_api: TestClient,
        session: Session,
        email_gateway: FakeEmailGateway,
        still_clock: FixedClock,
    ) -> None:
        response = _verify(account_api, _registered_token(account_api, email_gateway))
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.content == b""
        account = _new_customer(session)
        me = account_api.get(ME_PATH, headers=_signed_in(account, still_clock))
        assert me.status_code == status.HTTP_200_OK
        assert me.json()["emailVerified"] is True
        assert account.email_verified_at is not None
        verified_at = account.email_verified_at.replace(tzinfo=None)
        assert verified_at == still_clock.now().replace(tzinfo=None)
        assert account.email_verification_token_hash is None
        events = session.exec(
            select(AuditEvent).where(col(AuditEvent.action) == EMAIL_VERIFIED_ACTION)
        ).all()
        assert [event.entity_id for event in events] == [account.id]

    def test_an_unknown_token_is_answered_400(self, account_api: TestClient) -> None:
        _assert_link_invalid(_verify(account_api, UNKNOWN_TOKEN))

    def test_a_token_is_refused_the_second_time_it_is_presented(
        self, account_api: TestClient, email_gateway: FakeEmailGateway
    ) -> None:
        token = _registered_token(account_api, email_gateway)
        assert _verify(account_api, token).status_code == status.HTTP_204_NO_CONTENT
        _assert_link_invalid(_verify(account_api, token))

    def test_a_token_presented_when_its_day_is_up_is_refused(
        self,
        account_api: TestClient,
        session: Session,
        email_gateway: FakeEmailGateway,
        still_clock: FixedClock,
    ) -> None:
        token = _registered_token(account_api, email_gateway)
        still_clock.advance(EMAIL_VERIFICATION_LIFETIME)
        _assert_link_invalid(_verify(account_api, token))
        assert _new_customer(session).email_verified_at is None

    def test_unknown_used_and_expired_tokens_are_answered_in_the_same_bytes(
        self, account_api: TestClient, email_gateway: FakeEmailGateway, still_clock: FixedClock
    ) -> None:
        used = _registered_token(account_api, email_gateway)
        late = _registered_token(account_api, email_gateway, LATE_EMAIL)
        _verify(account_api, used)
        unknown = _verify(account_api, UNKNOWN_TOKEN)
        used_again = _verify(account_api, used)
        still_clock.advance(EMAIL_VERIFICATION_LIFETIME)
        expired = _verify(account_api, late)
        refusals = (unknown, used_again, expired)
        for response in refusals:
            _assert_link_invalid(response)
        assert len({response.content for response in refusals}) == 1, "The bodies differ."

    @pytest.mark.parametrize("body", MISSING_TOKEN_BODIES)
    def test_a_missing_or_empty_token_is_422_naming_the_token(
        self, account_api: TestClient, body: dict[str, str]
    ) -> None:
        response = account_api.post(VERIFY_PATH, json=body, headers=SHARED_REQUEST_ID)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert problem_code(response) == REQUEST_VALIDATION_PROBLEM
        errors = problem_of(response)["errors"]
        assert isinstance(errors, dict)
        assert set(errors["fields"]) == {"body.token"}

    def test_the_twenty_first_presentation_from_one_client_address_is_429(
        self, session: Session, still_clock: FixedClock, email_gateway: FakeEmailGateway
    ) -> None:
        with account_client(
            session, still_clock, email_gateway, client_address=CLIENT_ADDRESS
        ) as client:
            token = _registered_token(client, email_gateway)
            for _ in range(VERIFICATION_ATTEMPTS_PER_ADDRESS):
                _assert_link_invalid(_verify(client, UNKNOWN_TOKEN))
            throttled = _verify(client, token)
        _assert_throttled(throttled, ATTEMPT_WINDOW_SECONDS)
        assert _new_customer(session).email_verified_at is None


class TestSendingTheLinkAgain:
    """202 for any signed in role, a link that replaces the last one, counted per account."""

    def test_an_unverified_customer_is_answered_202_and_sent_a_new_link(
        self,
        account_api: TestClient,
        session: Session,
        factory: Factory,
        still_clock: FixedClock,
        email_gateway: FakeEmailGateway,
    ) -> None:
        customer = factory.user(role=UserRole.CUSTOMER)
        session.commit()
        response = _resend(account_api, customer, still_clock)
        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.json() == DELIVERABLE
        token = token_from(email_gateway, customer.email, VERIFY_KEY)
        session.refresh(customer)
        assert customer.email_verification_token_hash == hash_account_token(token)

    @pytest.mark.usefixtures("home_branch")
    def test_the_new_link_works_and_the_one_before_it_is_refused(
        self,
        account_api: TestClient,
        session: Session,
        still_clock: FixedClock,
        email_gateway: FakeEmailGateway,
    ) -> None:
        first = _registered_token(account_api, email_gateway)
        resent = _resend(account_api, _new_customer(session), still_clock)
        assert resent.status_code == status.HTTP_202_ACCEPTED
        second = token_from(email_gateway, NEW_EMAIL, VERIFY_KEY)
        assert second != first
        _assert_link_invalid(_verify(account_api, first))
        assert _verify(account_api, second).status_code == status.HTTP_204_NO_CONTENT

    def test_a_verified_account_gets_the_same_answer_and_no_message(
        self,
        account_api: TestClient,
        session: Session,
        factory: Factory,
        still_clock: FixedClock,
        email_gateway: FakeEmailGateway,
    ) -> None:
        verified, unverified = factory.user(), factory.user()
        verified.email_verified_at = still_clock.now()
        session.commit()
        answered = _resend(account_api, verified, still_clock)
        reference = _resend(account_api, unverified, still_clock)
        assert answered.status_code == reference.status_code == status.HTTP_202_ACCEPTED
        assert answered.content == reference.content
        assert email_gateway.sent_to(verified.email) == []
        assert len(email_gateway.sent_to(unverified.email)) == 1

    def test_a_request_without_a_credential_is_401(self, account_api: TestClient) -> None:
        response = account_api.post(RESEND_PATH, headers=SHARED_REQUEST_ID)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert problem_of(response)["status"] == status.HTTP_401_UNAUTHORIZED

    def test_the_sixth_request_by_one_account_in_an_hour_is_429(
        self,
        account_api: TestClient,
        session: Session,
        factory: Factory,
        still_clock: FixedClock,
        email_gateway: FakeEmailGateway,
    ) -> None:
        customer, other = factory.user(), factory.user()
        session.commit()
        for _ in range(VERIFICATION_RESENDS_PER_ACCOUNT):
            accepted = _resend(account_api, customer, still_clock)
            assert accepted.status_code == status.HTTP_202_ACCEPTED
        _assert_throttled(_resend(account_api, customer, still_clock), MAIL_WINDOW_SECONDS)
        assert len(email_gateway.sent_to(customer.email)) == VERIFICATION_RESENDS_PER_ACCOUNT
        assert _resend(account_api, other, still_clock).status_code == status.HTTP_202_ACCEPTED

    def test_counter_staff_may_ask_as_well(
        self,
        account_api: TestClient,
        session: Session,
        factory: Factory,
        still_clock: FixedClock,
    ) -> None:
        assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=factory.branch())
        session.commit()
        response = _resend(account_api, assistant, still_clock)
        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.json() == DELIVERABLE
