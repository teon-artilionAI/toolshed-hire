"""The lockout and the two throttles of a sign in, with no database (BR-46, C-17).

Five failures lock an account for fifteen minutes. Ten attempts on one address
and thirty from one client are all a window allows. The clock stands still
until a test moves it, so a lock and a window are run out without waiting.

A refusal raises, and what it changed is kept all the same. That is pinned
here as well, because a lockout that rolled back with its own refusal would
never count past one.
"""

from __future__ import annotations

from datetime import timedelta
from ipaddress import ip_address
from typing import Final

import pytest

from app.application.identity.sessions import ClientDetails
from app.application.identity.sign_in import (
    LOGIN_ADDRESS_RULE,
    LOGIN_ATTEMPTS_PER_ADDRESS,
    LOGIN_ATTEMPTS_PER_EMAIL,
    LOGIN_EMAIL_RULE,
    LOGIN_FAILED_ACTION,
    LOGIN_WINDOW,
)
from app.domain.account import LOCKOUT_DURATION, MAXIMUM_FAILED_LOGINS, Account
from app.domain.errors import InvalidCredentials, TooManyAttempts
from tests.support.identity_desk import CLIENT, UNKNOWN_EMAIL, Desk
from tests.support.memory_identity import KNOWN_EMAIL, KNOWN_PASSWORD

ONE_SECOND: Final[timedelta] = timedelta(seconds=1)


@pytest.fixture
def desk() -> Desk:
    return Desk()


@pytest.fixture
def account(desk: Desk) -> Account:
    return desk.identity.add_account()


class TestTheLockout:
    """Five failures lock the account, and the lock ends by itself (BR-46)."""

    def test_the_fifth_failure_locks_and_the_right_password_is_then_refused(
        self, desk: Desk, account: Account
    ) -> None:
        for _ in range(MAXIMUM_FAILED_LOGINS):
            desk.sign_in_refused()
        stored = desk.identity.account(account.id)
        assert stored.failed_login_count == MAXIMUM_FAILED_LOGINS
        assert stored.locked_until == desk.clock.now() + LOCKOUT_DURATION
        desk.sign_in_refused(password=KNOWN_PASSWORD)
        assert [event.after_state["reason"] for event in desk.audit(LOGIN_FAILED_ACTION)] == [
            *["wrong-password"] * MAXIMUM_FAILED_LOGINS,
            "locked",
        ]

    def test_the_failure_that_locks_says_so_in_its_event(
        self, desk: Desk, account: Account
    ) -> None:
        for _ in range(MAXIMUM_FAILED_LOGINS):
            desk.sign_in_refused()
        states = [event.after_state for event in desk.audit(LOGIN_FAILED_ACTION)]
        assert [state["locked"] for state in states] == [False, False, False, False, True]
        assert [state["failed_login_count"] for state in states] == [1, 2, 3, 4, 5]

    def test_the_account_signs_in_again_once_the_lock_has_run_out(
        self, desk: Desk, account: Account
    ) -> None:
        for _ in range(MAXIMUM_FAILED_LOGINS):
            desk.sign_in_refused()
        desk.clock.advance(LOCKOUT_DURATION - ONE_SECOND)
        desk.sign_in_refused(password=KNOWN_PASSWORD)
        desk.clock.advance(ONE_SECOND)
        assert desk.sign_in().account.id == account.id
        assert desk.identity.account(account.id).locked_until is None

    def test_a_refusal_is_committed_even_though_it_raises(
        self, desk: Desk, account: Account
    ) -> None:
        desk.sign_in_refused()
        assert desk.identity.account(account.id).failed_login_count == 1
        assert len(desk.audit(LOGIN_FAILED_ACTION)) == 1


class TestTheTwoThrottles:
    """Ten attempts for an address signed in to, thirty from a client address (C-17)."""

    def test_the_limits_and_the_window_are_the_documented_ones(self) -> None:
        assert (LOGIN_ATTEMPTS_PER_EMAIL, LOGIN_ATTEMPTS_PER_ADDRESS) == (10, 30)
        assert timedelta(minutes=15) == LOGIN_WINDOW
        assert (LOGIN_EMAIL_RULE.limit, LOGIN_ADDRESS_RULE.limit) == (10, 30)

    def test_the_eleventh_attempt_on_one_address_is_told_to_wait(self, desk: Desk) -> None:
        for _ in range(LOGIN_ATTEMPTS_PER_EMAIL):
            desk.sign_in_refused(email=UNKNOWN_EMAIL)
        with pytest.raises(TooManyAttempts) as refusal:
            desk.sign_in(email=UNKNOWN_EMAIL)
        seconds_left = int(
            (LOGIN_EMAIL_RULE.window_start(desk.clock.now()) + LOGIN_WINDOW - desk.clock.now())
            .total_seconds()
        )
        assert refusal.value.retry_after_seconds == seconds_left
        assert refusal.value.detail == {"retry_after_seconds": seconds_left}

    def test_a_throttled_attempt_verifies_no_password_and_writes_no_event(self, desk: Desk) -> None:
        for _ in range(LOGIN_ATTEMPTS_PER_EMAIL):
            desk.sign_in_refused(email=UNKNOWN_EMAIL)
        with pytest.raises(TooManyAttempts):
            desk.sign_in(email=UNKNOWN_EMAIL)
        assert len(desk.passwords.calls) == LOGIN_ATTEMPTS_PER_EMAIL
        assert len(desk.audit(LOGIN_FAILED_ACTION)) == LOGIN_ATTEMPTS_PER_EMAIL

    def test_the_thirty_first_attempt_from_one_client_is_told_to_wait(self, desk: Desk) -> None:
        for number in range(LOGIN_ATTEMPTS_PER_ADDRESS):
            desk.sign_in_refused(email=f"guess{number}@example.co.za")
        with pytest.raises(TooManyAttempts):
            desk.sign_in(email="one.more@example.co.za")

    def test_another_client_is_not_held_up_by_the_first(self, desk: Desk, account: Account) -> None:
        for number in range(LOGIN_ATTEMPTS_PER_ADDRESS):
            desk.sign_in_refused(email=f"guess{number}@example.co.za")
        elsewhere = ClientDetails(address=ip_address("198.51.100.20"))
        assert desk.sign_in(client=elsewhere).account.id == account.id

    def test_clients_with_no_known_address_share_one_window(self, desk: Desk) -> None:
        nowhere = ClientDetails()
        for number in range(LOGIN_ATTEMPTS_PER_ADDRESS):
            with pytest.raises(InvalidCredentials):
                desk.sign_in(email=f"guess{number}@example.co.za", client=nowhere)
        with pytest.raises(TooManyAttempts):
            desk.sign_in(email="one.more@example.co.za", client=nowhere)

    def test_the_next_window_lets_the_caller_try_again(self, desk: Desk, account: Account) -> None:
        for _ in range(LOGIN_ATTEMPTS_PER_EMAIL):
            desk.sign_in_refused(email=UNKNOWN_EMAIL)
        desk.clock.advance(LOGIN_WINDOW)
        desk.sign_in_refused(email=UNKNOWN_EMAIL)

    def test_the_counters_hold_no_address(self, desk: Desk, account: Account) -> None:
        desk.sign_in()
        keys = "".join(key for key, _window in desk.identity.committed.counters)
        assert KNOWN_EMAIL not in keys
        assert str(CLIENT.address) not in keys
