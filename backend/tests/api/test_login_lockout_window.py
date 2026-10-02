"""The sign in lockout counted over fifteen minutes, through `POST /api/auth/login` (BR-46).

Five wrong passwords inside fifteen minutes lock the account for fifteen
minutes, and a locked account is refused with the same 401 as a wrong
password, so the caller cannot tell a lock from a typing mistake. The failures
are counted in a window that slides with the clock, which replaced a count of
failures in a row. Five failures spread over more than fifteen minutes do not
lock, and a success starts the count again even while the earlier failures are
still inside the window.

The failures are rows in `rate_limit_counter`, one for each second a failure
happened in, under a salted hash of the account key. I read the table to prove
neither the address nor the key is in it.

The failures run without bcrypt, because a verifier that refuses everything is
all a wrong password needs. A sign in that is meant to succeed runs the real
verifier, since the cheap one refuses the right password too. The login
contract itself is in test_login.py.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from httpx import Response
from sqlmodel import Session, select

from app.api.identity_deps import get_throttle
from app.application.identity.sign_in import LOGIN_FAILURES
from app.domain.enums import UserRole
from app.infrastructure.models import RateLimitCounter, UserAccount
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.http import problem_code
from tests.support.sessions import (
    INVALID_CREDENTIALS_PROBLEM,
    WRONG_PASSWORD,
    sign_in,
    without_bcrypt,
)

FAILURES_THAT_LOCK: Final[int] = 5
LOCK_LENGTH: Final[timedelta] = timedelta(minutes=15)
ONE_SECOND: Final[timedelta] = timedelta(seconds=1)
ONE_MINUTE: Final[timedelta] = timedelta(minutes=1)
# Five failures this far apart span twelve minutes, inside the window.
THREE_MINUTES: Final[timedelta] = timedelta(minutes=3)
# Five failures this far apart span sixteen minutes, so the first has left the
# window by the time the fifth arrives.
FOUR_MINUTES: Final[timedelta] = timedelta(minutes=4)
NO_TIME: Final[timedelta] = timedelta(0)
FAILURES_SHORT_OF_A_LOCK: Final[int] = FAILURES_THAT_LOCK - 1
SHA256_HEX_LENGTH: Final[int] = 64
HEXADECIMAL_BASE: Final[int] = 16
KEY_ENCODING: Final[str] = "utf-8"


@pytest.fixture
def customer(session: Session, factory: Factory) -> UserAccount:
    """Return a committed, active customer account whose password is the test password."""
    account = factory.user(role=UserRole.CUSTOMER)
    session.commit()
    return account


def fail(
    client: TestClient, clock: FixedClock, email: str, times: int, step: timedelta
) -> list[Response]:
    """Sign in with a wrong password `times` times, moving the clock `step` between each.

    The verifier refuses without hashing, so the failures cost nothing.
    """
    refusals: list[Response] = []
    with without_bcrypt():
        for number in range(times):
            if number:
                clock.advance(step)
            refusals.append(sign_in(client, email, WRONG_PASSWORD))
    assert {refusal.status_code for refusal in refusals} == {status.HTTP_401_UNAUTHORIZED}
    return refusals


def stored(session: Session, account: UserAccount) -> UserAccount:
    """Return the account row as the database now holds it."""
    session.refresh(account)
    return account


class TestFiveFailuresInsideFifteenMinutesLock:
    """The fifth failure inside the window locks the account for fifteen minutes."""

    def test_the_right_password_is_then_refused_with_the_same_401(
        self,
        auth_client: TestClient,
        session: Session,
        customer: UserAccount,
        still_clock: FixedClock,
    ) -> None:
        refusals = fail(auth_client, still_clock, customer.email, FAILURES_THAT_LOCK, THREE_MINUTES)
        locked_out = sign_in(auth_client, customer.email)
        assert locked_out.status_code == status.HTTP_401_UNAUTHORIZED
        assert problem_code(locked_out) == INVALID_CREDENTIALS_PROBLEM
        assert locked_out.content == refusals[-1].content
        row = stored(session, customer)
        assert row.locked_until is not None
        expected_end = still_clock.now() + LOCK_LENGTH
        assert row.locked_until.replace(tzinfo=None) == expected_end.replace(tzinfo=None)

    def test_the_lock_ends_fifteen_minutes_after_the_fifth_failure(
        self, auth_client: TestClient, customer: UserAccount, still_clock: FixedClock
    ) -> None:
        fail(auth_client, still_clock, customer.email, FAILURES_THAT_LOCK, ONE_MINUTE)
        still_clock.advance(LOCK_LENGTH - ONE_SECOND)
        assert sign_in(auth_client, customer.email).status_code == status.HTTP_401_UNAUTHORIZED
        still_clock.advance(ONE_SECOND)
        assert sign_in(auth_client, customer.email).status_code == status.HTTP_200_OK


class TestFailuresTheWindowDoesNotHoldDoNotLock:
    """Failures older than fifteen minutes, or from before a success, are not counted."""

    def test_five_failures_four_minutes_apart_do_not_lock(
        self,
        auth_client: TestClient,
        session: Session,
        customer: UserAccount,
        still_clock: FixedClock,
    ) -> None:
        fail(auth_client, still_clock, customer.email, FAILURES_THAT_LOCK, FOUR_MINUTES)
        assert stored(session, customer).locked_until is None
        assert sign_in(auth_client, customer.email).status_code == status.HTTP_200_OK

    def test_four_failures_a_success_and_four_more_do_not_lock(
        self,
        auth_client: TestClient,
        session: Session,
        customer: UserAccount,
        still_clock: FixedClock,
    ) -> None:
        # Ten attempts on one address at one instant, which is the most the
        # sign in throttle allows in its window and so all of them are heard.
        fail(auth_client, still_clock, customer.email, FAILURES_SHORT_OF_A_LOCK, NO_TIME)
        assert sign_in(auth_client, customer.email).status_code == status.HTTP_200_OK
        fail(auth_client, still_clock, customer.email, FAILURES_SHORT_OF_A_LOCK, NO_TIME)
        assert stored(session, customer).locked_until is None
        assert sign_in(auth_client, customer.email).status_code == status.HTTP_200_OK


class TestTheFailureCounters:
    """The failures are counted in `rate_limit_counter` under a salted hash."""

    def test_the_failures_are_counted_under_a_salted_hash_of_the_account_key(
        self,
        auth_client: TestClient,
        session: Session,
        customer: UserAccount,
        still_clock: FixedClock,
    ) -> None:
        fail(auth_client, still_clock, customer.email, FAILURES_SHORT_OF_A_LOCK, NO_TIME)
        failure_key = get_throttle().bucket_key_hash(LOGIN_FAILURES, str(customer.id))
        counters = session.exec(select(RateLimitCounter)).all()
        (failures,) = [row for row in counters if row.bucket_key_hash == failure_key]
        assert failures.request_count == FAILURES_SHORT_OF_A_LOCK

    def test_no_counter_holds_the_address_or_the_account_key(
        self,
        auth_client: TestClient,
        session: Session,
        customer: UserAccount,
        still_clock: FixedClock,
    ) -> None:
        fail(auth_client, still_clock, customer.email, FAILURES_SHORT_OF_A_LOCK, ONE_SECOND)
        plain_values = (customer.email, str(customer.id), customer.id.hex)
        unsalted = {hashlib.sha256(text.encode(KEY_ENCODING)).hexdigest() for text in plain_values}
        keys = {row.bucket_key_hash for row in session.exec(select(RateLimitCounter)).all()}
        assert keys
        for key in keys:
            assert len(key) == SHA256_HEX_LENGTH
            assert int(key, HEXADECIMAL_BASE) >= 0
            assert not any(value in key for value in plain_values)
        assert not keys & unsalted
