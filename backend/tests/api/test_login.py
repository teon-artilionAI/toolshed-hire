"""`POST /api/auth/login`, through HTTP and real SQL (BR-45, BR-46, BR-48, C-14).

The contract is fixed. A good sign in answers 200 with the access token in the
body and the refresh token in a cookie. A wrong password, an unknown address,
a locked account and a deactivated account answer with the same 401, byte for
byte. The fifth failure locks the account and the lock ends fifteen minutes
later, which the tests reach by moving the clock.

Every sign in here runs the real bcrypt at work factor 12. The rules are
proved in full without it in tests/unit/test_sign_in_use_case.py, so this file
keeps to what only HTTP and SQL can show.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

import jwt
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.api.refresh_cookie import REFRESH_COOKIE_NAME, SET_COOKIE_HEADER
from app.application.identity.sign_in import LOGIN_FAILED_ACTION, LOGIN_SUCCEEDED_ACTION
from app.domain.account import LOCKOUT_DURATION, MAXIMUM_FAILED_LOGINS
from app.domain.enums import UserRole
from app.domain.session import hash_refresh_token
from app.infrastructure.models import AuditEvent, RefreshSession, UserAccount
from tests.support.clock import FixedClock
from tests.support.factories import TEST_PASSWORD, Factory
from tests.support.http import problem_code, problem_of
from tests.support.log_capture import LogCapture
from tests.support.sessions import (
    INVALID_CREDENTIALS_PROBLEM,
    ME_PATH,
    UNKNOWN_EMAIL,
    WRONG_PASSWORD,
    refresh_token_of,
    sign_in,
)
from tests.support.tokens import authorization_header

ONE_SECOND: Final[timedelta] = timedelta(seconds=1)
ACCESS_LIFETIME_SECONDS: Final[int] = 900
USER_FIELDS: Final[set[str]] = {
    "id", "email", "fullName", "role", "branchCode", "emailVerified", "emailDeliverable"
}  # fmt: skip
BODY_FIELDS: Final[set[str]] = {"accessToken", "tokenType", "expiresIn", "user"}


@pytest.fixture
def customer(session: Session, factory: Factory) -> UserAccount:
    """Return a committed, active customer account."""
    account = factory.user(role=UserRole.CUSTOMER)
    session.commit()
    return account


def events(session: Session, action: str) -> list[AuditEvent]:
    """Return the audit events of one action, oldest first."""
    statement = (
        select(AuditEvent).where(col(AuditEvent.action) == action).order_by(col(AuditEvent.id))
    )
    return list(session.exec(statement).all())


def lock(session: Session, account: UserAccount, clock: FixedClock) -> None:
    """Lock an account as five failures would, without paying for five hashes."""
    account.failed_login_count = MAXIMUM_FAILED_LOGINS
    account.locked_until = clock.now() + LOCKOUT_DURATION
    session.add(account)
    session.commit()


class TestAGoodSignIn:
    """200, the access token in the body and the refresh token in a cookie."""

    def test_the_body_is_the_contract(self, auth_client: TestClient, customer: UserAccount) -> None:
        response = sign_in(auth_client, customer.email)
        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body.keys() == BODY_FIELDS
        assert body["tokenType"] == "Bearer"
        assert body["expiresIn"] == ACCESS_LIFETIME_SECONDS
        assert body["user"] == {
            "id": str(customer.id),
            "email": customer.email,
            "fullName": customer.full_name,
            "role": "customer",
            "branchCode": None,
            "emailVerified": False,
            "emailDeliverable": True,
        }

    def test_counter_staff_are_told_their_branch_code_and_nobody_else_is(
        self, auth_client: TestClient, session: Session, factory: Factory
    ) -> None:
        branch = factory.branch(code="CBD")
        assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=branch)
        administrator = factory.user(role=UserRole.ADMIN)
        session.commit()
        assert sign_in(auth_client, assistant.email).json()["user"]["branchCode"] == "CBD"
        admin_user = sign_in(auth_client, administrator.email).json()["user"]
        assert admin_user["branchCode"] is None
        assert admin_user["role"] == "admin"
        assert admin_user.keys() == USER_FIELDS

    def test_the_access_token_is_in_the_body_and_in_no_cookie(
        self, auth_client: TestClient, customer: UserAccount
    ) -> None:
        response = sign_in(auth_client, customer.email)
        access_token = response.json()["accessToken"]
        cookies = response.headers.get_list(SET_COOKIE_HEADER)
        assert len(cookies) == 1
        assert cookies[0].startswith(f"{REFRESH_COOKIE_NAME}=")
        assert access_token not in cookies[0]

    def test_the_access_token_carries_the_role_and_branch_and_opens_a_protected_route(
        self, auth_client: TestClient, customer: UserAccount
    ) -> None:
        access_token = sign_in(auth_client, customer.email).json()["accessToken"]
        claims = jwt.decode(access_token, options={"verify_signature": False})
        assert claims["sub"] == str(customer.id)
        assert claims["role"] == UserRole.CUSTOMER.value
        assert claims["branch_id"] is None
        me = auth_client.get(ME_PATH, headers=authorization_header(access_token))
        assert me.status_code == status.HTTP_200_OK
        assert me.json()["id"] == str(customer.id)

    def test_the_refresh_token_is_stored_as_its_hash_and_never_returned_in_a_body(
        self, auth_client: TestClient, session: Session, customer: UserAccount
    ) -> None:
        response = sign_in(auth_client, customer.email)
        token = refresh_token_of(response)
        (stored,) = session.exec(select(RefreshSession)).all()
        assert stored.token_hash == hash_refresh_token(token)
        assert stored.user_account_id == customer.id
        assert stored.revoked_at is None
        assert token not in response.text

    def test_the_response_may_not_be_stored_by_any_cache(
        self, auth_client: TestClient, customer: UserAccount
    ) -> None:
        assert sign_in(auth_client, customer.email).headers["Cache-Control"] == "no-store"

    def test_it_notes_the_sign_in_and_writes_a_success_event(
        self,
        auth_client: TestClient,
        session: Session,
        customer: UserAccount,
        still_clock: FixedClock,
    ) -> None:
        sign_in(auth_client, customer.email)
        session.refresh(customer)
        assert customer.last_login_at is not None
        assert customer.last_login_at.replace(tzinfo=None) == still_clock.now().replace(tzinfo=None)
        (event,) = events(session, LOGIN_SUCCEEDED_ACTION)
        assert event.actor_user_id == customer.id
        assert event.entity_id == customer.id


class TestTheFourRefusalsAreIndistinguishable:
    """Same status, same bytes, no cookie, whatever was wrong (BR-46, C-14)."""

    def test_they_return_byte_identical_bodies(
        self,
        auth_client: TestClient,
        session: Session,
        factory: Factory,
        customer: UserAccount,
        still_clock: FixedClock,
    ) -> None:
        deactivated = factory.user(is_active=False)
        locked = factory.user()
        session.commit()
        lock(session, locked, still_clock)
        refusals = {
            "wrong password": sign_in(auth_client, customer.email, WRONG_PASSWORD),
            "unknown email": sign_in(auth_client, UNKNOWN_EMAIL, TEST_PASSWORD),
            "deactivated account": sign_in(auth_client, deactivated.email, TEST_PASSWORD),
            "locked account": sign_in(auth_client, locked.email, TEST_PASSWORD),
        }
        assert {r.status_code for r in refusals.values()} == {status.HTTP_401_UNAUTHORIZED}
        assert len({r.content for r in refusals.values()}) == 1, "The four bodies differ."
        assert {r.headers["content-type"] for r in refusals.values()} == {
            "application/problem+json"
        }
        assert all(SET_COOKIE_HEADER not in r.headers for r in refusals.values())
        assert problem_code(refusals["wrong password"]) == INVALID_CREDENTIALS_PROBLEM
        assert "errors" not in problem_of(refusals["wrong password"])

    def test_the_reason_reaches_the_audit_trail_and_not_the_caller(
        self,
        auth_client: TestClient,
        session: Session,
        factory: Factory,
        customer: UserAccount,
        still_clock: FixedClock,
    ) -> None:
        deactivated = factory.user(is_active=False)
        locked = factory.user()
        session.commit()
        lock(session, locked, still_clock)
        responses = [
            sign_in(auth_client, customer.email, WRONG_PASSWORD),
            sign_in(auth_client, UNKNOWN_EMAIL, TEST_PASSWORD),
            sign_in(auth_client, deactivated.email, TEST_PASSWORD),
            sign_in(auth_client, locked.email, TEST_PASSWORD),
        ]
        reasons = [event.after_state["reason"] for event in events(session, LOGIN_FAILED_ACTION)]
        assert reasons == ["wrong-password", "unknown-email", "deactivated", "locked"]
        for response in responses:
            assert not any(reason in response.text for reason in reasons)

    def test_neither_the_password_nor_a_token_reaches_the_log(
        self, auth_client: TestClient, customer: UserAccount, application_log: LogCapture
    ) -> None:
        refused = sign_in(auth_client, customer.email, WRONG_PASSWORD)
        accepted = sign_in(auth_client, customer.email)
        assert refused.status_code == status.HTTP_401_UNAUTHORIZED
        assert WRONG_PASSWORD not in application_log.text
        assert TEST_PASSWORD not in application_log.text
        assert accepted.json()["accessToken"] not in application_log.text
        assert refresh_token_of(accepted) not in application_log.text
        assert hash_refresh_token(refresh_token_of(accepted)) not in application_log.text
        assert customer.password_hash not in application_log.text


class TestTheLockout:
    """Five failures lock the account for fifteen minutes (BR-46)."""

    def test_five_failures_lock_and_the_lock_ends_when_its_time_is_up(
        self,
        auth_client: TestClient,
        session: Session,
        customer: UserAccount,
        still_clock: FixedClock,
    ) -> None:
        for _ in range(MAXIMUM_FAILED_LOGINS):
            assert sign_in(auth_client, customer.email, WRONG_PASSWORD).status_code == 401
        session.refresh(customer)
        assert customer.failed_login_count == MAXIMUM_FAILED_LOGINS
        assert customer.locked_until is not None

        locked_out = sign_in(auth_client, customer.email)
        assert locked_out.status_code == status.HTTP_401_UNAUTHORIZED
        assert problem_code(locked_out) == INVALID_CREDENTIALS_PROBLEM

        still_clock.advance(LOCKOUT_DURATION - ONE_SECOND)
        assert sign_in(auth_client, customer.email).status_code == status.HTTP_401_UNAUTHORIZED
        still_clock.advance(ONE_SECOND)
        assert sign_in(auth_client, customer.email).status_code == status.HTTP_200_OK
        session.refresh(customer)
        assert customer.failed_login_count == 0
        assert customer.locked_until is None

    def test_a_success_sets_the_count_back_to_zero(
        self, auth_client: TestClient, session: Session, customer: UserAccount
    ) -> None:
        sign_in(auth_client, customer.email, WRONG_PASSWORD)
        sign_in(auth_client, customer.email, WRONG_PASSWORD)
        session.refresh(customer)
        assert customer.failed_login_count == 2
        assert sign_in(auth_client, customer.email).status_code == status.HTTP_200_OK
        session.refresh(customer)
        assert customer.failed_login_count == 0
