"""The two sign in throttles and the timing of a refusal, through HTTP (C-14, C-17).

A throttled caller gets a 429 with `Retry-After` in seconds. The counters are
rows in `rate_limit_counter`, keyed by a salted hash, and the tests read the
table to prove no address is in it.

The throttle tests swap bcrypt for a verifier that refuses everything, because
they make forty attempts and are about counting. The timing tests keep the
real bcrypt, because the work factor is what they are about.

Timing is proved twice. The first test counts bcrypt verifications and is
exact. Every path, the four refusals and the success, runs one. The second
measures. It interleaves refusals for an unknown address with refusals for a
wrong password and compares the two medians, with a tolerance wide enough that
a busy machine does not fail it and narrow enough that a path which skipped the
hash, and so answered a hundred times faster, would.
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Iterator
from datetime import timedelta
from typing import Final

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.application.identity.sign_in import (
    LOGIN_ATTEMPTS_PER_ADDRESS,
    LOGIN_ATTEMPTS_PER_EMAIL,
    LOGIN_WINDOW,
)
from app.domain.account import LOCKOUT_DURATION, MAXIMUM_FAILED_LOGINS
from app.domain.enums import UserRole
from app.infrastructure import security
from app.infrastructure.models import RateLimitCounter, UserAccount
from tests.support.clock import FixedClock
from tests.support.factories import TEST_PASSWORD, Factory
from tests.support.http import problem_code, problem_of
from tests.support.sessions import (
    TOO_MANY_ATTEMPTS_PROBLEM,
    UNKNOWN_EMAIL,
    WRONG_PASSWORD,
    session_client,
    sign_in,
    without_bcrypt,
)

RETRY_AFTER_HEADER: Final[str] = "Retry-After"
CLIENT_ADDRESS: Final[str] = "203.0.113.9"
OTHER_CLIENT_ADDRESS: Final[str] = "198.51.100.20"
SHA256_HEX_LENGTH: Final[int] = 64
# The fixed clock starts on the hour, which is the start of a window.
WHOLE_WINDOW_SECONDS: Final[int] = int(LOGIN_WINDOW.total_seconds())
TIMING_SAMPLES: Final[int] = 5
# How far apart the two medians may be, as a ratio. A path that skipped the
# hash would be out by a factor of a hundred or more.
TIMING_TOLERANCE: Final[float] = 2.0


@pytest.fixture
def no_bcrypt() -> Iterator[None]:
    """Swap the password verifier of the real application for one that costs nothing."""
    with without_bcrypt():
        yield


@pytest.fixture
def customer(session: Session, factory: Factory) -> UserAccount:
    """Return a committed, active customer account."""
    account = factory.user(role=UserRole.CUSTOMER)
    session.commit()
    return account


@pytest.mark.usefixtures("no_bcrypt")
class TestTheEmailThrottle:
    """Ten attempts on one address in fifteen minutes, and then a wait."""

    def test_the_eleventh_attempt_is_429_with_retry_after_in_seconds(
        self, auth_client: TestClient
    ) -> None:
        for _ in range(LOGIN_ATTEMPTS_PER_EMAIL):
            assert sign_in(auth_client, UNKNOWN_EMAIL).status_code == status.HTTP_401_UNAUTHORIZED
        throttled = sign_in(auth_client, UNKNOWN_EMAIL)
        assert throttled.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert problem_code(throttled) == TOO_MANY_ATTEMPTS_PROBLEM
        assert throttled.headers[RETRY_AFTER_HEADER] == str(WHOLE_WINDOW_SECONDS)
        assert problem_of(throttled)["errors"] == {"retry_after_seconds": WHOLE_WINDOW_SECONDS}

    def test_the_wait_shrinks_as_the_window_runs_and_ends_with_it(
        self, auth_client: TestClient, still_clock: FixedClock
    ) -> None:
        for _ in range(LOGIN_ATTEMPTS_PER_EMAIL):
            sign_in(auth_client, UNKNOWN_EMAIL)
        still_clock.advance(timedelta(minutes=10))
        throttled = sign_in(auth_client, UNKNOWN_EMAIL)
        assert throttled.headers[RETRY_AFTER_HEADER] == str(WHOLE_WINDOW_SECONDS - 600)
        still_clock.advance(timedelta(minutes=5))
        assert sign_in(auth_client, UNKNOWN_EMAIL).status_code == status.HTTP_401_UNAUTHORIZED

    def test_another_address_is_not_held_up(self, auth_client: TestClient) -> None:
        for _ in range(LOGIN_ATTEMPTS_PER_EMAIL + 1):
            sign_in(auth_client, UNKNOWN_EMAIL)
        other = sign_in(auth_client, "somebody.else@toolshedhire.co.za")
        assert other.status_code == status.HTTP_401_UNAUTHORIZED

    def test_the_address_is_counted_whatever_its_case(self, auth_client: TestClient) -> None:
        for _ in range(LOGIN_ATTEMPTS_PER_EMAIL):
            sign_in(auth_client, UNKNOWN_EMAIL)
        throttled = sign_in(auth_client, UNKNOWN_EMAIL.upper())
        assert throttled.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.usefixtures("no_bcrypt")
class TestTheClientAddressThrottle:
    """Thirty attempts from one client address in fifteen minutes, and then a wait."""

    def test_the_thirty_first_attempt_from_one_address_is_429(self, session: Session) -> None:
        with session_client(session, client_address=CLIENT_ADDRESS) as client:
            for number in range(LOGIN_ATTEMPTS_PER_ADDRESS):
                response = sign_in(client, f"guess{number}@toolshedhire.co.za")
                assert response.status_code == status.HTTP_401_UNAUTHORIZED
            throttled = sign_in(client, "one.more@toolshedhire.co.za")
        assert throttled.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert throttled.headers[RETRY_AFTER_HEADER] == str(WHOLE_WINDOW_SECONDS)

    def test_a_second_client_address_is_not_held_up(self, session: Session) -> None:
        with session_client(session, client_address=CLIENT_ADDRESS) as client:
            for number in range(LOGIN_ATTEMPTS_PER_ADDRESS + 1):
                sign_in(client, f"guess{number}@toolshedhire.co.za")
        with session_client(session, client_address=OTHER_CLIENT_ADDRESS) as elsewhere:
            response = sign_in(elsewhere, "from.elsewhere@toolshedhire.co.za")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_the_counters_are_hashes_and_hold_neither_address(self, session: Session) -> None:
        with session_client(session, client_address=CLIENT_ADDRESS) as client:
            sign_in(client, UNKNOWN_EMAIL)
            sign_in(client, UNKNOWN_EMAIL)
        counters = session.exec(select(RateLimitCounter)).all()
        assert sorted(counter.request_count for counter in counters) == [2, 2]
        for counter in counters:
            assert len(counter.bucket_key_hash) == SHA256_HEX_LENGTH
            assert UNKNOWN_EMAIL not in counter.bucket_key_hash
            assert CLIENT_ADDRESS not in counter.bucket_key_hash


class TestEveryPathCostsOneHash:
    """The same work whatever the reason, so the time says nothing (BR-46, C-14)."""

    def test_each_refusal_and_the_success_run_exactly_one_bcrypt_verification(
        self,
        auth_client: TestClient,
        session: Session,
        factory: Factory,
        customer: UserAccount,
        still_clock: FixedClock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        deactivated = factory.user(is_active=False)
        locked = factory.user()
        locked.failed_login_count = MAXIMUM_FAILED_LOGINS
        locked.locked_until = still_clock.now() + LOCKOUT_DURATION
        session.add(locked)
        session.commit()
        verified: list[str] = []
        real_verify = security._password_context.verify

        def counting_verify(secret: str, stored_hash: str) -> bool:
            """Note the call and hand it to the real bcrypt."""
            verified.append(stored_hash)
            return bool(real_verify(secret, stored_hash))

        monkeypatch.setattr(security._password_context, "verify", counting_verify)
        attempts = {
            "wrong password": (customer.email, WRONG_PASSWORD),
            "unknown email": (UNKNOWN_EMAIL, TEST_PASSWORD),
            "deactivated account": (deactivated.email, TEST_PASSWORD),
            "locked account": (locked.email, TEST_PASSWORD),
            "success": (customer.email, TEST_PASSWORD),
        }
        counts: dict[str, int] = {}
        for name, (email, password) in attempts.items():
            before = len(verified)
            sign_in(auth_client, email, password)
            counts[name] = len(verified) - before
        assert counts == dict.fromkeys(attempts, 1)

    def test_an_unknown_address_takes_as_long_as_a_wrong_password(
        self, auth_client: TestClient, session: Session, factory: Factory
    ) -> None:
        # One account for each sample, so no account reaches its fifth failure
        # and turns a wrong password into a locked account part of the way in.
        accounts = [factory.user() for _ in range(TIMING_SAMPLES)]
        session.commit()
        emails = [account.email for account in accounts]

        def timed(email: str) -> float:
            """Return how long one refused sign in took, in seconds."""
            started = time.perf_counter()
            response = sign_in(auth_client, email, WRONG_PASSWORD)
            elapsed = time.perf_counter() - started
            assert response.status_code == status.HTTP_401_UNAUTHORIZED
            return elapsed

        timed(emails[0])  # The first request pays for imports and warm caches.
        wrong_password: list[float] = []
        unknown_email: list[float] = []
        for number, email in enumerate(emails):
            wrong_password.append(timed(email))
            unknown_email.append(timed(f"nobody{number}@toolshedhire.co.za"))
        ratio = statistics.median(unknown_email) / statistics.median(wrong_password)
        assert 1 / TIMING_TOLERANCE < ratio < TIMING_TOLERANCE, (
            f"An unknown address answered in {statistics.median(unknown_email):.4f}s and a "
            f"wrong password in {statistics.median(wrong_password):.4f}s. The two must cost "
            "the same, or the time gives the reason away."
        )
