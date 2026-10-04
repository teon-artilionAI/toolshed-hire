"""The throttle component, with a dictionary where the database would be (C-17).

A window is fixed, a bucket is a salted hash, and counting never deletes
anything, because the lazy sweep prunes old counters, which
tests/unit/test_throttle_pruning.py proves. These prove the three with no
database. The same counting is proved against SQL through the sign in tests,
and against PostgreSQL in tests/integration.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Final

import pytest

from app.application.throttle import (
    LONGEST_THROTTLE_WINDOW,
    SlidingWindow,
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
    """Counters in a dictionary, and a note of every delete it was asked for."""

    counters: dict[tuple[str, datetime], int] = field(default_factory=dict)
    deletes: list[datetime] = field(default_factory=list)

    def increment(self, bucket_key_hash: str, window_started_at: datetime) -> int:
        key = (bucket_key_hash, window_started_at)
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    def delete_windows_before(self, cutoff: datetime, limit: int) -> int:
        self.deletes.append(cutoff)
        return 0

    def total_since(self, bucket_key_hash: str, since: datetime) -> int:
        return sum(
            count
            for (bucket, window_started_at), count in self.counters.items()
            if bucket == bucket_key_hash and window_started_at >= since
        )


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


class TestCountingDeletesNothing:
    """Old counters are left for the sweep, so an attempt never pays for a delete."""

    def test_a_check_and_a_sliding_count_never_ask_for_a_delete(self) -> None:
        throttle, store = Throttle(SALT), DictionaryStore()
        an_old_window = ("an-old-bucket", NOW - timedelta(days=3))
        store.counters[an_old_window] = 7
        failures = SlidingWindow(name="login-failure", span=WINDOW)
        for later in (timedelta(0), timedelta(hours=1), timedelta(days=2)):
            throttle.check(store, RULE, EMAIL, NOW + later)
            throttle.count_in_span(store, failures, EMAIL, NOW + later)
        assert store.deletes == []
        assert store.counters[an_old_window] == 7


class TestARuleThatMakesNoSense:
    """Refused when it is built, not when it is first used."""

    @pytest.mark.parametrize(
        ("name", "limit", "window"),
        [
            ("", 10, WINDOW),
            ("login-email", 0, WINDOW),
            ("login-email", 10, timedelta(0)),
            ("login-email", 10, timedelta(seconds=1.5)),
            ("login-email", 10, LONGEST_THROTTLE_WINDOW + timedelta(seconds=1)),
        ],
    )
    def test_it_is_refused(self, name: str, limit: int, window: timedelta) -> None:
        with pytest.raises(ValueError, match="Attempted to build the throttle rule"):
            ThrottleRule(name=name, limit=limit, window=window)

    def test_a_window_as_long_as_the_longest_is_allowed(self) -> None:
        rule = ThrottleRule(name="register-email", limit=5, window=LONGEST_THROTTLE_WINDOW)
        assert rule.window == LONGEST_THROTTLE_WINDOW
