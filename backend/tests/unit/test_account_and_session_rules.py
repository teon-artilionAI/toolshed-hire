"""The lockout rule of an account and the lifetimes of a refresh session.

These are the rules of BR-46 and BR-48 with nothing around them. No database,
no HTTP and no hashing, only the two entities and a moment in time the test
chooses.

An account is told how many failures the last fifteen minutes hold, and here
the test is what tells it. The window itself, counted second by second, is
proved in test_lockout_window.py.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import uuid4

from app.domain.account import (
    FAILED_LOGIN_WINDOW,
    LOCKOUT_DURATION,
    MAXIMUM_FAILED_LOGINS,
    Account,
)
from app.domain.enums import RevokeReason, UserRole
from app.domain.session import (
    REFRESH_ABSOLUTE_LIFETIME,
    REFRESH_IDLE_LIFETIME,
    USER_AGENT_MAX_LENGTH,
    RefreshSession,
    hash_refresh_token,
    mint_refresh_token,
)

NOW: Final[datetime] = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
ONE_SECOND: Final[timedelta] = timedelta(seconds=1)
MINIMUM_TOKEN_BITS: Final[int] = 128
BITS_PER_URLSAFE_CHARACTER: Final[int] = 6
SHA256_HEX_LENGTH: Final[int] = 64
FAKE_TOKEN: Final[str] = "made-up-refresh-token-for-this-test"
MINTED_SAMPLE: Final[int] = 50


def account() -> Account:
    return Account(
        id=uuid4(),
        email="nomsa.dlamini@example.co.za",
        password_hash="stand-in-hash",
        role=UserRole.CUSTOMER,
        full_name="Nomsa Dlamini",
    )


def fail(subject: Account, times: int, now: datetime = NOW) -> list[bool]:
    """Fail a sign in `times` times at one instant, with every failure inside the window."""
    return [
        subject.record_failed_login(now, failures_in_window=subject.failed_login_count + 1)
        for _ in range(times)
    ]


def opened(now: datetime = NOW) -> RefreshSession:
    return RefreshSession.opened_at_sign_in(
        user_account_id=uuid4(),
        token_hash=hash_refresh_token(FAKE_TOKEN),
        now=now,
        user_agent="A browser",
        ip_address=None,
    )


class TestTheLockout:
    """Five failures inside fifteen minutes lock the account for fifteen minutes (BR-46)."""

    def test_the_limits_are_the_ones_the_design_document_states(self) -> None:
        assert MAXIMUM_FAILED_LOGINS == 5
        assert timedelta(minutes=15) == FAILED_LOGIN_WINDOW
        assert timedelta(minutes=15) == LOCKOUT_DURATION

    def test_four_failures_do_not_lock(self) -> None:
        subject = account()
        assert fail(subject, MAXIMUM_FAILED_LOGINS - 1) == [False, False, False, False]
        assert not subject.is_locked(NOW)

    def test_the_fifth_failure_locks_for_fifteen_minutes(self) -> None:
        subject = account()
        outcomes = fail(subject, MAXIMUM_FAILED_LOGINS)
        assert outcomes[-1] is True
        assert subject.locked_until == NOW + LOCKOUT_DURATION
        assert subject.is_locked(NOW + LOCKOUT_DURATION - ONE_SECOND)

    def test_the_lock_ends_exactly_when_its_time_is_up(self) -> None:
        subject = account()
        fail(subject, MAXIMUM_FAILED_LOGINS)
        assert not subject.is_locked(NOW + LOCKOUT_DURATION)

    def test_a_success_clears_the_count_and_notes_the_sign_in(self) -> None:
        subject = account()
        fail(subject, 2)
        subject.record_successful_login(NOW + ONE_SECOND)
        assert subject.failed_login_count == 0
        assert subject.locked_until is None
        assert subject.last_login_at == NOW + ONE_SECOND

    def test_the_first_failure_after_a_lock_ran_out_starts_the_count_again(self) -> None:
        subject = account()
        fail(subject, MAXIMUM_FAILED_LOGINS)
        later = NOW + LOCKOUT_DURATION + ONE_SECOND
        assert subject.record_failed_login(later, failures_in_window=1) is False
        assert subject.failed_login_count == 1
        assert not subject.is_locked(later)

    def test_a_failure_the_window_has_let_go_of_is_not_counted(self) -> None:
        # Four failures, and by the fifth the window only holds two of them.
        subject = account()
        fail(subject, MAXIMUM_FAILED_LOGINS - 1)
        later = NOW + FAILED_LOGIN_WINDOW
        assert subject.record_failed_login(later, failures_in_window=2) is False
        assert subject.failed_login_count == 2

    def test_a_failure_from_before_a_success_is_not_counted_while_its_window_runs(
        self,
    ) -> None:
        # The window still holds the four failures from before the success.
        # The account's own count went back to zero, and the smaller number wins.
        subject = account()
        fail(subject, MAXIMUM_FAILED_LOGINS - 1)
        subject.record_successful_login(NOW)
        locked = subject.record_failed_login(NOW, failures_in_window=MAXIMUM_FAILED_LOGINS)
        assert locked is False
        assert subject.failed_login_count == 1

    def test_a_window_that_reports_nothing_still_counts_the_failure_itself(self) -> None:
        subject = account()
        subject.record_failed_login(NOW, failures_in_window=0)
        assert subject.failed_login_count == 1

    def test_clearing_the_lockout_forgets_the_failures_and_lifts_the_lock(self) -> None:
        subject = account()
        fail(subject, MAXIMUM_FAILED_LOGINS)
        subject.clear_lockout()
        assert subject.failed_login_count == 0
        assert not subject.is_locked(NOW)

    def test_an_account_becomes_the_actor_with_its_role_and_branch(self) -> None:
        branch_id = uuid4()
        subject = account()
        subject.role = UserRole.COUNTER_STAFF
        subject.branch_id = branch_id
        actor = subject.as_actor()
        assert (actor.user_id, actor.role, actor.branch_id) == (
            subject.id,
            UserRole.COUNTER_STAFF,
            branch_id,
        )

    def test_the_stored_hash_is_left_out_of_the_representation(self) -> None:
        assert "stand-in-hash" not in repr(account())


class TestTheRefreshToken:
    """Opaque, random and stored only as its SHA-256."""

    def test_a_token_carries_at_least_128_bits(self) -> None:
        token = mint_refresh_token()
        assert len(token) * BITS_PER_URLSAFE_CHARACTER >= MINIMUM_TOKEN_BITS

    def test_no_two_tokens_are_the_same(self) -> None:
        assert len({mint_refresh_token() for _ in range(MINTED_SAMPLE)}) == MINTED_SAMPLE

    def test_the_stored_form_is_the_sha256_of_the_token(self) -> None:
        digest = hash_refresh_token(FAKE_TOKEN)
        assert digest == hashlib.sha256(FAKE_TOKEN.encode("utf-8")).hexdigest()
        assert len(digest) == SHA256_HEX_LENGTH
        assert FAKE_TOKEN not in digest

    def test_the_hash_is_left_out_of_the_representation_of_a_session(self) -> None:
        assert hash_refresh_token(FAKE_TOKEN) not in repr(opened())


class TestTheLifetimesOfASession:
    """Fourteen days from the sign in, and seven days from the last use (BR-48)."""

    def test_the_lifetimes_are_the_ones_the_design_document_states(self) -> None:
        assert timedelta(days=14) == REFRESH_ABSOLUTE_LIFETIME
        assert timedelta(days=7) == REFRESH_IDLE_LIFETIME

    def test_a_new_session_ends_after_seven_idle_days(self) -> None:
        session = opened()
        assert session.expires_at == NOW + REFRESH_ABSOLUTE_LIFETIME
        assert not session.is_expired(NOW + REFRESH_IDLE_LIFETIME - ONE_SECOND)
        assert session.is_expired(NOW + REFRESH_IDLE_LIFETIME)

    def test_a_session_kept_busy_still_ends_fourteen_days_after_the_sign_in(self) -> None:
        session = opened()
        for day in (6, 12):
            session = session.rotate(
                token_hash=hash_refresh_token(f"{FAKE_TOKEN}-{day}"),
                now=NOW + timedelta(days=day),
                user_agent=None,
                ip_address=None,
            )
        assert session.expires_at == NOW + REFRESH_ABSOLUTE_LIFETIME
        assert not session.is_expired(NOW + REFRESH_ABSOLUTE_LIFETIME - ONE_SECOND)
        assert session.is_expired(NOW + REFRESH_ABSOLUTE_LIFETIME)

    def test_the_seconds_left_are_those_of_whichever_lifetime_ends_first(self) -> None:
        session = opened()
        assert session.seconds_left(NOW) == int(REFRESH_IDLE_LIFETIME.total_seconds())
        late = session.rotate(
            token_hash=hash_refresh_token(f"{FAKE_TOKEN}-late"),
            now=NOW + timedelta(days=13),
            user_agent=None,
            ip_address=None,
        )
        assert late.seconds_left(NOW + timedelta(days=13)) == int(
            timedelta(days=1).total_seconds()
        )
        assert late.seconds_left(NOW + timedelta(days=30)) == 0

    def test_rotating_stamps_the_old_session_and_keeps_the_family(self) -> None:
        session = opened()
        successor = session.rotate(
            token_hash=hash_refresh_token(f"{FAKE_TOKEN}-next"),
            now=NOW + ONE_SECOND,
            user_agent="Another browser",
            ip_address=None,
        )
        assert session.was_rotated
        assert session.is_revoked
        assert session.revoked_reason is RevokeReason.ROTATION
        assert successor.family_id == session.family_id
        assert successor.id != session.id
        assert not successor.was_rotated
        assert not successor.is_revoked

    def test_a_long_or_blank_user_agent_is_fitted_to_its_column(self) -> None:
        long = RefreshSession.opened_at_sign_in(
            user_account_id=uuid4(),
            token_hash=hash_refresh_token(FAKE_TOKEN),
            now=NOW,
            user_agent="x" * (USER_AGENT_MAX_LENGTH + 50),
            ip_address=None,
        )
        blank = RefreshSession.opened_at_sign_in(
            user_account_id=uuid4(),
            token_hash=hash_refresh_token(FAKE_TOKEN),
            now=NOW,
            user_agent="   ",
            ip_address=None,
        )
        assert long.user_agent is not None
        assert len(long.user_agent) == USER_AGENT_MAX_LENGTH
        assert blank.user_agent is None
