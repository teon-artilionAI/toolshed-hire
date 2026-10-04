"""The names in the PostgreSQL schema that the application has to know.

The migration creates the schema from its own frozen definitions under
`alembic/baseline` and imports nothing from here, so a later edit to this
module cannot change what an already released migration does. What lives here
is the application's side of the same facts. The asset repository imports
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

# One account for one address. The column is declared unique in the baseline,
# and this is the name PostgreSQL gives the constraint. The account repository
# recognises it when two registrations race for one address.
ACCOUNT_EMAIL_CONSTRAINT_NAME: Final[str] = "user_account_email_key"

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
    "ix_damage_report_rental_item",
    "ix_rental_item_lost",
    "ix_audit_event_asset_status",
    "ix_audit_event_actor",
    "ix_audit_event_action",
)

REFERENCE_SEQUENCE: Final[str] = "reservation_reference_seq"
# The worked example in the design document is TSH-R-26-000123, so the
# sequence starts at the next number rather than colliding with it.
REFERENCE_SEQUENCE_START: Final[int] = 124
# Rental references come from a sequence of their own. The worked example is
# rental TSH-H-26-000098, and the migration starts the sequence after it.
RENTAL_REFERENCE_SEQUENCE: Final[str] = "rental_reference_seq"
# Damage report references come from the third sequence of the baseline.
DAMAGE_REPORT_REFERENCE_SEQUENCE: Final[str] = "damage_report_reference_seq"

# The three indexes the counter's customer lookup stands on. The first two
# are in the baseline. The third is revision 0003, a trigram index over the
# digits of the contact phone, and its expression has to be written in the
# search exactly as the migration wrote it, or the planner cannot use it.
CUSTOMER_NAME_SEARCH_INDEX: Final[str] = "ix_customer_profile_display_name_trgm"
CUSTOMER_EMAIL_SEARCH_INDEX: Final[str] = "user_account_email_key"
CUSTOMER_PHONE_SEARCH_INDEX: Final[str] = "ix_customer_profile_phone_digits_trgm"
# The punctuation a phone number may carry, in the order the index expression
# removes it, innermost first.
PHONE_PUNCTUATION_REMOVED: Final[tuple[str, ...]] = (" ", "-", "(", ")", "+")

# The three indexes of revision 0004. The asset locator matches part of a tag
# through the first and reaches the units of a model through the second. The
# counter's diary reads the hires due back at a branch on any day through the
# third, which the partial index on open hires cannot serve for a day that is
# past.
ASSET_TAG_SEARCH_INDEX: Final[str] = "ix_asset_tag_trgm"
ASSET_MODEL_INDEX: Final[str] = "ix_asset_product_model"
RENTAL_BRANCH_DUE_INDEX: Final[str] = "ix_rental_branch_due_back"

# The two indexes of revision 0005. Every read of a rental asks whether a
# damage report names each of its units, through the first, which is partial
# because a report outside a hire names no unit of a hire. The reports of one
# unit, which a list by tag and the close of a report read, are reached
# through the second.
DAMAGE_REPORT_RENTAL_ITEM_INDEX: Final[str] = "ix_damage_report_rental_item"
DAMAGE_REPORT_ASSET_INDEX: Final[str] = "ix_damage_report_asset"

# The five indexes of revision 0007, which the utilisation report reads a
# period through. The charges raised in a period, the hires still out or back
# since it began, the losses recorded, the damage reports open or resolved in
# it, and the changes of each unit's status, partial on that one action.
CHARGE_RAISED_INDEX: Final[str] = "ix_charge_raised_at"
RENTAL_ITEM_RETURNED_INDEX: Final[str] = "ix_rental_item_returned_at"
RENTAL_ITEM_LOST_INDEX: Final[str] = "ix_rental_item_lost"
DAMAGE_REPORT_RESOLVED_INDEX: Final[str] = "ix_damage_report_resolved_at"
AUDIT_STATUS_CHANGE_INDEX: Final[str] = "ix_audit_event_asset_status"

# The indexes the two logs of the admin console are read through. The first
# two are of the baseline. The other four are revision 0008, which finds the
# history of one record by its key, every event of one action but a change of
# status, everything one account did, partial on an event that has an actor,
# and every notification newest first.
AUDIT_ENTITY_INDEX: Final[str] = "ix_audit_event_entity"
AUDIT_OCCURRED_INDEX: Final[str] = "ix_audit_event_occurred_at"
AUDIT_ENTITY_ID_INDEX: Final[str] = "ix_audit_event_entity_id"
AUDIT_ACTION_INDEX: Final[str] = "ix_audit_event_action"
AUDIT_ACTOR_INDEX: Final[str] = "ix_audit_event_actor"
NOTIFICATION_QUEUED_INDEX: Final[str] = "ix_notification_queued_at"
NOTIFICATION_FAILED_INDEX: Final[str] = "ix_notification_failed"
# The action the partial index of the report holds and that of the log leaves out.
STATUS_CHANGE_ACTION: Final[str] = "asset.status_changed"

# The columns a revision after the baseline added to one of its tables, each
# with its table and the default PostgreSQL prints back for it. Revision 0006
# adds the counter's damage flag to `rental_item`. It is NOT NULL and defaults
# to false, so a release that never names it still inserts a rental item, and
# the schema test checks the default for that reason.
RENTAL_ITEM_TABLE: Final[str] = "rental_item"
DAMAGE_FLAG_COLUMN: Final[str] = "flagged_for_damage"
COLUMNS_ADDED_AFTER_BASELINE: Final[tuple[tuple[str, str, str], ...]] = (
    (RENTAL_ITEM_TABLE, DAMAGE_FLAG_COLUMN, "false"),
)

# The seventeen native enumerated types and their members, read from the domain
# enumerations so there is one Python statement of each.
ENUM_TYPES: Final[dict[str, tuple[str, ...]]] = {
    type_name: tuple(enumeration.values()) for type_name, enumeration in ENUMS_BY_TYPE_NAME.items()
}
