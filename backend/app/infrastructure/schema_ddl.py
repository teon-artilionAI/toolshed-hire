"""PostgreSQL specific DDL that Alembic cannot generate, kept in one place.

The migration imports these, the allocation use case imports the constraint
name it has to recognise, and a test can assert the constraint exists by the
same name. Written once here rather than typed out in three files where the
three copies would drift.
"""

from __future__ import annotations

from typing import Final

# btree_gist lets a GiST index mix an equality operator on a scalar column with
# an overlap operator on a range. Without it, `asset_id WITH =` in the same
# exclusion constraint as `daterange(...) WITH &&` is not creatable. citext
# gives the case insensitive email column, so two accounts cannot differ only
# by capitalisation.
REQUIRED_EXTENSIONS: Final[tuple[str, ...]] = ("btree_gist", "citext")

OVERLAP_CONSTRAINT_NAME: Final[str] = "ex_asset_allocations_no_active_overlap"
RELEASE_STATE_CONSTRAINT_NAME: Final[str] = "ck_asset_allocations_release_state"
BRANCH_SCOPE_CONSTRAINT_NAME: Final[str] = "ck_user_accounts_branch_scope"

REFERENCE_SEQUENCE: Final[str] = "reservation_reference_seq"
# The worked example in the documentation is TSH-R-26-000123, so the sequence
# starts at the next number rather than colliding with it.
REFERENCE_SEQUENCE_START: Final[int] = 124

ENUM_TYPES: Final[dict[str, tuple[str, ...]]] = {
    "user_role": ("CUSTOMER", "COUNTER_STAFF", "ADMIN"),
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
        "CLOSED",
        "CANCELLED",
        "NO_SHOW",
        "EXPIRED",
    ),
    "allocation_status": (
        "ACTIVE",
        "RETURNED",
        "CANCELLED",
        "NO_SHOW",
        "EXPIRED",
        "REALLOCATED",
    ),
}

# The defining constraint. An active allocation of one asset may not overlap
# another active allocation of the same asset. The range is built here rather
# than stored, and the bounds are half open so a return on the twelfth frees
# the twelfth. The partial WHERE clause is what lets a released allocation stay
# in the table as history without blocking a new hire.
EXCLUSION_CONSTRAINT_DDL: Final[str] = f"""
ALTER TABLE asset_allocations
ADD CONSTRAINT {OVERLAP_CONSTRAINT_NAME}
EXCLUDE USING gist (
    asset_id WITH =,
    daterange(start_date, end_date, '[)') WITH &&
) WHERE (released_at IS NULL)
"""

# A released allocation must say when it was released, and an active one must
# not claim to have been. Without this the partial index above could be
# bypassed by writing a released status while leaving released_at null.
RELEASE_STATE_CHECK_DDL: Final[str] = f"""
ALTER TABLE asset_allocations
ADD CONSTRAINT {RELEASE_STATE_CONSTRAINT_NAME}
CHECK (
    (status = 'ACTIVE' AND released_at IS NULL)
    OR (status <> 'ACTIVE' AND released_at IS NOT NULL)
)
"""

# Only counter staff are branch scoped, and every one of them is. A nullable
# column without this check could be used to create an unscoped assistant.
BRANCH_SCOPE_CHECK_DDL: Final[str] = f"""
ALTER TABLE user_accounts
ADD CONSTRAINT {BRANCH_SCOPE_CONSTRAINT_NAME}
CHECK ((role = 'COUNTER_STAFF') = (branch_id IS NOT NULL))
"""
