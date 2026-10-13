"""The weekly job that deletes the refresh sessions that expired more than ninety days ago (#90).

    python -m app.jobs.prune_refresh_sessions

It connects with OPERATOR_DATABASE_URL, the operator role that may delete from
`refresh_session`, and never with DATABASE_URL, whose role may not. It deletes
five hundred sessions a transaction, oldest expiry first, until a batch comes
back short, and logs the count of each batch and of the run.

It reads no other setting, so it needs neither the signing key nor the
application's own connection string where it runs.
"""

from __future__ import annotations

import os
import sys
from typing import Final

from app.application.identity.session_pruning import (
    SESSION_PRUNE_BATCH_SIZE,
    prune_expired_sessions,
)
from app.infrastructure.clock import SystemClock
from app.infrastructure.session_pruning import (
    OPERATOR_URL_VARIABLE,
    SqlExpiredSessionStore,
    operator_engine,
)
from app.jobs.job_run import JobFacts, run_job
from app.logging_config import configure_logging

JOB_NAME: Final[str] = "prune-refresh-sessions"


def main() -> int:
    """Prune the expired sessions on the operator's connection, and return the exit status."""

    def work() -> JobFacts:
        engine = operator_engine(os.environ.get(OPERATOR_URL_VARIABLE, ""))
        try:
            deleted = prune_expired_sessions(
                SqlExpiredSessionStore(engine), SystemClock().now(), SESSION_PRUNE_BATCH_SIZE
            )
        finally:
            engine.dispose()
        return {"deleted_count": deleted, "batch_size": SESSION_PRUNE_BATCH_SIZE}

    configure_logging()
    return run_job(JOB_NAME, work)


if __name__ == "__main__":
    sys.exit(main())
