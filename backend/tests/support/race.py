"""Plumbing for tests that run two real transactions at the same time.

A concurrency test is only worth having if the two transactions genuinely
overlap. Two things make that true here. A `threading.Barrier` holds both
contenders until the other has arrived, so neither can finish before the other
starts. And `wait_until_backend_is_blocked` lets a test wait for the moment one
connection is actually stuck behind another's lock, using PostgreSQL's own view
of its backends rather than a sleep long enough to "probably" be sufficient. A
sleep would make the test slow when it works and flaky when it does not.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Final

from sqlalchemy import text
from sqlmodel import Session

logger = logging.getLogger(__name__)

CONTENDER_COUNT: Final[int] = 2
EXPECTED_WINNERS: Final[int] = 1
# Long enough to cover two local transactions, short enough that a deadlock
# fails the suite in seconds rather than hanging until the job timeout kills it
# with no explanation at all.
BARRIER_TIMEOUT_SECONDS: Final[float] = 15.0
RESULT_TIMEOUT_SECONDS: Final[float] = 30.0
BLOCKED_WAIT_TIMEOUT_SECONDS: Final[float] = 15.0
BLOCKED_POLL_SECONDS: Final[float] = 0.02


@dataclass(frozen=True, slots=True)
class Outcome:
    """What one contender's transaction did.

    Attributes:
        succeeded: True when the transaction committed.
        error: The exception that ended it, if it did not.
        sqlstate: The five character SQLSTATE the driver reported, if any.
        constraint: The constraint the database named in its diagnostics.

    """

    succeeded: bool
    error: Exception | None = None
    sqlstate: str | None = None
    constraint: str | None = None


# One contender, already bound to its engine, its work and its synchronisation.
type Contender = Callable[[], Outcome]


def run_race(first: Contender, second: Contender) -> list[Outcome]:
    """Run two contenders at the same time and return both outcomes.

    Args:
        first: A zero argument callable returning an Outcome.
        second: The other one.

    Returns:
        Both outcomes, in submission order.

    Raises:
        TimeoutError: If either contender has not finished within the result
            timeout, which means the two have deadlocked in a way PostgreSQL
            did not resolve and the test must not hang waiting for.

    """
    with ThreadPoolExecutor(max_workers=CONTENDER_COUNT) as pool:
        futures = [pool.submit(contender) for contender in (first, second)]
        outcomes = [future.result(timeout=RESULT_TIMEOUT_SECONDS) for future in futures]
    logger.info(
        "test.race_finished",
        extra={"winners": sum(outcome.succeeded for outcome in outcomes)},
    )
    return outcomes


def backend_pid(session: Session) -> int:
    """Return the server side process id of this session's connection.

    The caller must not commit or roll back between this call and the work it
    intends to watch. A session releases its connection when its transaction
    ends, and against a NullPool engine releasing means closing, so the next
    statement would run on a different backend with a different process id and
    the watcher would be watching a process that no longer exists.
    """
    return int(session.execute(text("SELECT pg_backend_pid()")).scalar_one())


def wait_until_backend_is_blocked(
    session: Session, pid: int, *, timeout: float = BLOCKED_WAIT_TIMEOUT_SECONDS
) -> None:
    """Block until the named backend is waiting on a lock.

    Used to stage a race deterministically: the first writer holds its
    uncommitted row until the second writer is provably stuck behind it, so the
    second writer is guaranteed to be the one the constraint refuses.

    Args:
        session: A session on the same database, used only to ask the lock
            manager a question. It takes no lock on any table under test, so it
            never becomes part of the contention it is observing.
        pid: The backend process id to watch.
        timeout: How long to wait before giving up.

    Raises:
        AssertionError: If the backend never blocked. That means the race did
            not happen, so any result the test went on to assert would be
            meaningless.

    """
    # pg_blocking_pids reads the lock manager directly and returns the backends
    # standing in the given one's way. pg_stat_activity is deliberately not used:
    # its contents are snapshotted per transaction, so a polling loop would read
    # the same stale answer until it committed between every poll.
    statement = text("SELECT cardinality(pg_blocking_pids(:pid))")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        waiting = session.execute(statement, {"pid": pid}).scalar_one()
        if waiting:
            logger.debug("test.backend_is_blocked", extra={"pid": pid})
            return
        time.sleep(BLOCKED_POLL_SECONDS)
    raise AssertionError(
        f"Attempted to stage a race by waiting for backend {pid} to block on a lock, "
        f"and it never did within {timeout} seconds. The second writer therefore never "
        "contended with the first, so the outcome under test was never produced."
    )


__all__ = [
    "BARRIER_TIMEOUT_SECONDS",
    "CONTENDER_COUNT",
    "EXPECTED_WINNERS",
    "Contender",
    "Outcome",
    "backend_pid",
    "run_race",
    "wait_until_backend_is_blocked",
]
