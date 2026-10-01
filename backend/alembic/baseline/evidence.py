"""Evidence and supporting tables: audit_event, notification and rate_limit_counter.

audit_event and rate_limit_counter are the two tables keyed by BIGSERIAL rather
than a UUID. Both are written far more often than they are read, and a
monotonic key is cheaper for that than a random one.

No grants are issued here. Restricting the application role to INSERT and
SELECT on audit_event belongs with the roles themselves, which are created by
a later revision.
"""

from __future__ import annotations

import logging
from typing import Final

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

from .columns import (
    bigserial_pk,
    enum,
    sha256_hex,
    small_int,
    timestamp,
    timestamps,
    uuid_column,
    uuid_fk,
    uuid_pk,
)

logger = logging.getLogger("alembic.baseline")

# Creation order. Dropped in reverse.
TABLES: Final[tuple[str, ...]] = ("audit_event", "notification", "rate_limit_counter")


def create() -> None:
    """Create the three supporting tables and their indexes."""
    _create_audit_event()
    _create_notification()
    _create_rate_limit_counter()
    logger.info("Created evidence and supporting tables: %s", ", ".join(TABLES))


def drop() -> None:
    """Drop the supporting tables."""
    for table in reversed(TABLES):
        op.drop_table(table)
    logger.info("Dropped evidence and supporting tables: %s", ", ".join(reversed(TABLES)))


def _create_audit_event() -> None:
    """Create audit_event, the append only record of every state change.

    It carries no created_at and no updated_at. A row is written once, at
    `occurred_at`, and never changed.
    """
    op.create_table(
        "audit_event",
        bigserial_pk(),
        timestamp("occurred_at", nullable=False, default_now=True),
        # Null for the lazy sweep, which has no human actor.
        uuid_fk("actor_user_id", "user_account.id", nullable=True),
        # Copied, so the log survives a later role change.
        enum("user_role", "actor_role", nullable=True),
        sa.Column("entity_type", sa.String(40), nullable=False),
        # Deliberately not a foreign key. The log has to outlive whatever it
        # describes and must never acquire a cascade path.
        uuid_column("entity_id"),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("before_state", postgresql.JSONB, nullable=True),
        sa.Column("after_state", postgresql.JSONB, nullable=True),
        uuid_column("request_id", nullable=True),
        sa.Column("ip_address", postgresql.INET, nullable=True),
    )
    op.create_index("ix_audit_event_entity", "audit_event", ["entity_type", "entity_id"])
    op.create_index("ix_audit_event_occurred_at", "audit_event", ["occurred_at"])


def _create_notification() -> None:
    """Create notification, the record of an outbound booking confirmation."""
    op.create_table(
        "notification",
        uuid_pk(),
        uuid_fk("reservation_id", "reservation.id"),
        enum("notification_type", "notification_type"),
        enum("notification_channel", "channel"),
        sa.Column("recipient_email", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        enum("notification_status"),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("provider_message_id", sa.String(80), nullable=True),
        small_int("attempts"),
        sa.Column("last_error", sa.String(300), nullable=True),
        timestamp("queued_at", nullable=False),
        timestamp("sent_at"),
        *timestamps(),
        sa.CheckConstraint(
            "status <> 'SENT' OR sent_at IS NOT NULL", name="ck_notification_sent_at"
        ),
    )
    # The sends an administrator can retry. Partial, so delivered mail is not in it.
    op.create_index(
        "ix_notification_failed",
        "notification",
        ["queued_at"],
        postgresql_where=sa.text("status = 'FAILED'"),
    )


def _create_rate_limit_counter() -> None:
    """Create rate_limit_counter, the sliding window counters behind the rate limits.

    The seventeenth table. It has no foreign key, because the limiter has to
    count for an unauthenticated caller with no account row. The bucket key is
    hashed, so an expired window can be swept without the table ever holding an
    address or an identifier. It carries no created_at and no updated_at
    either, because a counter row lives no longer than the window it counts.
    """
    op.create_table(
        "rate_limit_counter",
        bigserial_pk(),
        sha256_hex("bucket_key_hash", nullable=False),
        timestamp("window_started_at", nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint(
            "bucket_key_hash", "window_started_at", name="uq_rate_limit_counter_bucket_window"
        ),
    )
