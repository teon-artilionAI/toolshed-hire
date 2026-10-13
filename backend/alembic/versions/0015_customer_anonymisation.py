"""Record when a customer was anonymised, and index the two maintenance jobs (#113, #90).

1. `customer_profile.anonymised_at`, a nullable TIMESTAMPTZ. An anonymised
   profile keeps its row, because its hires, charges and deposits are
   financial records kept for five years, so the row itself has to say that it
   no longer names anybody. The owner's request refuses a customer who was
   anonymised already by reading it, and the monthly job leaves such a profile
   out. Telling one apart by the words written over the name would refuse a
   real customer who happened to be registered as "Former customer".
2. `ix_customer_profile_identified`, a btree on `customer_profile (id)`,
   partial on `anonymised_at IS NULL`. The job reads the customers who
   qualify a page at a time in the order of their key. Every customer
   anonymised stays in the table for good, so without the predicate each run
   would walk past all of them again, and the walk would grow every month.
3. `ix_refresh_session_expires_at`, a btree on `refresh_session (expires_at)`.
   The weekly pruning deletes a batch at a time of the sessions that expired
   more than ninety days ago, oldest first. Without it every batch reads the
   whole table, which gains a row at every sign in and every refresh, to find
   five hundred rows. A session's expiry is written once and never changed, so
   the index costs one entry for each new session and nothing on a rotation.

The predicate is written as the statement writes it, so the planner can match
it whatever plan the server caches.

The column is nullable with no default, so adding it rewrites no row. The two
indexes are built inside the migration's transaction, which blocks writes to
their tables while they build. Both tables hold a row a customer or a few
rows a customer, which is a moment today. A table a hundred times larger would
want `CREATE INDEX CONCURRENTLY` outside a transaction instead.

A column added to a table is covered by the privileges already granted on the
table, so there is nothing to grant.

Revision ID: 0015
Revises: 0014
Created: 2026-10-13
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.revision_0015")

PROFILE_TABLE: Final[str] = "customer_profile"
SESSION_TABLE: Final[str] = "refresh_session"
ANONYMISED_COLUMN: Final[str] = "anonymised_at"
IDENTIFIED_INDEX: Final[str] = "ix_customer_profile_identified"
IDENTIFIED_PREDICATE: Final[str] = "anonymised_at IS NULL"
SESSION_EXPIRY_INDEX: Final[str] = "ix_refresh_session_expires_at"


def upgrade() -> None:
    """Add the column and create the two indexes."""
    op.add_column(
        PROFILE_TABLE,
        sa.Column(ANONYMISED_COLUMN, sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        IDENTIFIED_INDEX,
        PROFILE_TABLE,
        ["id"],
        postgresql_where=sa.text(IDENTIFIED_PREDICATE),
    )
    op.create_index(SESSION_EXPIRY_INDEX, SESSION_TABLE, ["expires_at"])
    logger.info(
        "Added %s.%s and created %s and %s",
        PROFILE_TABLE,
        ANONYMISED_COLUMN,
        IDENTIFIED_INDEX,
        SESSION_EXPIRY_INDEX,
    )


def downgrade() -> None:
    """Drop the two indexes and the column, and with it the record of who was anonymised."""
    op.drop_index(SESSION_EXPIRY_INDEX, table_name=SESSION_TABLE)
    op.drop_index(IDENTIFIED_INDEX, table_name=PROFILE_TABLE)
    op.drop_column(PROFILE_TABLE, ANONYMISED_COLUMN)
    logger.info(
        "Dropped %s, %s and %s.%s",
        SESSION_EXPIRY_INDEX,
        IDENTIFIED_INDEX,
        PROFILE_TABLE,
        ANONYMISED_COLUMN,
    )
