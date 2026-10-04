"""Index what the utilisation report reads for a period.

The report reads, for any period of up to a year, the charges raised in it,
the hires and the damage reports open at any moment of it, the losses recorded
before its end and the recorded changes of status of every unit around it.
Without these the first four would each read their table from end to end, and
those are the tables that grow with every hire.

1. `ix_charge_raised_at`, a btree on `charge.raised_at`. A charge counts in
   the period its business day of `raised_at` falls in, so the money of a
   period is a range of this column.
2. `ix_rental_item_returned_at`, a btree on `rental_item.returned_at`. A hire
   touches a period when it is still out or came back after the period began,
   and both halves are found here, the first as the null entries.
3. `ix_rental_item_lost`, a btree on `rental_item.returned_at`, partial on a
   rental item closed with no condition, which is how a lost unit is recorded.
   A loss keeps a unit out of service until its status next changes, so every
   loss before the end of a period is read, and this index holds the few there
   are and nothing else.
4. `ix_damage_report_resolved_at`, a btree on `damage_report.resolved_at`,
   which finds the reports open during a period the way the second finds the
   hires, and the reports resolved within it, whose repair costs are counted.
5. `ix_audit_event_asset_status`, a btree on `audit_event (entity_id,
   occurred_at)`, partial on the action `asset.status_changed`. The report
   asks, for each unit, for the last change of its status before the period
   and the first after it, and each is one entry of this index. It holds only
   those events, so it stays a small part of the largest table.

Every index is additive and changes no row. Each is built inside the
migration's transaction, which blocks writes to its table while it builds, and
writes to `audit_event` happen in every transaction that changes anything. On
the tables of a first year that takes moments. A table a hundred times larger
would want `CREATE INDEX CONCURRENTLY` outside a transaction instead.

No table, no column and no sequence is created, so there is nothing to grant.

Revision ID: 0007
Revises: 0006
Created: 2026-10-04
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.revision_0007")

CHARGE_RAISED_INDEX: Final[str] = "ix_charge_raised_at"
RENTAL_ITEM_RETURNED_INDEX: Final[str] = "ix_rental_item_returned_at"
RENTAL_ITEM_LOST_INDEX: Final[str] = "ix_rental_item_lost"
DAMAGE_REPORT_RESOLVED_INDEX: Final[str] = "ix_damage_report_resolved_at"
AUDIT_STATUS_INDEX: Final[str] = "ix_audit_event_asset_status"
LOST_ITEM_PREDICATE: Final[str] = "returned_at IS NOT NULL AND condition_in IS NULL"
STATUS_CHANGE_PREDICATE: Final[str] = "action = 'asset.status_changed'"


def upgrade() -> None:
    """Create the five indexes the report reads through."""
    op.create_index(CHARGE_RAISED_INDEX, "charge", ["raised_at"])
    op.create_index(RENTAL_ITEM_RETURNED_INDEX, "rental_item", ["returned_at"])
    op.create_index(
        RENTAL_ITEM_LOST_INDEX,
        "rental_item",
        ["returned_at"],
        postgresql_where=sa.text(LOST_ITEM_PREDICATE),
    )
    op.create_index(DAMAGE_REPORT_RESOLVED_INDEX, "damage_report", ["resolved_at"])
    op.create_index(
        AUDIT_STATUS_INDEX,
        "audit_event",
        ["entity_id", "occurred_at"],
        postgresql_where=sa.text(STATUS_CHANGE_PREDICATE),
    )
    logger.info(
        "Created %s, %s, %s, %s and %s",
        CHARGE_RAISED_INDEX,
        RENTAL_ITEM_RETURNED_INDEX,
        RENTAL_ITEM_LOST_INDEX,
        DAMAGE_REPORT_RESOLVED_INDEX,
        AUDIT_STATUS_INDEX,
    )


def downgrade() -> None:
    """Drop the five indexes the upgrade created."""
    op.drop_index(AUDIT_STATUS_INDEX, table_name="audit_event")
    op.drop_index(DAMAGE_REPORT_RESOLVED_INDEX, table_name="damage_report")
    op.drop_index(RENTAL_ITEM_LOST_INDEX, table_name="rental_item")
    op.drop_index(RENTAL_ITEM_RETURNED_INDEX, table_name="rental_item")
    op.drop_index(CHARGE_RAISED_INDEX, table_name="charge")
    logger.info("Dropped the five indexes of revision 0007")
