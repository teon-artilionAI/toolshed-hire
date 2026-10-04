"""Index what the audit log and the notification log are read by.

An administrator reads the audit log newest first, narrowed by the kind and
the key of a record, the action, the account that acted and a span of days,
and reads the notification log newest first, narrowed by status. The baseline
indexes `audit_event` on `(entity_type, entity_id)` and on `occurred_at`, and
`notification` on `queued_at` for the failed sends only. Three filters of the
audit log and the unfiltered notification log plainly had no index, and
`audit_event` is the table that grows fastest, so each would have read it from
end to end.

1. `ix_audit_event_entity_id`, a btree on `audit_event (entity_id,
   occurred_at)`, for the history of one record named by its key alone. The
   baseline index leads with the kind of record, so it cannot be searched by
   the key without it.
2. `ix_audit_event_action`, a btree on `audit_event (action, occurred_at)`,
   partial on every action but `asset.status_changed`, for every event of one
   action, for example every waiver.
3. `ix_audit_event_actor`, a btree on `audit_event (actor_user_id,
   occurred_at)`, partial on an event that has an actor, for everything one
   account did. The events of the sweep have none and are left out of it.
4. `ix_notification_queued_at`, a btree on `notification.queued_at`, for the
   log of every notification, and of the sent and the queued ones.

Each index on `audit_event` ends in `occurred_at`, so the newest page of a
filter is read off the end of its index. The index of an action leaves out
the changes of status of the units on purpose. The utilisation report asks,
for every unit, for its last change of status before a period through
`ix_audit_event_asset_status` of revision 0007, and an index that led with the
action and held those changes in time order would answer the same question
by reading every change of status of the fleet backwards, which the planner
takes on a small table. Left out, it cannot be used for that question at all.
The log of that one action is read through `ix_audit_event_occurred_at`
instead, where its events are common enough that a page is found quickly.

Every index is additive and changes no row. Each is built inside the
migration's transaction, which blocks writes to its table while it builds, and
every transaction that changes anything writes to `audit_event`. On the tables
of a first year that takes moments. A table a hundred times larger would want
`CREATE INDEX CONCURRENTLY` outside a transaction instead. Every insert into
`audit_event` keeps up to three more indexes up to date, which at the few
hundred events a day the business writes costs nothing that can be measured.

No table, no column and no sequence is created, so there is nothing to grant.

Revision ID: 0008
Revises: 0007
Created: 2026-10-04
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.revision_0008")

AUDIT_ENTITY_ID_INDEX: Final[str] = "ix_audit_event_entity_id"
AUDIT_ACTION_INDEX: Final[str] = "ix_audit_event_action"
AUDIT_ACTOR_INDEX: Final[str] = "ix_audit_event_actor"
NOTIFICATION_QUEUED_INDEX: Final[str] = "ix_notification_queued_at"
HAS_ACTOR_PREDICATE: Final[str] = "actor_user_id IS NOT NULL"
NOT_A_STATUS_CHANGE_PREDICATE: Final[str] = "action <> 'asset.status_changed'"


def upgrade() -> None:
    """Create the four indexes the two logs are read through."""
    op.create_index(AUDIT_ENTITY_ID_INDEX, "audit_event", ["entity_id", "occurred_at"])
    op.create_index(
        AUDIT_ACTION_INDEX,
        "audit_event",
        ["action", "occurred_at"],
        postgresql_where=sa.text(NOT_A_STATUS_CHANGE_PREDICATE),
    )
    op.create_index(
        AUDIT_ACTOR_INDEX,
        "audit_event",
        ["actor_user_id", "occurred_at"],
        postgresql_where=sa.text(HAS_ACTOR_PREDICATE),
    )
    op.create_index(NOTIFICATION_QUEUED_INDEX, "notification", ["queued_at"])
    logger.info(
        "Created %s, %s, %s and %s",
        AUDIT_ENTITY_ID_INDEX,
        AUDIT_ACTION_INDEX,
        AUDIT_ACTOR_INDEX,
        NOTIFICATION_QUEUED_INDEX,
    )


def downgrade() -> None:
    """Drop the four indexes the upgrade created."""
    op.drop_index(NOTIFICATION_QUEUED_INDEX, table_name="notification")
    op.drop_index(AUDIT_ACTOR_INDEX, table_name="audit_event")
    op.drop_index(AUDIT_ACTION_INDEX, table_name="audit_event")
    op.drop_index(AUDIT_ENTITY_ID_INDEX, table_name="audit_event")
    logger.info("Dropped the four indexes of revision 0008")
