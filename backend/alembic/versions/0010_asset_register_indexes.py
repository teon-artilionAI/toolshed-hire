"""Index what the asset register searches and what a unit's history reads.

The administrator's register of the fleet arrives with two reads the existing
indexes do not serve (FR-23, SC-21).

1. `ix_asset_serial_trgm`, a trigram index on `asset.serial_number`. The
   register is searched by part of the tag, the serial number or the model
   name. The tag has the trigram index of revision 0004 and the model name is
   matched on the small `product_model` table, but the serial number had no
   index at all, so a search would read every unit. A trigram index serves
   `ILIKE '%text%'` the way the one on the tag does. A unit with no serial
   number has nothing to index, which the index does not mind.
2. `ix_asset_allocation_released`, a btree on `asset_allocation (asset_id,
   released_at)`, partial on a released allocation. The history of a unit
   lists every booking that ever held it. The GiST index of the exclusion
   constraint leads with the unit and holds the active allocations, so it
   already finds those, and this index holds the released ones, in the order
   they were let go. Nothing else on the table leads with the unit, and the
   allocations are the table that grows with every booking, so without it the
   history of one unit would read all of them.

The second index is partial on purpose. A plain index on the unit would be
offered to every statement that asks about the allocations of a unit, the
availability search among them, and on a small table the planner can prefer
it to the GiST index the search is written for. An index that holds released
allocations only can never answer a question about active ones, so the
search keeps the index the exclusion constraint gives it.

Both indexes are additive and change no row. Each is built inside the
migration's transaction, which blocks writes to its table while it builds. On
four hundred units and the allocations of a first year that is a moment. A
table a hundred times larger would want `CREATE INDEX CONCURRENTLY` outside a
transaction instead. Every write of a unit and every release of an allocation
keeps one more index up to date, which is the price of a register that can be
searched and a history that is read through an index.

No table, no column and no sequence is created, so there is nothing to grant.

Revision ID: 0010
Revises: 0009
Created: 2026-10-04
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.revision_0010")

ASSET_SERIAL_INDEX: Final[str] = "ix_asset_serial_trgm"
ALLOCATION_RELEASED_INDEX: Final[str] = "ix_asset_allocation_released"
RELEASED_PREDICATE: Final[str] = "released_at IS NOT NULL"


def upgrade() -> None:
    """Create the trigram index on the serial number and the btree on released allocations."""
    op.execute(
        f"CREATE INDEX {ASSET_SERIAL_INDEX} ON asset USING gin (serial_number gin_trgm_ops)"
    )
    op.create_index(
        ALLOCATION_RELEASED_INDEX,
        "asset_allocation",
        ["asset_id", "released_at"],
        postgresql_where=sa.text(RELEASED_PREDICATE),
    )
    logger.info("Created %s and %s", ASSET_SERIAL_INDEX, ALLOCATION_RELEASED_INDEX)


def downgrade() -> None:
    """Drop the two indexes the upgrade created."""
    op.drop_index(ALLOCATION_RELEASED_INDEX, table_name="asset_allocation")
    op.execute(f"DROP INDEX IF EXISTS {ASSET_SERIAL_INDEX}")
    logger.info("Dropped %s and %s", ALLOCATION_RELEASED_INDEX, ASSET_SERIAL_INDEX)
