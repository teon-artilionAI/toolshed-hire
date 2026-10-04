"""Index the staff accounts and the customers by standing, for the administrator's lists of people.

User and role management (FR-25, US-35, SC-23) brings three reads the existing
indexes do not serve.

1. `ix_user_account_staff`, a btree on `user_account (lower(full_name), id)`,
   partial on every account that is not a customer's. The list of staff, and
   the lock every change to a staff account takes on the active
   administrators, read the staff accounts only. `user_account` holds a row
   for every customer who registered as well, so without it both would read
   every account the business has to find the few dozen people who work
   there.
2. `ix_customer_profile_name`, a btree on `customer_profile
   (lower(display_name), id)`. The administrator's list of customers is in
   name order, case blind. The trigram index of the baseline finds part of a
   name but cannot give an order, so a page with no standing named, or of the
   customers in good standing, would sort every profile to find twenty.
3. `ix_customer_profile_standing`, a btree on `customer_profile
   (lower(display_name), id)`, partial on a standing that is not ACTIVE. The
   holds and the blacklisting are what the screen is for, and they are a
   handful of customers among thousands, so their count and their page are
   read from an index that holds them and nobody else.

The names are indexed through `lower` on purpose, beyond giving an order that
ignores capitals. An index on the bare column holds every name, so the planner
can answer a search for part of a name by reading the whole of it instead of
the trigram index, and on a small table it does. The counter's search would
then stop standing on the trigram index it was written for, which
`tests/integration/test_customer_search_index.py` caught. An index on
`lower(display_name)` cannot answer a condition on `display_name`, so the
search keeps its index and the list gets its order.

The predicates are written the way the statements write them, as literals,
`role <> 'CUSTOMER'` and `account_status <> 'ACTIVE'`, so the planner can
match them whatever plan the server caches.

Every index is additive and changes no row. Each is built inside the
migration's transaction, which blocks writes to its table while it builds.
`user_account` and `customer_profile` hold a row for each customer, a few
thousand in a first year, so that is a moment. A table a hundred times larger
would want `CREATE INDEX CONCURRENTLY` outside a transaction instead. A
registration and an edit of a profile keep up to two more indexes up to date,
and both happen a few times a day.

No table, no column and no sequence is created, so there is nothing to grant.

Revision ID: 0011
Revises: 0010
Created: 2026-10-04
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.revision_0011")

STAFF_ACCOUNT_INDEX: Final[str] = "ix_user_account_staff"
CUSTOMER_NAME_INDEX: Final[str] = "ix_customer_profile_name"
CUSTOMER_STANDING_INDEX: Final[str] = "ix_customer_profile_standing"
STAFF_PREDICATE: Final[str] = "role <> 'CUSTOMER'"
OUT_OF_GOOD_STANDING_PREDICATE: Final[str] = "account_status <> 'ACTIVE'"
STAFF_NAME: Final[str] = "lower(full_name)"
CUSTOMER_NAME: Final[str] = "lower(display_name)"


def upgrade() -> None:
    """Create the three indexes the lists of staff and of customers are read through."""
    op.create_index(
        STAFF_ACCOUNT_INDEX,
        "user_account",
        [sa.text(STAFF_NAME), "id"],
        postgresql_where=sa.text(STAFF_PREDICATE),
    )
    op.create_index(CUSTOMER_NAME_INDEX, "customer_profile", [sa.text(CUSTOMER_NAME), "id"])
    op.create_index(
        CUSTOMER_STANDING_INDEX,
        "customer_profile",
        [sa.text(CUSTOMER_NAME), "id"],
        postgresql_where=sa.text(OUT_OF_GOOD_STANDING_PREDICATE),
    )
    logger.info(
        "Created %s, %s and %s", STAFF_ACCOUNT_INDEX, CUSTOMER_NAME_INDEX, CUSTOMER_STANDING_INDEX
    )


def downgrade() -> None:
    """Drop the three indexes the upgrade created."""
    op.drop_index(CUSTOMER_STANDING_INDEX, table_name="customer_profile")
    op.drop_index(CUSTOMER_NAME_INDEX, table_name="customer_profile")
    op.drop_index(STAFF_ACCOUNT_INDEX, table_name="user_account")
    logger.info(
        "Dropped %s, %s and %s", CUSTOMER_STANDING_INDEX, CUSTOMER_NAME_INDEX, STAFF_ACCOUNT_INDEX
    )
