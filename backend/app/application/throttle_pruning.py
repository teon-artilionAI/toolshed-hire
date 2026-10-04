"""Deleting the throttle counters whose window ended long ago (C-17).

`rate_limit_counter` gains a row for every bucket in every window, so it grows
with every attempt that is counted. A counter is no use once its window has
ended, and a day after that it is deleted. The lazy sweep asks for it as its
fourth part, a bounded batch in one statement a call, oldest window first, so
no request ever pays for an unbounded delete and the table holds about a day
of counters.

A counter does not record the length of its window, only its start. No window
is longer than `LONGEST_THROTTLE_WINDOW`, so a counter whose window began that
long and a day before now has a window that ended more than a day ago,
whatever rule it belongs to. A live counter is therefore never deleted.

The delete is the only one the application role is allowed, and this table is
the only one it is allowed on. `refresh_session` is not pruned, because
nothing in the domain is ever hard deleted (BR-51), and the README says what
an operator job would do about it.

This belongs to no module, like the throttle it tidies after.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Final

from app.application.throttle import LONGEST_THROTTLE_WINDOW, RateLimitStore

logger = logging.getLogger(__name__)

# How long a counter is kept once its window has ended. It is longer than the
# longest window, so the last day of throttling can still be read after an
# incident, and no counter is ever deleted while its window still runs.
COUNTER_KEPT_AFTER_WINDOW: Final[timedelta] = timedelta(days=1)
# The most counters one sweep deletes, in its one statement. A request pays for
# no more than this however far behind the pruning has fallen.
COUNTER_PRUNE_BATCH_SIZE: Final[int] = 500


def finished_window_cutoff(now: datetime) -> datetime:
    """Return the instant a counter's window must have begun before for it to be pruned.

    No window is longer than `LONGEST_THROTTLE_WINDOW`, so a window that began
    before this instant ended more than `COUNTER_KEPT_AFTER_WINDOW` before
    `now`, whatever rule it belongs to.
    """
    return now - LONGEST_THROTTLE_WINDOW - COUNTER_KEPT_AFTER_WINDOW


def prune_finished_windows(store: RateLimitStore, now: datetime, limit: int) -> int:
    """Delete at most `limit` counters whose window ended more than a day ago, oldest first.

    Args:
        store: The counters, inside the transaction of the caller, who commits.
        now: The current instant, from the clock.
        limit: The most counters to delete in this one statement.

    Returns:
        How many counters were deleted. The log line `throttle.counters_pruned`
        says the same.

    Raises:
        ValueError: If the limit is below one.

    """
    if limit < 1:
        raise ValueError(
            f"Attempted to prune throttle counters with a batch of {limit}. A batch is at "
            "least one counter."
        )
    cutoff = finished_window_cutoff(now)
    deleted = store.delete_windows_before(cutoff, limit)
    log = logger.info if deleted else logger.debug
    log(
        "throttle.counters_pruned",
        extra={
            "deleted_count": deleted,
            "batch_size": limit,
            "window_started_before": cutoff.isoformat(),
        },
    )
    return deleted
