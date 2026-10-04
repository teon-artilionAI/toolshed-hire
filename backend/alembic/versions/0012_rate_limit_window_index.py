"""Index the throttle counters by when their window began, so old ones can be pruned cheaply.

The lazy sweep deletes the counters of `rate_limit_counter` whose window ended
more than a day ago, at most a bounded batch in one statement a call, oldest
first. The sweep runs before many reads, an availability search among them,
so the statement has to cost almost nothing when nothing is due.

1. `ix_rate_limit_counter_window_started_at`, a btree on
   `rate_limit_counter (window_started_at)`. The statement reads it from its
   start up to the cutoff and stops at the end of the batch, so when nothing is
   due it reads one entry. The unique key of the baseline on
   `(bucket_key_hash, window_started_at)` leads with the bucket, so it cannot
   find the old windows of every bucket at once, and without this index the
   statement would read the whole table on every call. The table holds about a
   day of counters when the sweep keeps up, and far more after a burst of
   attempts, which is exactly when the sweep has to stay cheap.

The index is additive and changes no row. It is built inside the migration's
transaction, which blocks writes to `rate_limit_counter`, and so the throttle,
while it builds, and on a day of counters that is a moment. A counter is
inserted once for its window and afterwards only has its count raised, which
never touches the indexed column, so the index costs each attempt very little.

No table, no column and no sequence is created, so there is nothing to grant.
The application role already holds DELETE on this one table.

Revision ID: 0012
Revises: 0011
Created: 2026-10-04
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Final

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.revision_0012")

RATE_LIMIT_WINDOW_INDEX: Final[str] = "ix_rate_limit_counter_window_started_at"


def upgrade() -> None:
    """Create the index the sweep finds the old throttle counters through."""
    op.create_index(RATE_LIMIT_WINDOW_INDEX, "rate_limit_counter", ["window_started_at"])
    logger.info("Created %s", RATE_LIMIT_WINDOW_INDEX)


def downgrade() -> None:
    """Drop the index the upgrade created."""
    op.drop_index(RATE_LIMIT_WINDOW_INDEX, table_name="rate_limit_counter")
    logger.info("Dropped %s", RATE_LIMIT_WINDOW_INDEX)
