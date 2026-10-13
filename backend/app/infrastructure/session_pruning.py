"""The SQL side of pruning expired refresh sessions, on the operator's connection (#90).

The weekly job connects as the operator role, which may delete from
`refresh_session`, and never as the application role, which may not. The
connection string is its own setting, `OPERATOR_DATABASE_URL`, so the web
process never holds a credential that can delete a session.

Each batch is one DELETE in a transaction of its own. Its rows are picked by a
subquery in the order of `ix_refresh_session_expires_at`, revision 0015, so the
planner reads that index from its start and stops at the batch or at the
cutoff, whichever comes first, and a batch costs what it deletes and not the
size of the table. A session another transaction holds is skipped, not waited
for.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Final

from sqlalchemy import CursorResult, Delete, Engine, create_engine, delete, select
from sqlalchemy.pool import NullPool
from sqlmodel import col

from app.config_checks import force_psycopg_driver
from app.infrastructure.models import RefreshSession

logger = logging.getLogger(__name__)

OPERATOR_URL_VARIABLE: Final[str] = "OPERATOR_DATABASE_URL"
APPLICATION_NAME: Final[str] = "toolshed-hire-session-pruning"


def expired_sessions_statement(cutoff: datetime, limit: int) -> Delete:
    """Return the one statement that deletes at most `limit` sessions expired before `cutoff`."""
    due = (
        select(col(RefreshSession.id))
        .where(col(RefreshSession.expires_at) < cutoff)
        .order_by(col(RefreshSession.expires_at))
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return delete(RefreshSession).where(col(RefreshSession.id).in_(due))


def operator_engine(operator_url: str) -> Engine:
    """Return an engine on the operator's connection string, with no pool to keep open.

    The job runs a few statements and exits, so a connection is opened for each
    batch and closed with it.

    Raises:
        ValueError: If the value is blank or not a PostgreSQL connection
            string. The message names the variable and never the value, which
            holds a password.

    """
    if not operator_url.strip():
        raise ValueError(
            f"{OPERATOR_URL_VARIABLE} is not set. The session pruning connects as the operator "
            "role, which may delete refresh sessions, and never as the application role."
        )
    try:
        url = force_psycopg_driver(operator_url)
    except ValueError:
        # The driver's message names DATABASE_URL, which is not the variable
        # this job reads. The value itself is never repeated.
        raise ValueError(
            f"{OPERATOR_URL_VARIABLE} must be a PostgreSQL connection string starting with "
            "postgresql+psycopg://, postgresql:// or postgres://."
        ) from None
    return create_engine(
        url,
        poolclass=NullPool,
        echo=False,
        connect_args={"application_name": APPLICATION_NAME},
    )


class SqlExpiredSessionStore:
    """Deletes expired refresh sessions a batch at a time, each batch committed."""

    def __init__(self, engine: Engine) -> None:
        """Bind the store to the operator's engine."""
        self._engine = engine

    def delete_expired_batch(self, cutoff: datetime, limit: int) -> int:
        """Delete at most `limit` sessions whose expiry passed before `cutoff`, and commit."""
        logger.debug(
            "sessions.batch_delete_started",
            extra={"expired_before": cutoff.isoformat(), "limit": limit},
        )
        with self._engine.begin() as connection:
            result = connection.execute(expired_sessions_statement(cutoff, limit))
            deleted_count = result.rowcount if isinstance(result, CursorResult) else 0
        logger.debug("sessions.batch_deleted", extra={"deleted_count": deleted_count})
        return deleted_count
