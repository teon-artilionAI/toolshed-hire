"""The lockout window, with no database (BR-46).

Five failed sign ins inside fifteen minutes lock an account for fifteen
minutes. The window slides with the clock. It is not a count of failures in a
row and it is not a fixed quarter of an hour, so these move the clock between
attempts and prove both.

The first class runs the sign in use case over the in memory stores. The
second proves the count underneath it, which is one counter for each second a
failure fell in and a sum over the seconds the span covers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Final

import pytest

from app.application.identity.sign_in import LOGIN_FAILURES
from app.application.throttle import SWEEP_RETENTION, SlidingWindow, Throttle
from app.domain.account import (
    FAILED_LOGIN_WINDOW,
    LOCKOUT_DURATION,
    MAXIMUM_FAILED_LOGINS,
    Account,
)
from tests.support.identity_desk import FAKE_SALT, Desk
from tests.support.memory_identity import KNOWN_PASSWORD

ONE_SECOND: Final[timedelta] = timedelta(seconds=1)
ONE_MINUTE: Final[timedelta] = timedelta(minutes=1)
FOUR_MINUTES: Final[timedelta] = timedelta(minutes=4)
NOW: Final[datetime] = datetime(2026, 3, 2, 8, 7, 30, 250000, tzinfo=UTC)
WINDOW: Final[SlidingWindow] = SlidingWindow(name="login-failure", span=timedelta(minutes=15))
SUBJECT: Final[str] = "an-account-key"
SHA256_HEX_LENGTH: Final[int] = 64


@dataclass
class DictionaryStore:
    """Counters in a dictionary, where the database would be."""

    counters: dict[tuple[str, datetime], int] = field(default_factory=dict)

    def increment(self, bucket_key_hash: str, window_started_at: datetime) -> int:
        key = (bucket_key_hash, window_started_at)
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    def delete_windows_before(self, cutoff: datetime) -> int:
        return 0

    def total_since(self, bucket_key_hash: str, since: datetime) -> int:
        return sum(
            count
            for (bucket, second), count in self.counters.items()
            if bucket == bucket_key_hash and second >= since
        )


@pytest.fixture
def desk() -> Desk:
    return Desk()


@pytest.fixture
def account(desk: Desk) -> Account:
    return desk.identity.add_account()


def fail(desk: Desk, times: int, *, every: timedelta = timedelta(0)) -> None:
    """Fail `times` sign ins, moving the clock on by `every` before each one but the first."""
    for attempt in range(times):
        if attempt:
            desk.clock.advance(every)
        desk.sign_in_refused()


class TestTheWindowOfTheLockout:
    """Five failures inside fifteen minutes, wherever those fifteen minutes fall."""

    def test_the_window_is_the_fifteen_minutes_the_design_document_states(self) -> None:
        assert LOGIN_FAILURES.span == FAILED_LOGIN_WINDOW == timedelta(minutes=15)

    def test_four_failures_then_a_success_leave_nothing_counted(
        self, desk: Desk, account: Account
    ) -> None:
        fail(desk, MAXIMUM_FAILED_LOGINS - 1, every=ONE_MINUTE)
        desk.sign_in()
        assert desk.identity.account(account.id).failed_login_count == 0
        fail(desk, MAXIMUM_FAILED_LOGINS - 1, every=ONE_SECOND)
        stored = desk.identity.account(account.id)
        assert stored.failed_login_count == MAXIMUM_FAILED_LOGINS - 1
        assert stored.locked_until is None
        assert desk.sign_in(password=KNOWN_PASSWORD).account.id == account.id

    def test_five_failures_inside_the_window_lock_the_account(
        self, desk: Desk, account: Account
    ) -> None:
        fail(desk, MAXIMUM_FAILED_LOGINS, every=timedelta(minutes=3))
        stored = desk.identity.account(account.id)
        assert stored.failed_login_count == MAXIMUM_FAILED_LOGINS
        assert stored.locked_until == desk.clock.now() + LOCKOUT_DURATION
        desk.sign_in_refused(password=KNOWN_PASSWORD)

    def test_five_failures_spread_over_more_than_fifteen_minutes_do_not_lock(
        self, desk: Desk, account: Account
    ) -> None:
        fail(desk, MAXIMUM_FAILED_LOGINS, every=FOUR_MINUTES)
        stored = desk.identity.account(account.id)
        assert stored.locked_until is None
        assert stored.failed_login_count == MAXIMUM_FAILED_LOGINS - 1
        assert desk.sign_in(password=KNOWN_PASSWORD).account.id == account.id

    def test_a_slow_guesser_is_never_locked(self, desk: Desk, account: Account) -> None:
        fail(desk, MAXIMUM_FAILED_LOGINS * 2, every=FOUR_MINUTES)
        assert desk.identity.account(account.id).locked_until is None

    def test_five_failures_that_straddle_a_quarter_hour_still_lock(
        self, desk: Desk, account: Account
    ) -> None:
        # The fixed clock starts on the hour. Four failures at fourteen minutes
        # past and a fifth at sixteen past sit in two fixed windows and in one
        # sliding one.
        desk.clock.advance(timedelta(minutes=14))
        fail(desk, MAXIMUM_FAILED_LOGINS - 1)
        desk.clock.advance(timedelta(minutes=2))
        desk.sign_in_refused()
        assert desk.identity.account(account.id).locked_until is not None

    def test_the_oldest_failure_stops_counting_a_second_after_fifteen_minutes(
        self, desk: Desk, account: Account
    ) -> None:
        fail(desk, MAXIMUM_FAILED_LOGINS - 1)
        desk.clock.advance(FAILED_LOGIN_WINDOW + ONE_SECOND)
        desk.sign_in_refused()
        stored = desk.identity.account(account.id)
        assert stored.failed_login_count == 1
        assert stored.locked_until is None

    def test_a_failure_exactly_fifteen_minutes_old_is_still_counted(
        self, desk: Desk, account: Account
    ) -> None:
        fail(desk, MAXIMUM_FAILED_LOGINS - 1)
        desk.clock.advance(FAILED_LOGIN_WINDOW)
        desk.sign_in_refused()
        assert desk.identity.account(account.id).locked_until is not None

    def test_the_count_starts_again_once_a_lock_has_run_out(
        self, desk: Desk, account: Account
    ) -> None:
        fail(desk, MAXIMUM_FAILED_LOGINS)
        desk.clock.advance(LOCKOUT_DURATION + ONE_SECOND)
        desk.sign_in_refused()
        stored = desk.identity.account(account.id)
        assert stored.failed_login_count == 1
        assert stored.locked_until is None

    def test_an_attempt_refused_for_the_lock_is_not_a_failure_of_its_own(
        self, desk: Desk, account: Account
    ) -> None:
        fail(desk, MAXIMUM_FAILED_LOGINS)
        locked_until = desk.identity.account(account.id).locked_until
        desk.clock.advance(ONE_MINUTE)
        desk.sign_in_refused()
        stored = desk.identity.account(account.id)
        assert stored.failed_login_count == MAXIMUM_FAILED_LOGINS
        assert stored.locked_until == locked_until

    def test_the_failures_of_one_account_do_not_count_against_another(
        self, desk: Desk, account: Account
    ) -> None:
        other = desk.identity.add_account(email="sipho.ndlovu@example.co.za")
        fail(desk, MAXIMUM_FAILED_LOGINS - 1)
        desk.sign_in_refused(email=other.email)
        assert desk.identity.account(other.id).failed_login_count == 1

    def test_the_counters_hold_a_hash_and_never_the_key_of_the_account(
        self, desk: Desk, account: Account
    ) -> None:
        desk.sign_in_refused()
        keys = [key for key, _second in desk.identity.committed.counters]
        assert all(len(key) == SHA256_HEX_LENGTH for key in keys)
        assert str(account.id) not in "".join(keys)


class TestTheSlidingCount:
    """One counter for each second, and the sum of the seconds a span covers."""

    def count(self, store: DictionaryStore, now: datetime) -> int:
        return Throttle(FAKE_SALT).count_in_span(store, WINDOW, SUBJECT, now)

    def test_each_event_is_counted_and_included_in_the_total(self) -> None:
        store = DictionaryStore()
        assert [self.count(store, NOW) for _ in range(3)] == [1, 2, 3]

    def test_an_event_is_kept_under_the_second_it_fell_in(self) -> None:
        store = DictionaryStore()
        self.count(store, NOW)
        ((bucket, second),) = store.counters
        assert second == NOW.replace(microsecond=0)
        assert WINDOW.second_of(NOW) == second
        assert len(bucket) == SHA256_HEX_LENGTH
        assert SUBJECT not in bucket

    def test_an_event_older_than_the_span_drops_out_of_the_total(self) -> None:
        store = DictionaryStore()
        self.count(store, NOW)
        assert self.count(store, NOW + WINDOW.span) == 2
        assert self.count(store, NOW + WINDOW.span + ONE_SECOND) == 2
        assert self.count(store, NOW + WINDOW.span * 3) == 1

    def test_another_subject_and_another_window_are_counted_apart(self) -> None:
        store = DictionaryStore()
        throttle = Throttle(FAKE_SALT)
        other_window = SlidingWindow(name="something-else", span=WINDOW.span)
        throttle.count_in_span(store, WINDOW, SUBJECT, NOW)
        assert throttle.count_in_span(store, WINDOW, "another-account-key", NOW) == 1
        assert throttle.count_in_span(store, other_window, SUBJECT, NOW) == 1

    @pytest.mark.parametrize("name", ["", "   "])
    def test_a_window_needs_a_name(self, name: str) -> None:
        with pytest.raises(ValueError, match="with no name"):
            SlidingWindow(name=name, span=WINDOW.span)

    @pytest.mark.parametrize(
        "span",
        [timedelta(0), timedelta(milliseconds=1500), SWEEP_RETENTION + ONE_SECOND],
        ids=["nothing", "part of a second", "longer than a counter is kept"],
    )
    def test_a_span_is_whole_seconds_and_no_longer_than_a_counter_is_kept(
        self, span: timedelta
    ) -> None:
        with pytest.raises(ValueError, match="A span is a whole number of seconds"):
            SlidingWindow(name="login-failure", span=span)
