"""Fixed window throttling and a sliding count, both kept in the database (C-17).

The instances of the service share no memory, so a counter kept in a process
would be a separate counter on each of them. The counts live in
`rate_limit_counter` instead, behind the `RateLimitStore` port.

A rule names what is limited, how many attempts a window allows and how long a
window is. Windows are fixed. They start on multiples of their own length
counted from the Unix epoch, so every instance agrees where one starts without
being told.

A counter is keyed by a salted SHA-256 of the rule and the subject, and never
by the subject. The subject is an email address or a client address, and the
table must not become a list of either. The salt is a secret of the service,
which is what stops the short list of possible addresses being hashed and
matched.

Old windows are deleted here as well. One delete removes every window that
began more than a day ago, and each process issues it at most once in fifteen
minutes, so the table holds a day of counters at most and no request pays for
the housekeeping twice.

A second kind of count slides with the clock. The sign in lockout asks how
many times an account failed in the fifteen minutes that end now (BR-46), and
a fixed window cannot answer that, because five failures can straddle the
moment one window ends and the next begins. So each event of a sliding window
is counted in the second it happened in, and the total is the sum of the
seconds the span covers. That makes the count exact to the second. An event
that is less than a second older than the span is still counted, which errs
towards counting an event and never towards missing one.

This belongs to no module. Signing in, registration, the verification email
and the password reset all use the same component with rules of their own.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final, Protocol

logger = logging.getLogger(__name__)

# How long a finished window is kept before it is deleted. No rule may use a
# longer window than this, or its live counter would be swept.
SWEEP_RETENTION: Final[timedelta] = timedelta(hours=24)
# How often one process deletes old windows.
SWEEP_INTERVAL: Final[timedelta] = timedelta(minutes=15)
MINIMUM_RETRY_AFTER_SECONDS: Final[int] = 1
# How finely an event of a sliding window is timed.
SLIDING_RESOLUTION: Final[timedelta] = timedelta(seconds=1)
KEY_SEPARATOR: Final[str] = "\x1f"
KEY_ENCODING: Final[str] = "utf-8"


class RateLimitStore(Protocol):
    """Where the counters are kept."""

    def increment(self, bucket_key_hash: str, window_started_at: datetime) -> int:
        """Add one to the counter of a bucket and a window, and return the new count.

        The first attempt of a window creates the counter at one. The step is
        atomic, so two attempts at once are both counted.
        """
        ...

    def delete_windows_before(self, cutoff: datetime) -> int:
        """Delete every counter whose window began before `cutoff`, and return how many."""
        ...

    def total_since(self, bucket_key_hash: str, since: datetime) -> int:
        """Return the sum of the counters of a bucket whose windows began at or after `since`."""
        ...


@dataclass(frozen=True, slots=True)
class ThrottleRule:
    """What is limited, how many attempts a window allows and how long a window is.

    Attributes:
        name: A short name that keeps the counters of two rules apart, for
            example `login-email`.
        limit: How many attempts one subject may make in one window.
        window: The length of a window.

    """

    name: str
    limit: int
    window: timedelta

    def __post_init__(self) -> None:
        """Refuse a rule that could never allow anything or never be swept safely.

        Raises:
            ValueError: If the name is blank, the limit is below one, or the
                window is not a whole number of seconds between one second
                and the sweep retention.

        """
        seconds = self.window.total_seconds()
        if not self.name.strip() or self.limit < 1:
            raise ValueError(
                f"Attempted to build the throttle rule {self.name!r} with a limit of "
                f"{self.limit}. A rule needs a name and a limit of at least 1."
            )
        if seconds < 1 or seconds != int(seconds) or self.window > SWEEP_RETENTION:
            raise ValueError(
                f"Attempted to build the throttle rule {self.name!r} with a window of "
                f"{self.window}. A window is a whole number of seconds, at least one and at "
                f"most {SWEEP_RETENTION}."
            )

    def window_start(self, now: datetime) -> datetime:
        """Return the start of the fixed window that `now` falls in."""
        length = int(self.window.total_seconds())
        return datetime.fromtimestamp(int(now.timestamp()) // length * length, tz=UTC)


@dataclass(frozen=True, slots=True)
class SlidingWindow:
    """What is counted over a span of time that ends at the present moment.

    Attributes:
        name: A short name that keeps its counters apart from every other
            count, for example `login-failure`.
        span: How far back from now an event still counts.

    """

    name: str
    span: timedelta

    def __post_init__(self) -> None:
        """Refuse a window with no name, or a span the sweep would cut short.

        Raises:
            ValueError: If the name is blank, or the span is not a whole
                number of seconds between one second and the sweep retention.

        """
        seconds = self.span.total_seconds()
        if not self.name.strip():
            raise ValueError("Attempted to build a sliding window with no name.")
        if seconds < 1 or seconds != int(seconds) or self.span > SWEEP_RETENTION:
            raise ValueError(
                f"Attempted to build the sliding window {self.name!r} with a span of "
                f"{self.span}. A span is a whole number of seconds, at least one and at "
                f"most {SWEEP_RETENTION}."
            )

    def second_of(self, now: datetime) -> datetime:
        """Return the start of the second `now` falls in, which is where an event is counted."""
        resolution = int(SLIDING_RESOLUTION.total_seconds())
        return datetime.fromtimestamp(int(now.timestamp()) // resolution * resolution, tz=UTC)


@dataclass(frozen=True, slots=True)
class ThrottleVerdict:
    """Whether an attempt may go ahead, and how long to wait when it may not.

    Attributes:
        allowed: False when the attempt went over the limit of its window.
        attempts: How many attempts the window has seen, this one included.
        retry_after_seconds: The seconds until the window ends, at least one.

    """

    allowed: bool
    attempts: int
    retry_after_seconds: int


class Throttle:
    """Counts attempts against rules. One instance serves the whole process."""

    def __init__(self, salt: str) -> None:
        """Create the throttle.

        Args:
            salt: A secret of the service, mixed into every bucket key.

        Raises:
            ValueError: If the salt is blank, which would leave the keys as
                plain hashes of addresses that anybody could reproduce.

        """
        if not salt:
            raise ValueError(
                "Attempted to build a throttle with no salt. The bucket keys are hashes of "
                "email and client addresses, and without a secret salt they can be matched."
            )
        self._salt = salt
        self._sweep_lock = threading.Lock()
        self._next_sweep_at: datetime | None = None

    def bucket_key_hash(self, rule: ThrottleRule | SlidingWindow, subject: str) -> str:
        """Return the salted SHA-256 that stands for one subject under one rule."""
        material = KEY_SEPARATOR.join((self._salt, rule.name, subject))
        return hashlib.sha256(material.encode(KEY_ENCODING)).hexdigest()

    def count_in_span(
        self, store: RateLimitStore, window: SlidingWindow, subject: str, now: datetime
    ) -> int:
        """Count one event and return how many the span that ends at `now` holds.

        Args:
            store: The counters, inside the transaction of the caller.
            window: What is being counted and over how long a span.
            subject: Who or what the event belongs to. It is hashed and never stored.
            now: The current instant, from the clock.

        Returns:
            The events of this subject inside the span, this one included.

        """
        bucket = self.bucket_key_hash(window, subject)
        second = window.second_of(now)
        store.increment(bucket, second)
        events = store.total_since(bucket, second - window.span)
        logger.debug(
            "throttle.event_counted",
            extra={
                "window": window.name,
                "events_in_span": events,
                "span_seconds": int(window.span.total_seconds()),
            },
        )
        return events

    def check(
        self, store: RateLimitStore, rule: ThrottleRule, subject: str, now: datetime
    ) -> ThrottleVerdict:
        """Count one attempt and say whether it is within the limit.

        Args:
            store: The counters, inside the transaction of the caller.
            rule: The rule the attempt is counted against.
            subject: Who or what is attempting. It is hashed and never stored.
            now: The current instant, from the clock.

        """
        self._sweep_when_due(store, now)
        window_start = rule.window_start(now)
        attempts = store.increment(self.bucket_key_hash(rule, subject), window_start)
        allowed = attempts <= rule.limit
        retry_after = int((window_start + rule.window - now).total_seconds())
        verdict = ThrottleVerdict(
            allowed=allowed,
            attempts=attempts,
            retry_after_seconds=max(MINIMUM_RETRY_AFTER_SECONDS, retry_after),
        )
        log = logger.debug if allowed else logger.warning
        log(
            "throttle.attempt_counted",
            extra={
                "rule": rule.name,
                "attempts": attempts,
                "limit": rule.limit,
                "allowed": allowed,
                "retry_after_seconds": verdict.retry_after_seconds,
            },
        )
        return verdict

    def _sweep_when_due(self, store: RateLimitStore, now: datetime) -> None:
        """Delete the old windows, at most once per interval in this process."""
        with self._sweep_lock:
            if self._next_sweep_at is not None and now < self._next_sweep_at:
                return
            self._next_sweep_at = now + SWEEP_INTERVAL
        deleted = store.delete_windows_before(now - SWEEP_RETENTION)
        logger.info(
            "throttle.windows_swept",
            extra={
                "deleted_count": deleted,
                "retention_seconds": int(SWEEP_RETENTION.total_seconds()),
            },
        )
