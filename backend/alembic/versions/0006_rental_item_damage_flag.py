"""Give `rental_item` a column for the counter's damage flag.

When the counter takes a unit back it may flag it for a damage assessment,
whatever grade it came back in. A flagged unit goes to QUARANTINED, and its
assessment reads REQUIRED until a damage report names it (BR-35). The flag has
to outlive the return, because every later read of the rental asks it again,
and so does the settlement before it lets the deposit go (BR-32).

The design document lists the columns of `rental_item`, and none of them holds
this flag. Adding one is a deliberate departure from the document. The only
other place the schema offers is the notes, which are free text the counter
writes, and a fact the deposit depends on should not be read back out of free
text by matching its first words. A boolean says it plainly, can be filtered
on and leaves the notes holding only what the counter wrote.

`flagged_for_damage` is a BOOLEAN, NOT NULL, with a default of false. On
PostgreSQL 11 and later a column with a constant default is added without
rewriting the table, so the statement holds its lock for a moment and returns
at once however many rows there are. The release before this one never names
the column, so every row it inserts takes the default and it keeps working
against a migrated database. No release has stored the flag anywhere else, so
there is nothing to carry over into the new column.

No table and no sequence is created. A privilege granted on a table covers
every column it gains later, so the grants of revision 0002 already cover this
one and there is nothing to grant.

The downgrade drops the column, and with it every flag recorded since. A unit
that came back in the grade it went out in and was only flagged then reads as
needing no assessment.

Revision ID: 0006
Revises: 0005
Created: 2026-10-03
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.revision_0006")

TABLE: Final[str] = "rental_item"
COLUMN: Final[str] = "flagged_for_damage"


def upgrade() -> None:
    """Add the flag as a NOT NULL boolean that defaults to false."""
    op.add_column(
        TABLE,
        sa.Column(COLUMN, sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    logger.info("Added %s to %s, NOT NULL with a default of false", COLUMN, TABLE)


def downgrade() -> None:
    """Drop the column the upgrade added."""
    op.drop_column(TABLE, COLUMN)
    logger.info("Dropped %s from %s", COLUMN, TABLE)
