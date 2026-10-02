"""Booking and allocation: reservation, reservation_line and asset_allocation.

asset_allocation is the table that makes double booking impossible. It carries
the GiST exclusion constraint, which Alembic autogenerate will not write, so it
is written out here by hand as raw DDL.
"""

from __future__ import annotations

import logging
from typing import Final

import sqlalchemy as sa

from alembic import op

from .columns import (
    ON_DELETE,
    enum,
    money,
    non_negative,
    percent,
    timestamp,
    timestamps,
    uuid_column,
    uuid_fk,
    uuid_pk,
)

logger = logging.getLogger("alembic.baseline")

# Creation order. Dropped in reverse.
TABLES: Final[tuple[str, ...]] = ("reservation", "reservation_line", "asset_allocation")

REFERENCE_SEQUENCE: Final[str] = "reservation_reference_seq"
# The worked example in the design document is TSH-R-26-000123, so the
# sequence starts at the next number rather than colliding with it.
REFERENCE_SEQUENCE_START: Final[int] = 124

# The defining constraint. An active allocation of one asset may not overlap
# another active allocation of the same asset. The range is built here rather
# than stored, and the bounds are half open so a return on the twelfth frees
# the twelfth. The partial WHERE clause is what lets a released allocation stay
# in the table as history without blocking a new hire. The GiST index behind
# this constraint is also the index an availability search probes, which is why
# asset_id gets no separate index of its own.
EXCLUSION_CONSTRAINT_DDL: Final[str] = """
ALTER TABLE asset_allocation
ADD CONSTRAINT asset_allocation_no_overlap
EXCLUDE USING gist (
    asset_id WITH =,
    daterange(start_date, end_date, '[)') WITH &&
) WHERE (released_at IS NULL)
"""


def create() -> None:
    """Create the three booking tables, their indexes and the reference sequence."""
    _create_reservation()
    _create_reservation_line()
    _create_asset_allocation()
    op.execute(f"CREATE SEQUENCE {REFERENCE_SEQUENCE} START {REFERENCE_SEQUENCE_START}")
    logger.info("Created booking and allocation tables: %s", ", ".join(TABLES))


def drop() -> None:
    """Drop the reference sequence and the booking tables, children first."""
    op.execute(f"DROP SEQUENCE IF EXISTS {REFERENCE_SEQUENCE}")
    for table in reversed(TABLES):
        op.drop_table(table)
    logger.info("Dropped booking and allocation tables: %s", ", ".join(reversed(TABLES)))


