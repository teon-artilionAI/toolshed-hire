"""The extensions and enumerated types every baseline table depends on.

These are created first and dropped last. A table cannot name an enumerated
type that does not exist yet, and the exclusion constraint on asset_allocation
cannot be created without `btree_gist`.
"""

from __future__ import annotations

import logging
from typing import Final

from sqlalchemy.dialects import postgresql

from alembic import op

logger = logging.getLogger("alembic.baseline")

# btree_gist lets a GiST index mix an equality operator on a scalar column with
# an overlap operator on a range. Without it, `asset_id WITH =` in the same
# exclusion constraint as `daterange(...) WITH &&` is not creatable. citext
# gives the case insensitive email column, so two accounts cannot differ only
# by capitalisation. pg_trgm backs the trigram index the counter uses to find a
# customer by part of a name, which is a leading wildcard search a btree cannot
# serve.
EXTENSIONS: Final[tuple[str, ...]] = ("btree_gist", "citext", "pg_trgm")

# The seventeen enumerated types, in the order the data schema section of the
# design document lists them. Adding a value later is a new migration.
ENUM_TYPES: Final[dict[str, tuple[str, ...]]] = {
    "user_role": ("CUSTOMER", "COUNTER_STAFF", "ADMIN"),
    "customer_type": ("INDIVIDUAL", "TRADE"),
    "id_doc_type": ("SA_ID", "PASSPORT", "DRIVING_LICENCE"),
    "account_status": ("ACTIVE", "ON_HOLD", "BLACKLISTED"),
    "asset_status": (
        "INTAKE",
        "AVAILABLE",
        "ON_HIRE",
        "QUARANTINED",
        "UNDER_REPAIR",
        "LOST",
        "RETIRED",
    ),
    "condition_grade": ("A", "B", "C"),
    "reservation_status": (
        "DRAFT",
        "HELD",
        "CONFIRMED",
        "COLLECTED",
        "RETURNED",
        "CANCELLED",
        "NO_SHOW",
        "EXPIRED",
    ),
    "release_reason": ("RETURNED", "CANCELLED", "NO_SHOW", "EXPIRED", "REALLOCATED"),
    "rental_status": ("OPEN", "OVERDUE", "PARTIALLY_RETURNED", "RETURNED", "SETTLED"),
    "charge_type": (
        "HIRE",
        "DEPOSIT_HOLD",
        "DEPOSIT_RELEASE",
        "DEPOSIT_FORFEIT",
        "LATE_FEE",
        "DAMAGE_RECOVERY",
        "CLEANING",
        "ADJUSTMENT",
    ),
    "charge_status": ("PENDING", "SETTLED", "WAIVED", "REVERSED"),
    "damage_severity": ("MINOR", "MAJOR", "WRITE_OFF"),
    "damage_status": ("OPEN", "UNDER_REPAIR", "RESOLVED", "WRITTEN_OFF"),
    "notification_type": ("BOOKING_CONFIRMATION",),
    "notification_channel": ("EMAIL",),
    "notification_status": ("QUEUED", "SENT", "FAILED"),
    "revoke_reason": ("LOGOUT", "ROTATION", "REUSE_DETECTED", "ADMIN_REVOKE"),
}


def create() -> None:
    """Create the extensions and then the enumerated types."""
    for extension in EXTENSIONS:
        op.execute(f"CREATE EXTENSION IF NOT EXISTS {extension}")
    bind = op.get_bind()
    for type_name, values in ENUM_TYPES.items():
        postgresql.ENUM(*values, name=type_name).create(bind, checkfirst=True)
    logger.info(
        "Created %d extensions and %d enumerated types", len(EXTENSIONS), len(ENUM_TYPES)
    )


def drop() -> None:
    """Drop the enumerated types and then the extensions.

    The extensions are dropped without CASCADE. If anything outside this
    migration has come to depend on one of them, PostgreSQL refuses and the
    whole downgrade rolls back, which is the right answer. Removing somebody
    else's column to finish a downgrade would not be.
    """
    bind = op.get_bind()
    for type_name in reversed(list(ENUM_TYPES)):
        postgresql.ENUM(name=type_name).drop(bind, checkfirst=True)
    for extension in reversed(EXTENSIONS):
        op.execute(f"DROP EXTENSION IF EXISTS {extension}")
    logger.info(
        "Dropped %d enumerated types and %d extensions", len(ENUM_TYPES), len(EXTENSIONS)
    )
