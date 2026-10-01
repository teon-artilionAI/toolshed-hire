"""The names in the PostgreSQL schema that the application has to know.

The migration creates the schema from its own frozen definitions under
`alembic/baseline` and imports nothing from here, so a later edit to this
module cannot change what an already released migration does. What lives here
is the application's side of the same facts. The allocation use case imports
the constraint name it has to recognise, the health check and the tests read
the extension list, and an integration test asserts that the database the
migration built carries every one of these names. That test is what keeps the
two listings from drifting.
"""

from __future__ import annotations

from typing import Final

from app.domain.enums import ENUMS_BY_TYPE_NAME

# btree_gist lets a GiST index mix an equality operator on a scalar column with
# an overlap operator on a range. Without it, `asset_id WITH =` in the same
# exclusion constraint as `daterange(...) WITH &&` is not creatable. citext
# gives the case insensitive email column, so two accounts cannot differ only
# by capitalisation. pg_trgm backs the trigram index behind the counter's
# customer lookup by part of a name.
REQUIRED_EXTENSIONS: Final[tuple[str, ...]] = ("btree_gist", "citext", "pg_trgm")

# The seventeen tables of the documented schema, parents before children.
TABLE_NAMES: Final[tuple[str, ...]] = (
    "branch",
    "user_account",
    "customer_profile",
    "refresh_session",
    "category",
    "product_model",
    "asset",
    "reservation",
    "reservation_line",
    "asset_allocation",
    "rental",
    "rental_item",
    "damage_report",
    "charge",
    "audit_event",
    "notification",
    "rate_limit_counter",
)

ALLOCATION_TABLE: Final[str] = "asset_allocation"

# The defining constraint. An active allocation of one asset may not overlap
# another active allocation of the same asset. The range is built inside the
# constraint rather than stored, and the bounds are half open so a return on
# the twelfth frees the twelfth. The partial WHERE clause is what lets a
# released allocation stay in the table as history without blocking a new hire.
OVERLAP_CONSTRAINT_NAME: Final[str] = "asset_allocation_no_overlap"
# The constraint as PostgreSQL prints it back through pg_get_constraintdef. It
# is the documented clause with the two decorations the catalogue adds, a cast
# on the bound specifier and a second pair of brackets round the predicate.
OVERLAP_CONSTRAINT_DEFINITION: Final[str] = (
    "EXCLUDE USING gist (asset_id WITH =, "
    "daterange(start_date, end_date, '[)'::text) WITH &&) "
    "WHERE ((released_at IS NULL))"
)

# A released allocation always records why it was released, and an active one
# never claims a reason. Without this the partial predicate above could be
# sidestepped by writing a reason while leaving released_at null.
RELEASE_STATE_CONSTRAINT_NAME: Final[str] = "ck_asset_allocation_release_state"

# Only counter staff are branch scoped, and every one of them is.
BRANCH_SCOPE_CONSTRAINT_NAME: Final[str] = "ck_user_account_branch_scope"

# Every partial index the schema defines. An index that kept its name and lost
# its predicate would go on answering queries, so nothing would fail and nobody
# would notice it had grown to cover every row. The schema test checks each of
# these by name for that reason.
PARTIAL_INDEX_NAMES: Final[tuple[str, ...]] = (
    "ix_asset_available",
    "ix_product_model_published",
    "ix_reservation_hold_expiry",
    "ix_reservation_confirmed_start",
    "ix_rental_open_due_back",
    "ix_charge_rental_item",
    "ix_notification_failed",
    "ix_refresh_session_live",
    "ux_user_account_email_verification_token_hash",
    "ux_user_account_password_reset_token_hash",
)

REFERENCE_SEQUENCE: Final[str] = "reservation_reference_seq"
# The worked example in the design document is TSH-R-26-000123, so the
# sequence starts at the next number rather than colliding with it.
REFERENCE_SEQUENCE_START: Final[int] = 124

# The seventeen native enumerated types and their members, read from the domain
# enumerations so there is one Python statement of each.
ENUM_TYPES: Final[dict[str, tuple[str, ...]]] = {
    type_name: tuple(enumeration.values()) for type_name, enumeration in ENUMS_BY_TYPE_NAME.items()
}