def _create_reservation() -> None:
    """Create reservation and the indexes behind the diary and the two sweeps."""
    op.create_table(
        "reservation",
        uuid_pk(),
        sa.Column("reference", sa.String(16), nullable=False, unique=True),
        # The profile and not the account, so a walk-in owns a booking history.
        uuid_fk("customer_profile_id", "customer_profile.id"),
        uuid_fk("branch_id", "branch.id"),
        sa.Column("start_date", sa.Date(), nullable=False),
        # Exclusive. The day the unit comes back.
        sa.Column("end_date", sa.Date(), nullable=False),
        enum("reservation_status"),
        # Derived from the two dates, so it cannot drift from them.
        sa.Column(
            "hire_days",
            sa.Integer(),
            sa.Computed("end_date - start_date", persisted=True),
            nullable=False,
        ),
        money("subtotal_ex_vat"),
        money("vat_amount"),
        money("deposit_total"),
        money("estimated_total_inc_vat"),
        timestamp("hold_expires_at"),
        uuid_fk("created_by_user_id", "user_account.id"),
        timestamp("confirmed_at"),
        timestamp("cancelled_at"),
        sa.Column("cancellation_reason", sa.String(200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *timestamps(),
        sa.CheckConstraint("end_date > start_date", name="ck_reservation_period"),
        sa.CheckConstraint("end_date - start_date <= 28", name="ck_reservation_max_hire_days"),
        non_negative(
            "reservation",
            "money",
            "subtotal_ex_vat",
            "vat_amount",
            "deposit_total",
            "estimated_total_inc_vat",
        ),
    )
    # The branch diary, and a customer's own bookings.
    op.create_index("ix_reservation_branch_start", "reservation", ["branch_id", "start_date"])
    op.create_index(
        "ix_reservation_customer_start", "reservation", ["customer_profile_id", "start_date"]
    )
    # One partial index per lazy sweep, so a sweep only ever scans rows that
    # could actually change state. Hold expiry is BR-13 and no-show is BR-17.
    op.create_index(
        "ix_reservation_hold_expiry",
        "reservation",
        ["hold_expires_at"],
        postgresql_where=sa.text("status = 'HELD'"),
    )
    op.create_index(
        "ix_reservation_confirmed_start",
        "reservation",
        ["start_date"],
        postgresql_where=sa.text("status = 'CONFIRMED'"),
    )


def _create_reservation_line() -> None:
    """Create reservation_line, one product model and a quantity with its price snapshot."""
    op.create_table(
        "reservation_line",
        uuid_pk(),
        uuid_fk("reservation_id", "reservation.id"),
        uuid_fk("product_model_id", "product_model.id"),
        sa.Column("quantity", sa.SmallInteger(), nullable=False),
        sa.Column("line_position", sa.SmallInteger(), nullable=False),
        # Copied from product_model at creation, so a later price change never
        # rewrites an existing booking (BR-20).
        money("daily_rate_snapshot"),
        money("weekly_rate_snapshot"),
        money("deposit_snapshot"),
        money("late_fee_per_day_snapshot"),
        money("replacement_value_snapshot"),
        percent("discount_percent", default="0"),
        money("line_subtotal_ex_vat"),
        *timestamps(),
        # A model appears once per booking and quantity does the counting.
        sa.UniqueConstraint(
            "reservation_id", "product_model_id", name="uq_reservation_line_model_once"
        ),
        sa.CheckConstraint("quantity >= 1 AND quantity <= 10", name="ck_reservation_line_quantity"),
        non_negative(
            "reservation_line",
            "money",
            "daily_rate_snapshot",
            "weekly_rate_snapshot",
            "deposit_snapshot",
            "late_fee_per_day_snapshot",
            "replacement_value_snapshot",
            "line_subtotal_ex_vat",
        ),
        non_negative("reservation_line", "discount", "discount_percent"),
    )


def _create_asset_allocation() -> None:
    """Create asset_allocation and the exclusion constraint that guards it."""
    op.create_table(
        "asset_allocation",
        uuid_pk(),
        uuid_fk("reservation_line_id", "reservation_line.id"),
        uuid_column("asset_id"),
        uuid_column("branch_id"),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        timestamp("allocated_at", nullable=False, default_now=True),
        # Null means the allocation is active.
        timestamp("released_at"),
        enum("release_reason", "release_reason", nullable=True),
        *timestamps(),
        # Composite, so the branch copy cannot drift from the asset's branch
        # and a unit cannot be allocated at a branch where it is not (BR-06).
        sa.ForeignKeyConstraint(
            ["asset_id", "branch_id"],
            ["asset.id", "asset.branch_id"],
            name="fk_asset_allocation_asset_branch",
            ondelete=ON_DELETE,
        ),
        # The target of the composite foreign key on rental_item.
        sa.UniqueConstraint("id", "asset_id", name="uq_asset_allocation_id_asset"),
        sa.CheckConstraint("end_date > start_date", name="ck_asset_allocation_period"),
        # A released allocation always records why it was released, and an
        # active one never claims a reason. This is what keeps the partial
        # predicate on the exclusion constraint honest.
        sa.CheckConstraint(
            "(released_at IS NULL) = (release_reason IS NULL)",
            name="ck_asset_allocation_release_state",
        ),
    )
    op.execute(EXCLUSION_CONSTRAINT_DDL)
    # Loading a booking reads the allocations of each of its lines, and the
    # exclusion index leads with asset_id, so it cannot serve that lookup.
    op.create_index("ix_asset_allocation_line", "asset_allocation", ["reservation_line_id"])
