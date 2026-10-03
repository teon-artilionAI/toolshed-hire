"""Index what the counter's asset locator and branch diary read.

Three reads arrive with the counter overview, and the baseline has an index
for each of them except these.

The asset locator finds a unit at any branch by part of its tag or of its
model name (FR-15). The tag has a unique btree, which only finds a tag typed in
full, and the counter types `0042` or `DR-00`. `ix_asset_tag_trgm` is a trigram
index on the tag, which serves `ILIKE '%text%'`. The model name is matched on
`product_model`, which holds a few hundred rows, and the units of the models
found are then reached by their model. `asset.product_model_id` has only the
partial index of available units, and a unit on hire or in quarantine is
exactly the one the counter is looking for, so `ix_asset_product_model` is a
plain btree on it.

The branch diary lists the hires due back at a branch on any day (FR-16). The
baseline's `ix_rental_open_due_back` holds only hires with a unit still out,
which serves the dashboard and never a day in the past, when most hires are
back. `ix_rental_branch_due_back` is a btree on the branch and the day.

Each index is built inside the migration's transaction, which blocks writes to
its table while it builds. That takes moments on the four hundred units and
the hires of a first year. A table a hundred times larger would want
`CREATE INDEX CONCURRENTLY` outside a transaction instead.

No table, no column and no sequence is created, so there is nothing to grant.

Revision ID: 0004
Revises: 0003
Created: 2026-10-03
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Final

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.revision_0004")

ASSET_TAG_INDEX: Final[str] = "ix_asset_tag_trgm"
ASSET_MODEL_INDEX: Final[str] = "ix_asset_product_model"
RENTAL_DIARY_INDEX: Final[str] = "ix_rental_branch_due_back"


def upgrade() -> None:
    """Create the trigram index on the tag and the two btrees."""
    op.execute(f"CREATE INDEX {ASSET_TAG_INDEX} ON asset USING gin (asset_tag gin_trgm_ops)")
    op.create_index(ASSET_MODEL_INDEX, "asset", ["product_model_id"])
    op.create_index(RENTAL_DIARY_INDEX, "rental", ["branch_id", "due_back_on"])
    logger.info(
        "Created %s, %s and %s", ASSET_TAG_INDEX, ASSET_MODEL_INDEX, RENTAL_DIARY_INDEX
    )


def downgrade() -> None:
    """Drop the three indexes the upgrade created."""
    op.drop_index(RENTAL_DIARY_INDEX, table_name="rental")
    op.drop_index(ASSET_MODEL_INDEX, table_name="asset")
    op.execute(f"DROP INDEX IF EXISTS {ASSET_TAG_INDEX}")
    logger.info(
        "Dropped %s, %s and %s", RENTAL_DIARY_INDEX, ASSET_MODEL_INDEX, ASSET_TAG_INDEX
    )
