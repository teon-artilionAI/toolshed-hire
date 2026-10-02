"""The throttle component, with a dictionary where the database would be (C-17).

A window is fixed, a bucket is a salted hash and an old window is deleted.
These prove the three with no database. The same counting is proved against
SQL through the sign in tests, and against PostgreSQL in tests/integration.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Final

import pytest

from app.application.throttle import (
    SWEEP_INTERVAL,
    SWEEP_RETENTION,
    Throttle,
    ThrottleRule,
)

NOW: Final[datetime] = datetime(2026, 3, 2, 8, 7, 30, tzinfo=UTC)
WINDOW: Final[timedelta] = timedelta(minutes=15)
WINDOW_START: Final[datetime] = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
LIMIT: Final[int] = 3
RULE: Final[ThrottleRule] = ThrottleRule(name="login-email", limit=LIMIT, window=WINDOW)
OTHER_RULE: Final[ThrottleRule] = ThrottleRule(name="login-address", limit=LIMIT, window=WINDOW)
SALT: Final[str] = "made-up-salt-for-this-test"
EMAIL: Final[str] = "nomsa.dlamini@example.co.za"
ADDRESS: Final[str] = "203.0.113.9"
SHA256_HEX_LENGTH: Final[int] = 64
SECONDS_LEFT_IN_WINDOW: Final[int] = 450


@dataclass
class DictionaryStore:
    """Counters in a dictionary, and a note of every sweep it was asked for."""

    counters: dict[tuple[str, datetime], int] = field(default_factory=dict)
    sweeps: list[datetime] = field(default_factory=list)

    def increment(self, bucket_key_hash: str, window_started_at: datetime) -> int:
        key = (bucket_key_hash, window_started_at)
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    def delete_windows_before(self, cutoff: datetime) -> int:
        self.sweeps.append(cutoff)
        expired = [key for key in self.counters if key[1] < cutoff]
        for key in expired:
            del self.counters[key]
        return len(expired)


class TestTheFixedWindow:
    """A window starts on a multiple of its own length and allows `limit` attempts."""

    def test_a_window_starts_on_a_multiple_of_its_length(self) -> None:
        assert RULE.window_start(NOW) == WINDOW_START
        assert RULE.window_start(WINDOW_START) == WINDOW_START
        assert RULE.window_start(WINDOW_START + WINDOW) == WINDOW_START + WINDOW

    def test_attempts_up_to_the_limit_are_allowed_and_the_next_is_not(self) -> None:
        throttle, store = Throttle(SALT), DictionaryStore()
        verdicts = [throttle.check(store, RULE, EMAIL, NOW) for _ in range(LIMIT + 1)]
        assert [verdict.allowed for verdict in verdicts] == [True, True, True, False]
        assert [verdict.attempts for verdict in verdicts] == [1, 2, 3, 4]

    def test_the_wait_is_the_time_left_in_the_window_in_seconds(self) -> None:
        verdict = Throttle(SALT).check(DictionaryStore(), RULE, EMAIL, NOW)
        assert verdict.retry_after_seconds == SECONDS_LEFT_IN_WINDOW

    def test_the_wait_is_never_less_than_a_second(self) -> None:
        last_instant = WINDOW_START + WINDOW - timedelta(milliseconds=200)
        verdict = Throttle(SALT).check(DictionaryStore(), RULE, EMAIL, last_instant)
        assert verdict.retry_after_seconds == 1

    def test_the_next_window_starts_from_nothing(self) -> None:
        throttle, store = Throttle(SALT), DictionaryStore()
        for _ in range(LIMIT + 1):
            throttle.check(store, RULE, EMAIL, NOW)
        verdict = throttle.check(store, RULE, EMAIL, NOW + WINDOW)
        assert verdict.allowed
        assert verdict.attempts == 1

    def test_two_subjects_and_two_rules_are_counted_apart(self) -> None:
        throttle, store = Throttle(SALT), DictionaryStore()
        for _ in range(LIMIT):
            throttle.check(store, RULE, EMAIL, NOW)
        assert throttle.check(store, RULE, "someone.else@example.co.za", NOW).attempts == 1
        assert throttle.check(store, OTHER_RULE, EMAIL, NOW).attempts == 1


class TestTheBucketKey:
    """A salted SHA-256, never the address it stands for."""

    def test_the_stored_key_is_a_digest_and_does_not_hold_the_subject(self) -> None:
        throttle, store = Throttle(SALT), DictionaryStore()
        throttle.check(store, RULE, EMAIL, NOW)
        throttle.check(store, OTHER_RULE, ADDRESS, NOW)
        for key, _window in store.counters:
            assert len(key) == SHA256_HEX_LENGTH
            assert EMAIL not in key
            assert ADDRESS not in key

    def test_the_key_is_not_the_plain_hash_of_the_subject(self) -> None:
        key = Throttle(SALT).bucket_key_hash(OTHER_RULE, ADDRESS)
        assert key != hashlib.sha256(ADDRESS.encode("utf-8")).hexdigest()

    def test_a_different_salt_gives_a_different_key(self) -> None:
        first = Throttle(SALT).bucket_key_hash(RULE, EMAIL)
        second = Throttle("another-made-up-salt").bucket_key_hash(RULE, EMAIL)
        assert first != second

    def test_a_throttle_with_no_salt_is_refused(self) -> None:
        with pytest.raises(ValueError, match="no salt"):
            Throttle("")


class TestSweepingOldWindows:
    """Old windows are deleted, at most once per interval in one process."""

    def test_the_first_check_sweeps_windows_older_than_the_retention(self) -> None:
        throttle, store = Throttle(SALT), DictionaryStore()
        store.counters[("an-old-bucket", NOW - SWEEP_RETENTION - WINDOW)] = 7
        store.counters[("a-recent-bucket", NOW - WINDOW)] = 2
        throttle.check(store, RULE, EMAIL, NOW)
        assert store.sweeps == [NOW - SWEEP_RETENTION]
        assert ("an-old-bucket", NOW - SWEEP_RETENTION - WINDOW) not in store.counters
        assert ("a-recent-bucket", NOW - WINDOW) in store.counters

    def test_a_second_check_inside_the_interval_does_not_sweep_again(self) -> None:
        throttle, store = Throttle(SALT), DictionaryStore()
        throttle.check(store, RULE, EMAIL, NOW)
        throttle.check(store, RULE, EMAIL, NOW + SWEEP_INTERVAL - timedelta(seconds=1))
        assert len(store.sweeps) == 1

    def test_a_check_after_the_interval_sweeps_again(self) -> None:
        throttle, store = Throttle(SALT), DictionaryStore()
        throttle.check(store, RULE, EMAIL, NOW)
        throttle.check(store, RULE, EMAIL, NOW + SWEEP_INTERVAL)
        assert len(store.sweeps) == 2


class TestARuleThatMakesNoSense:
    """Refused when it is built, not when it is first used."""

    @pytest.mark.parametrize(
        ("name", "limit", "window"),
        [
            ("", 10, WINDOW),
            ("login-email", 0, WINDOW),
            ("login-email", 10, timedelta(0)),
            ("login-email", 10, timedelta(seconds=1.5)),
            ("login-email", 10, SWEEP_RETENTION + timedelta(seconds=1)),
        ],
    )
    def test_it_is_refused(self, name: str, limit: int, window: timedelta) -> None:
        with pytest.raises(ValueError, match="Attempted to build the throttle rule"):
            ThrottleRule(name=name, limit=limit, window=window)
