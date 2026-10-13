"""Deleting the refresh sessions that expired long ago, which an operator's job does weekly (#90).

`refresh_session` gains a row at every sign in and every refresh, and a row
stays once it is rotated, revoked or out of time. A session whose expiry passed
more than ninety days ago can never be presented again, and the audit events of
every sign in, refresh and sign out stay, so nothing the log answers is lost
when it goes.

The application role holds no DELETE on the table, and nothing in the domain is
ever hard deleted (BR-51), so the delete is not the application's. The weekly
job connects as the operator role, which may delete, through a connection
string of its own, and calls this. It deletes a bounded batch at a time, oldest
expiry first, each batch in a transaction of its own, until a batch comes back
short. So no transaction holds more than one batch of locks however far behind
the pruning has fallen, and a failure part way keeps what was already done.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Final, Protocol

logger = logging.getLogger(__name__)

# How long a session is kept once its expiry has passed.
SESSION_KEPT_AFTER_EXPIRY: Final[timedelta] = timedelta(days=90)
# The most sessions one transaction deletes.
SESSION_PRUNE_BATCH_SIZE: Final[int] = 500


class ExpiredSessionStore(Protocol):
    """Where the expired refresh sessions are deleted, as the operator role."""

    def delete_expired_batch(self, cutoff: datetime, limit: int) -> int:
        """Delete at most `limit` sessions whose expiry passed before `cutoff`, and commit.

        Each call is a transaction of its own, oldest expiry first.

        Returns:
            How many sessions were deleted.

        """
        ...


def expired_session_cutoff(now: datetime) -> datetime:
    """Return the instant a session's expiry must have passed before for it to be deleted."""
    return now - SESSION_KEPT_AFTER_EXPIRY


def prune_expired_sessions(
    store: ExpiredSessionStore, now: datetime, batch_size: int = SESSION_PRUNE_BATCH_SIZE
) -> int:
    """Delete every session whose expiry passed more than ninety days ago, a batch at a time.

    Args:
        store: The sessions, on the operator's connection.
        now: The current instant, from the clock.
        batch_size: The most sessions one transaction deletes.

    Returns:
        How many sessions were deleted. The log line `sessions.pruned` says
        the same.

    Raises:
        ValueError: If the batch size is below one.

    """
    if batch_size < 1:
        raise ValueError(
            f"Attempted to prune refresh sessions in batches of {batch_size}. A batch is at "
            "least one session."
        )
    cutoff = expired_session_cutoff(now)
    logger.info(
        "sessions.pruning_started",
        extra={"expired_before": cutoff.isoformat(), "batch_size": batch_size},
    )
    total = 0
    batches = 0
    while True:
        deleted = store.delete_expired_batch(cutoff, batch_size)
        batches += 1
        total += deleted
        logger.info(
            "sessions.batch_pruned",
            extra={"batch_number": batches, "deleted_count": deleted, "total_deleted": total},
        )
        if deleted < batch_size:
            break
    logger.info(
        "sessions.pruned",
        extra={
            "deleted_count": total,
            "batch_count": batches,
            "expired_before": cutoff.isoformat(),
        },
    )
    return total
