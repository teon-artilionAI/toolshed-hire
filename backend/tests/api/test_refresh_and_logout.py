"""`POST /api/auth/refresh` and `POST /api/auth/logout`, through HTTP and SQL (BR-48).

Both are authenticated by the refresh cookie alone. A refresh rotates the
token. A token that comes back a second time revokes its whole family and
leaves an audit event. Signing out revokes on the server and clears the
cookie, and answers 204 whatever it was handed.

The rules are proved in full without HTTP in
tests/unit/test_refresh_and_sign_out_use_cases.py. This file keeps to what the
cookie, the status codes and the rows can show. The cookie attributes and the
`Origin` check are in test_refresh_cookie_and_origin.py.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.api.refresh_cookie import SET_COOKIE_HEADER
from app.application.identity.refresh_session import REFRESH_REUSE_DETECTED_ACTION
from app.domain.enums import RevokeReason, UserRole
from app.domain.session import (
    REFRESH_ABSOLUTE_LIFETIME,
    REFRESH_IDLE_LIFETIME,
    hash_refresh_token,
)
from app.infrastructure.models import AuditEvent, RefreshSession, UserAccount
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.http import problem_code, problem_of
from tests.support.sessions import (
    LOGOUT_PATH,
    ME_PATH,
    REFRESH_PATH,
    SESSION_EXPIRED_PROBLEM,
    present,
    refresh_cookie_header,
    refresh_token_of,
    sign_in,
)
from tests.support.tokens import authorization_header

ONE_SECOND: Final[timedelta] = timedelta(seconds=1)
SIX_DAYS: Final[timedelta] = timedelta(days=6)
UNKNOWN_TOKEN: Final[str] = "made-up-refresh-token-nobody-was-given"
CLEARED_COOKIE_MARKER: Final[str] = "Max-Age=0"


@pytest.fixture
def customer(session: Session, factory: Factory) -> UserAccount:
    """Return a committed, active customer account."""
    account = factory.user(role=UserRole.CUSTOMER)
    session.commit()
    return account


@pytest.fixture
def first_token(auth_client: TestClient, customer: UserAccount) -> str:
    """Sign the customer in and return the refresh token that was set."""
    return refresh_token_of(sign_in(auth_client, customer.email))


def sessions_of(session: Session, account: UserAccount) -> list[RefreshSession]:
    """Return every refresh session of an account, in the order they were opened."""
    session.expire_all()
    statement = (
        select(RefreshSession)
        .where(col(RefreshSession.user_account_id) == account.id)
        .order_by(col(RefreshSession.created_at), col(RefreshSession.issued_at))
    )
    return list(session.exec(statement).all())


def reasons_of(session: Session, account: UserAccount) -> set[RevokeReason | None]:
    """Return the distinct reasons the sessions of an account were revoked for."""
    return {stored.revoked_reason for stored in sessions_of(session, account)}


class TestRefreshWithRotation:
    """A new access token, a new cookie, and the old token retired."""

    def test_it_returns_the_login_body_and_replaces_the_cookie(
        self, auth_client: TestClient, customer: UserAccount, first_token: str
    ) -> None:
        response = present(auth_client, REFRESH_PATH, first_token)
        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body.keys() == {"accessToken", "tokenType", "expiresIn", "user"}
        assert body["tokenType"] == "Bearer"
        assert body["user"]["id"] == str(customer.id)
        assert refresh_token_of(response) != first_token
        assert response.headers["Cache-Control"] == "no-store"

    def test_the_cookie_the_browser_was_given_is_enough_and_no_body_is_needed(
        self, auth_client: TestClient, customer: UserAccount
    ) -> None:
        sign_in(auth_client, customer.email)
        # No header set by the test. The client sends back what it was given.
        response = auth_client.post(REFRESH_PATH)
        assert response.status_code == status.HTTP_200_OK

    def test_the_new_access_token_opens_a_protected_route(
        self, auth_client: TestClient, customer: UserAccount, first_token: str
    ) -> None:
        access_token = present(auth_client, REFRESH_PATH, first_token).json()["accessToken"]
        me = auth_client.get(ME_PATH, headers=authorization_header(access_token))
        assert me.status_code == status.HTTP_200_OK

    def test_the_old_row_is_stamped_and_the_new_one_joins_its_family(
        self, auth_client: TestClient, session: Session, customer: UserAccount, first_token: str
    ) -> None:
        new_token = refresh_token_of(present(auth_client, REFRESH_PATH, first_token))
        stored = {row.token_hash: row for row in sessions_of(session, customer)}
        old, new = stored[hash_refresh_token(first_token)], stored[hash_refresh_token(new_token)]
        assert old.rotated_at is not None
        assert old.revoked_reason is RevokeReason.ROTATION
        assert new.family_id == old.family_id
        assert new.rotated_at is None
        assert new.revoked_at is None

    def test_the_account_is_read_again_so_a_new_role_shows_at_once(
        self, auth_client: TestClient, session: Session, customer: UserAccount, first_token: str
    ) -> None:
        customer.role = UserRole.ADMIN
        session.add(customer)
        session.commit()
        body = present(auth_client, REFRESH_PATH, first_token).json()
        assert body["user"]["role"] == "admin"


class TestReuseDetection:
    """The old token, presented again, ends the family (BR-48)."""

    def test_the_old_token_is_rejected_after_a_rotation(
        self, auth_client: TestClient, first_token: str
    ) -> None:
        present(auth_client, REFRESH_PATH, first_token)
        replay = present(auth_client, REFRESH_PATH, first_token)
        assert replay.status_code == status.HTTP_401_UNAUTHORIZED
        assert problem_code(replay) == SESSION_EXPIRED_PROBLEM

    def test_the_replay_revokes_the_family_so_the_live_token_stops_working_too(
        self, auth_client: TestClient, session: Session, customer: UserAccount, first_token: str
    ) -> None:
        live_token = refresh_token_of(present(auth_client, REFRESH_PATH, first_token))
        present(auth_client, REFRESH_PATH, first_token)
        assert reasons_of(session, customer) == {
            RevokeReason.ROTATION,
            RevokeReason.REUSE_DETECTED,
        }
        after = present(auth_client, REFRESH_PATH, live_token)
        assert after.status_code == status.HTTP_401_UNAUTHORIZED

    def test_the_replay_writes_the_audit_event(
        self, auth_client: TestClient, session: Session, customer: UserAccount, first_token: str
    ) -> None:
        present(auth_client, REFRESH_PATH, first_token)
        present(auth_client, REFRESH_PATH, first_token)
        (event,) = session.exec(
            select(AuditEvent).where(col(AuditEvent.action) == REFRESH_REUSE_DETECTED_ACTION)
        ).all()
        (family_id,) = {stored.family_id for stored in sessions_of(session, customer)}
        assert event.entity_id == customer.id
        assert event.after_state == {
            "session_family_id": str(family_id),
            "revoked_session_count": 1,
            "reason": "REUSE_DETECTED",
        }


class TestARefusedRefresh:
    """Missing, unknown, expired, revoked or deactivated. One answer for all."""

    @pytest.mark.parametrize("token", [None, UNKNOWN_TOKEN])
    def test_a_missing_or_unknown_cookie_is_401_and_the_cookie_is_cleared(
        self, auth_client: TestClient, token: str | None
    ) -> None:
        response = present(auth_client, REFRESH_PATH, token)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert problem_code(response) == SESSION_EXPIRED_PROBLEM
        assert "errors" not in problem_of(response)
        assert CLEARED_COOKIE_MARKER in refresh_cookie_header(response)

    def test_a_session_left_idle_for_seven_days_is_refused(
        self, auth_client: TestClient, first_token: str, still_clock: FixedClock
    ) -> None:
        still_clock.advance(REFRESH_IDLE_LIFETIME - ONE_SECOND)
        token = refresh_token_of(present(auth_client, REFRESH_PATH, first_token))
        still_clock.advance(REFRESH_IDLE_LIFETIME)
        assert present(auth_client, REFRESH_PATH, token).status_code == 401

    def test_a_busy_session_is_refused_fourteen_days_after_the_sign_in(
        self, auth_client: TestClient, first_token: str, still_clock: FixedClock
    ) -> None:
        token = first_token
        for _ in range(2):
            still_clock.advance(SIX_DAYS)
            token = refresh_token_of(present(auth_client, REFRESH_PATH, token))
        still_clock.advance(REFRESH_ABSOLUTE_LIFETIME - 2 * SIX_DAYS - ONE_SECOND)
        last = present(auth_client, REFRESH_PATH, token)
        assert last.status_code == status.HTTP_200_OK
        assert "Max-Age=1;" in refresh_cookie_header(last)
        still_clock.advance(ONE_SECOND)
        expired = present(auth_client, REFRESH_PATH, refresh_token_of(last))
        assert expired.status_code == status.HTTP_401_UNAUTHORIZED

    def test_an_account_deactivated_since_the_sign_in_is_refused(
        self, auth_client: TestClient, session: Session, customer: UserAccount, first_token: str
    ) -> None:
        customer.is_active = False
        session.add(customer)
        session.commit()
        response = present(auth_client, REFRESH_PATH, first_token)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert problem_code(response) == SESSION_EXPIRED_PROBLEM

    def test_every_refusal_returns_the_same_bytes(
        self, auth_client: TestClient, first_token: str, still_clock: FixedClock
    ) -> None:
        rotated = present(auth_client, REFRESH_PATH, first_token)
        refusals = [
            present(auth_client, REFRESH_PATH, None),
            present(auth_client, REFRESH_PATH, UNKNOWN_TOKEN),
            present(auth_client, REFRESH_PATH, first_token),
            present(auth_client, REFRESH_PATH, refresh_token_of(rotated)),
        ]
        assert {response.status_code for response in refusals} == {401}
        assert len({response.content for response in refusals}) == 1


class TestLogout:
    """Always 204. The session is revoked and the cookie is cleared."""

    def test_it_revokes_the_session_and_clears_the_cookie(
        self, auth_client: TestClient, session: Session, customer: UserAccount, first_token: str
    ) -> None:
        response = present(auth_client, LOGOUT_PATH, first_token)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.content == b""
        assert CLEARED_COOKIE_MARKER in refresh_cookie_header(response)
        assert reasons_of(session, customer) == {RevokeReason.LOGOUT}

    def test_the_token_no_longer_refreshes_afterwards(
        self, auth_client: TestClient, first_token: str
    ) -> None:
        present(auth_client, LOGOUT_PATH, first_token)
        response = present(auth_client, REFRESH_PATH, first_token)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_the_browser_drops_the_cookie_so_the_next_refresh_presents_nothing(
        self, auth_client: TestClient, customer: UserAccount
    ) -> None:
        sign_in(auth_client, customer.email)
        assert auth_client.post(LOGOUT_PATH).status_code == status.HTTP_204_NO_CONTENT
        assert not auth_client.cookies
        assert auth_client.post(REFRESH_PATH).status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.parametrize("token", [None, UNKNOWN_TOKEN])
    def test_it_is_204_with_no_cookie_and_with_one_nobody_was_given(
        self, auth_client: TestClient, token: str | None
    ) -> None:
        response = present(auth_client, LOGOUT_PATH, token)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert CLEARED_COOKIE_MARKER in response.headers[SET_COOKIE_HEADER]

    def test_it_is_204_a_second_time(self, auth_client: TestClient, first_token: str) -> None:
        present(auth_client, LOGOUT_PATH, first_token)
        assert present(auth_client, LOGOUT_PATH, first_token).status_code == 204

    def test_another_sign_in_of_the_same_account_is_left_signed_in(
        self, auth_client: TestClient, customer: UserAccount, first_token: str
    ) -> None:
        other_token = refresh_token_of(sign_in(auth_client, customer.email))
        present(auth_client, LOGOUT_PATH, first_token)
        assert present(auth_client, REFRESH_PATH, other_token).status_code == 200
