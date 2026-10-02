"""The SQL store behind the throttle, which is `rate_limit_counter` (C-17).

A counter is one row for one bucket and one window. Counting an attempt is a
single statement that inserts the row at one or, when the row is already
there, adds one to it and returns the new count. The database does the adding
under its own row lock, so two attempts at once are both counted and neither
reads a count the other is about to change.

The statement is written out as text because it is the same in PostgreSQL and
in the SQLite the fast tests run on, and the two insert constructs SQLAlchemy
offers for it are not. Nothing is placed in the text. The three values are
bound.

Deleting old windows is the one delete the application role is allowed, and
this table is the only one it is allowed on.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Final

from sqlalchemy import CursorResult, DateTime, String, bindparam, delete, text
from sqlmodel import Session, col

from app.infrastructure.models import RateLimitCounter

logger = logging.getLogger(__name__)

FIRST_ATTEMPT: Final[int] = 1

_COUNT_ATTEMPT = text(
    "INSERT INTO rate_limit_counter (bucket_key_hash, window_started_at, request_count) "
    "VALUES (:bucket_key_hash, :window_started_at, :first_attempt) "
    "ON CONFLICT (bucket_key_hash, window_started_at) "
    "DO UPDATE SET request_count = rate_limit_counter.request_count + 1 "
    "RETURNING request_count"
).bindparams(
    bindparam("bucket_key_hash", type_=String()),
    bindparam("window_started_at", type_=DateTime(timezone=True)),
)


class SqlRateLimitStore:
    """Counts attempts in `rate_limit_counter` through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the store to the session of its unit of work."""
        self._session = session

    def increment(self, bucket_key_hash: str, window_started_at: datetime) -> int:
        """Add one to the counter of a bucket and a window, and return the new count."""
        count = self._session.execute(
            _COUNT_ATTEMPT,
            {
                "bucket_key_hash": bucket_key_hash,
                "window_started_at": window_started_at,
                "first_attempt": FIRST_ATTEMPT,
            },
        ).scalar_one()
        logger.debug("rate_limit.attempt_counted", extra={"request_count": int(count)})
        return int(count)

    def delete_windows_before(self, cutoff: datetime) -> int:
        """Delete every counter whose window began before `cutoff`, and return how many."""
        statement = delete(RateLimitCounter).where(
            col(RateLimitCounter.window_started_at) < cutoff
        )
        result = self._session.execute(statement)
        deleted_count = result.rowcount if isinstance(result, CursorResult) else 0
        logger.debug(
            "rate_limit.windows_deleted",
            extra={"deleted_count": deleted_count, "cutoff": cutoff.isoformat()},
        )
        return deleted_count
