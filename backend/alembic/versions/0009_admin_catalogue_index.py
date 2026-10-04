"""Index the product models of a category, published or not, for the admin catalogue.

The administrator lists every product model, published or not, narrowed by
category and ordered by name, and the list of categories counts the models of
each. The baseline indexes `product_model` on `(category_id, name)` for the
published models only, `ix_product_model_published`, because a visitor never
sees any other. Nothing served the category of a model that is not published,
and the foreign key on `category_id` has no index of its own, because
PostgreSQL never makes one for a foreign key.

1. `ix_product_model_category`, a btree on `product_model (category_id,
   name)` with no predicate, for the models of one category in the order the
   list shows them, and for the count of the models of each category, which
   is one probe of it a category.

The units of a model are counted through `ix_asset_product_model` of revision
0004, and a code, a SKU and a slug are found through the unique indexes of the
baseline, so nothing else is needed.

The index is additive and changes no row. It is built inside the migration's
transaction, which blocks writes to `product_model` while it builds. The table
holds the catalogue, 120 rows that change by hand, so that is a moment. A
table a hundred times larger would want `CREATE INDEX CONCURRENTLY` outside a
transaction instead. Every write to a model keeps one more index up to date,
and models are written a few times a month.

No table, no column and no sequence is created, so there is nothing to grant.

Revision ID: 0009
Revises: 0008
Created: 2026-10-04
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Final

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.revision_0009")

PRODUCT_MODEL_CATEGORY_INDEX: Final[str] = "ix_product_model_category"


def upgrade() -> None:
    """Create the index the admin catalogue finds the models of a category through."""
    op.create_index(PRODUCT_MODEL_CATEGORY_INDEX, "product_model", ["category_id", "name"])
    logger.info("Created %s", PRODUCT_MODEL_CATEGORY_INDEX)


def downgrade() -> None:
    """Drop the index the upgrade created."""
    op.drop_index(PRODUCT_MODEL_CATEGORY_INDEX, table_name="product_model")
    logger.info("Dropped %s", PRODUCT_MODEL_CATEGORY_INDEX)
