"""Sessions, lockout and throttling on real PostgreSQL (BR-46, BR-48, C-17).

The fast tests prove the rules on SQLite, which has no row lock, no `inet`, no
native enumerated type and no time zone on a timestamp. These prove the four
things that only PostgreSQL can.

The rows are written the way the schema types them. An address is an `inet`, a
revoke reason is the native enumerated type and an instant keeps its zone.

The counter is one atomic statement, as the restricted application role, which
may also delete an old window and may delete nothing else.

Two requests that present the same refresh token cannot both rotate it. The
second waits on the row lock, finds the token used and ends the family.

And two failed sign ins at the same moment are both counted.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import timedelta
from ipaddress import ip_address
from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.application.identity.refresh_session import (
    REFRESH_REUSE_DETECTED_ACTION,
    RefreshSessionCommand,
    RefreshSessionUseCase,
)
from app.application.identity.sign_in import (
    LOGIN_ATTEMPTS_PER_EMAIL,
    LOGIN_WINDOW,
    SignInCommand,
    SignInUseCase,
)
from app.application.throttle import Throttle
from app.domain.account import LOCKOUT_DURATION, MAXIMUM_FAILED_LOGINS
from app.domain.enums import RevokeReason
from app.domain.errors import InvalidCredentials, SessionExpired
from app.infrastructure.identity_accounts import JwtAccessTokenIssuer
from app.infrastructure.models import AuditEvent, RateLimitCounter, RefreshSession, UserAccount
from app.infrastructure.rate_limit import SqlRateLimitStore
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from tests.support.clock import FixedClock
from tests.support.factories import TEST_PASSWORD, Factory
from tests.support.race import BARRIER_TIMEOUT_SECONDS, CONTENDER_COUNT, Outcome, run_race
from tests.support.roles import (
    APPLICATION_ROLE,
    APPLICATION_ROLE_PASSWORD,
    engine_as,
    provision_restricted_roles,
)
from tests.support.sessions import (
    LOGOUT_PATH,
    REFRESH_PATH,
    UNKNOWN_EMAIL,
    WRONG_PASSWORD,
    RefusingVerifier,
    present,
    refresh_token_of,
    session_client,
    sign_in,
    without_bcrypt,
)

pytestmark = [pytest.mark.postgres, pytest.mark.usefixtures("postgres_session")]

CLIENT_ADDRESS: Final[str] = "203.0.113.9"
BUCKET: Final[str] = "b" * 64
RETRY_AFTER_HEADER: Final[str] = "Retry-After"


@pytest.fixture
def clock() -> FixedClock:
    """Return a clock that stands still until the test moves it."""
    return FixedClock()


@pytest.fixture
def api(postgres_session: Session, clock: FixedClock) -> Iterator[TestClient]:
    """Yield a client for the real application on the real database, from a known address."""
    with session_client(postgres_session, clock, client_address=CLIENT_ADDRESS) as client:
        yield client


@pytest.fixture
def customer(postgres_session: Session, postgres_factory: Factory) -> UserAccount:
    """Return a committed, active customer account."""
    account = postgres_factory.user()
    postgres_session.commit()
    return account


@pytest.fixture(scope="module")
def application_engine(postgres_engine: Engine, postgres_url: str) -> Iterator[Engine]:
    """Yield an engine signed in as the restricted application role."""
    provision_restricted_roles(postgres_engine, postgres_url)
    engine = engine_as(postgres_url, APPLICATION_ROLE, APPLICATION_ROLE_PASSWORD)
    try:
        yield engine
    finally:
        engine.dispose()


def sessions_of(session: Session, account: UserAccount) -> list[RefreshSession]:
    """Return every refresh session of an account, oldest first."""
    session.expire_all()
    statement = (
        select(RefreshSession)
        .where(col(RefreshSession.user_account_id) == account.id)
        .order_by(col(RefreshSession.issued_at), col(RefreshSession.created_at))
    )
    return list(session.exec(statement).all())


class TestTheRowsAreTypedAsTheSchemaTypesThem:
    """An `inet`, a native enumerated type and an instant that keeps its zone."""

    def test_a_sign_in_stores_the_address_the_instant_and_the_browser(
        self, api: TestClient, postgres_session: Session, customer: UserAccount, clock: FixedClock
    ) -> None:
        response = api.post(
            "/api/auth/login",
            json={"email": customer.email, "password": TEST_PASSWORD},
            headers={"User-Agent": "A browser at the counter"},
        )
        assert response.status_code == status.HTTP_200_OK
        (stored,) = sessions_of(postgres_session, customer)
        assert stored.ip_address == ip_address(CLIENT_ADDRESS)
        assert stored.user_agent == "A browser at the counter"
        assert stored.issued_at == clock.now()
        assert stored.issued_at.tzinfo is not None

    def test_rotation_reuse_and_logout_store_their_reasons(
        self, api: TestClient, postgres_session: Session, customer: UserAccount
    ) -> None:
        first = refresh_token_of(sign_in(api, customer.email))
        second = refresh_token_of(present(api, REFRESH_PATH, first))
        assert present(api, REFRESH_PATH, first).status_code == status.HTTP_401_UNAUTHORIZED
        assert present(api, REFRESH_PATH, second).status_code == status.HTTP_401_UNAUTHORIZED
        other = refresh_token_of(sign_in(api, customer.email))
        assert present(api, LOGOUT_PATH, other).status_code == status.HTTP_204_NO_CONTENT
        reasons = [stored.revoked_reason for stored in sessions_of(postgres_session, customer)]
        assert reasons == [
            RevokeReason.ROTATION,
            RevokeReason.REUSE_DETECTED,
            RevokeReason.LOGOUT,
        ]

    def test_the_reuse_event_carries_the_address_it_came_from(
        self, api: TestClient, postgres_session: Session, customer: UserAccount
    ) -> None:
        first = refresh_token_of(sign_in(api, customer.email))
        present(api, REFRESH_PATH, first)
        present(api, REFRESH_PATH, first)
        (event,) = postgres_session.exec(
            select(AuditEvent).where(col(AuditEvent.action) == REFRESH_REUSE_DETECTED_ACTION)
        ).all()
        assert event.entity_id == customer.id
        assert event.ip_address == ip_address(CLIENT_ADDRESS)

    def test_five_failures_lock_and_the_lock_ends_with_the_clock(
        self, api: TestClient, postgres_session: Session, customer: UserAccount, clock: FixedClock
    ) -> None:
        for _ in range(MAXIMUM_FAILED_LOGINS):
            assert sign_in(api, customer.email, WRONG_PASSWORD).status_code == 401
        postgres_session.refresh(customer)
        assert customer.locked_until == clock.now() + LOCKOUT_DURATION
        assert sign_in(api, customer.email).status_code == status.HTTP_401_UNAUTHORIZED
        clock.advance(LOCKOUT_DURATION)
        assert sign_in(api, customer.email).status_code == status.HTTP_200_OK


class TestTheCounters:
    """One atomic statement, and the one delete the application may issue (C-17)."""

    def test_the_eleventh_attempt_is_429_and_both_windows_were_counted(
        self, postgres_session: Session, clock: FixedClock
    ) -> None:
        with (
            without_bcrypt(),
            session_client(postgres_session, clock, client_address=CLIENT_ADDRESS) as api,
        ):
            for _ in range(LOGIN_ATTEMPTS_PER_EMAIL):
                sign_in(api, UNKNOWN_EMAIL)
            throttled = sign_in(api, UNKNOWN_EMAIL)
        assert throttled.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert throttled.headers[RETRY_AFTER_HEADER] == str(int(LOGIN_WINDOW.total_seconds()))
        counters = postgres_session.exec(select(RateLimitCounter)).all()
        assert [counter.request_count for counter in counters] == [
            LOGIN_ATTEMPTS_PER_EMAIL + 1,
            LOGIN_ATTEMPTS_PER_EMAIL + 1,
        ]
        assert all(counter.window_started_at == clock.now() for counter in counters)

    def test_the_application_role_may_count_and_may_delete_an_old_window(
        self, application_engine: Engine, clock: FixedClock
    ) -> None:
        old_window = clock.now() - timedelta(days=2)
        with Session(application_engine) as session:
            store = SqlRateLimitStore(session)
            assert [store.increment(BUCKET, clock.now()) for _ in range(3)] == [1, 2, 3]
            assert store.increment(BUCKET, old_window) == 1
            session.commit()
        with Session(application_engine) as session:
            store = SqlRateLimitStore(session)
            assert store.delete_windows_before(clock.now() - timedelta(days=1)) == 1
            session.commit()
            remaining = session.exec(select(RateLimitCounter)).all()
        assert [(row.bucket_key_hash, row.request_count) for row in remaining] == [(BUCKET, 3)]

    def test_two_attempts_at_once_are_both_counted(
        self, postgres_engine: Engine, clock: FixedClock
    ) -> None:
        barrier = threading.Barrier(CONTENDER_COUNT, timeout=BARRIER_TIMEOUT_SECONDS)

        def count_once() -> Outcome:
            """Count one attempt in a transaction of its own."""
            with Session(postgres_engine) as session:
                barrier.wait()
                SqlRateLimitStore(session).increment(BUCKET, clock.now())
                session.commit()
            return Outcome(succeeded=True)

        run_race(count_once, count_once)
        with Session(postgres_engine) as session:
            (counter,) = session.exec(select(RateLimitCounter)).all()
        assert counter.request_count == CONTENDER_COUNT


class TestTwoRequestsAtOnce:
    """The row locks, which are the part SQLite cannot show."""

    def test_one_token_presented_twice_at_once_rotates_once_and_then_ends_the_family(
        self,
        api: TestClient,
        postgres_engine: Engine,
        postgres_session: Session,
        customer: UserAccount,
        clock: FixedClock,
    ) -> None:
        token = refresh_token_of(sign_in(api, customer.email))
        barrier = threading.Barrier(CONTENDER_COUNT, timeout=BARRIER_TIMEOUT_SECONDS)

        def refresh_once() -> Outcome:
            """Present the token in a transaction of its own."""
            use_case = RefreshSessionUseCase(
                SqlAlchemyUnitOfWork(lambda: Session(postgres_engine)),
                clock,
                JwtAccessTokenIssuer(),
            )
            barrier.wait()
            try:
                use_case.execute(RefreshSessionCommand(presented_token=token))
            except SessionExpired as refusal:
                return Outcome(succeeded=False, error=refusal)
            return Outcome(succeeded=True)

        outcomes = run_race(refresh_once, refresh_once)
        assert sorted(outcome.succeeded for outcome in outcomes) == [False, True]
        stored = sessions_of(postgres_session, customer)
        assert len(stored) == 2, "Both requests rotated the token, so the lock did not hold."
        assert all(row.revoked_at is not None for row in stored)
        assert {row.revoked_reason for row in stored} == {
            RevokeReason.ROTATION,
            RevokeReason.REUSE_DETECTED,
        }

    def test_two_failed_sign_ins_at_once_are_both_counted(
        self,
        postgres_engine: Engine,
        postgres_session: Session,
        customer: UserAccount,
        clock: FixedClock,
    ) -> None:
        email = customer.email
        barrier = threading.Barrier(CONTENDER_COUNT, timeout=BARRIER_TIMEOUT_SECONDS)
        throttle = Throttle("made-up-salt-for-this-test")

        def fail_once() -> Outcome:
            """Fail one sign in, in a transaction of its own."""
            use_case = SignInUseCase(
                SqlAlchemyUnitOfWork(lambda: Session(postgres_engine)),
                clock,
                RefusingVerifier(),
                JwtAccessTokenIssuer(),
                throttle,
            )
            barrier.wait()
            try:
                use_case.execute(SignInCommand(email=email, password=WRONG_PASSWORD))
            except InvalidCredentials as refusal:
                return Outcome(succeeded=False, error=refusal)
            return Outcome(succeeded=True)

        outcomes = run_race(fail_once, fail_once)
        assert [outcome.succeeded for outcome in outcomes] == [False, False]
        postgres_session.refresh(customer)
        assert customer.failed_login_count == CONTENDER_COUNT
