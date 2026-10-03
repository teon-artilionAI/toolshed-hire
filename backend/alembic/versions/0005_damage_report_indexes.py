"""Index what damage and quarantine read of `damage_report`.

The baseline gives `damage_report` its primary key and the unique reference
and nothing else, because nothing read it until damage and quarantine. Two
reads now need an index.

Every read of a rental, the one the counter opens and every page of the list,
asks whether a damage report names each of its units, because that is what
makes the damage assessment of a returned unit DONE (BR-35). The question is
a correlated EXISTS on `damage_report.rental_item_id` for every unit read.
`ix_damage_report_rental_item` is a btree on that column. It is partial,
because a report about damage found outside a hire names no unit of a hire and
is never asked about this way.

The reports of one unit are read by the list filtered by a tag, by the close
of a report, which counts the other reports of the unit still open, and by a
write off. `ix_damage_report_asset` is a btree on `damage_report.asset_id`.

Each index is built inside the migration's transaction, which blocks writes to
`damage_report` while it builds. The table is empty when this first runs, so
that takes no time at all.

No table, no column and no sequence is created, so there is nothing to grant.

Revision ID: 0005
Revises: 0004
Created: 2026-10-03
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.revision_0005")

RENTAL_ITEM_INDEX: Final[str] = "ix_damage_report_rental_item"
ASSET_INDEX: Final[str] = "ix_damage_report_asset"
TABLE: Final[str] = "damage_report"


def upgrade() -> None:
    """Create the partial btree on the rental item and the btree on the unit."""
    op.create_index(
        RENTAL_ITEM_INDEX,
        TABLE,
        ["rental_item_id"],
        postgresql_where=sa.text("rental_item_id IS NOT NULL"),
    )
    op.create_index(ASSET_INDEX, TABLE, ["asset_id"])
    logger.info("Created %s and %s on %s", RENTAL_ITEM_INDEX, ASSET_INDEX, TABLE)


def downgrade() -> None:
    """Drop the two indexes the upgrade created."""
    op.drop_index(ASSET_INDEX, table_name=TABLE)
    op.drop_index(RENTAL_ITEM_INDEX, table_name=TABLE)
    logger.info("Dropped %s and %s", ASSET_INDEX, RENTAL_ITEM_INDEX)
