"""Index the digits of a customer's phone number, for the counter's lookup.

The counter finds a customer by part of a name, by a phone number or by the
email address of an account (US-21). The baseline gives the name a trigram
index and the email a unique one, and it gives the phone a plain btree, which
only finds a number typed exactly as it was stored. A number is stored the
way the customer typed it, for example `082 441 7719`, and the counter types
it however the customer reads it out, so the btree finds almost nothing.

This revision adds a trigram index over the digits of the number, with the
spaces, hyphens, brackets and plus sign the phone rule allows taken out. A
search for `0824417719`, `082 441` or `7719` then stands on an index whatever
punctuation either side used. The expression is written with `replace` and not
with a regular expression, so the in memory database of the fast tests can
run the same statement. The search in
`app/infrastructure/customer_search.py` writes the same expression, character
for character, and an integration test asks the planner to prove it uses the
index.

The index is built in the migration's transaction, which blocks writes to
`customer_profile` while it builds. That takes moments on the tens of
thousands of profiles this business will hold. A table a hundred times larger
would want `CREATE INDEX CONCURRENTLY` outside a transaction instead.

No table and no sequence is created, so there is nothing to grant.

Revision ID: 0003
Revises: 0002
Created: 2026-10-03
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Final

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.revision_0003")

INDEX_NAME: Final[str] = "ix_customer_profile_phone_digits_trgm"
# The digits of the contact phone. The punctuation is removed in this order,
# innermost first, and the search repeats the order exactly.
PHONE_DIGITS: Final[str] = (
    "replace(replace(replace(replace(replace(contact_phone, ' ', ''), '-', ''), "
    "'(', ''), ')', ''), '+', '')"
)


def upgrade() -> None:
    """Create the trigram index over the digits of the contact phone."""
    op.execute(
        f"CREATE INDEX {INDEX_NAME} ON customer_profile USING gin (({PHONE_DIGITS}) gin_trgm_ops)"
    )
    logger.info("Created %s on customer_profile", INDEX_NAME)


def downgrade() -> None:
    """Drop the index the upgrade created."""
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
    logger.info("Dropped %s", INDEX_NAME)
