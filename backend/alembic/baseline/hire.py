"""Hire and money: rental, rental_item, damage_report and charge.

A reservation is the promise and a rental is the fulfilment, which is what
makes late fees, partial returns and no-shows expressible. Every money line on
a hire lives in the one charge table, deposits included, so settlement is a
single sum and gross contribution per asset is a single grouped query.
"""

from __future__ import annotations

import logging
from typing import Final

import sqlalchemy as sa

from alembic import op

from .columns import (
    ON_DELETE,
    enum,
    flag,
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

# Creation order. damage_report comes before charge because a damage recovery
# charge points at the report behind it. Dropped in reverse.
TABLES: Final[tuple[str, ...]] = ("rental", "rental_item", "damage_report", "charge")

DEPOSIT_CHARGE_TYPES: Final[str] = "'DEPOSIT_HOLD', 'DEPOSIT_RELEASE', 'DEPOSIT_FORFEIT'"


def create() -> None:
    """Create the four hire and money tables and their indexes."""
    _create_rental()
    _create_rental_item()
    _create_damage_report()
    _create_charge()
    logger.info("Created hire and money tables: %s", ", ".join(TABLES))


def drop() -> None:
    """Drop the hire and money tables, children first."""
    for table in reversed(TABLES):
        op.drop_table(table)
    logger.info("Dropped hire and money tables: %s", ", ".join(reversed(TABLES)))


def _create_rental() -> None:
    """Create rental, the hire once the customer has walked out with the goods."""
    op.create_table(
        "rental",
        uuid_pk(),
        sa.Column("reference", sa.String(16), nullable=False, unique=True),
        # Unique, because a booking is collected once.
        uuid_fk("reservation_id", "reservation.id", unique=True),
        uuid_fk("branch_id", "branch.id"),
        enum("rental_status"),
        timestamp("checked_out_at", nullable=False),
        uuid_fk("checked_out_by_user_id", "user_account.id"),
        sa.Column("due_back_on", sa.Date(), nullable=False),
        timestamp("returned_at"),
        uuid_fk("returned_to_user_id", "user_account.id", nullable=True),
        money("deposit_held"),
        money("deposit_refunded", default="0"),
        money("deposit_withheld", default="0"),
        money("balance_due", default="0"),
        timestamp("settled_at"),
        flag("agreement_signed", default=False),
        *timestamps(),
        # No more of a deposit can be kept or given back than was taken (BR-32).
        sa.CheckConstraint(
            "deposit_withheld + deposit_refunded <= deposit_held",
            name="ck_rental_deposit_settlement",
        ),
        # A closed hire carries the moment its last item came back (BR-53).
        sa.CheckConstraint(
            "status NOT IN ('RETURNED', 'SETTLED') OR returned_at IS NOT NULL",
            name="ck_rental_closed_has_return",
        ),
        non_negative(
            "rental",
            "money",
            "deposit_held",
            "deposit_refunded",
            "deposit_withheld",
            "balance_due",
        ),
    )
    # The overdue worklist. Partial, so a hire that is back is not in it.
    op.create_index(
        "ix_rental_open_due_back",
        "rental",
        ["due_back_on"],
        postgresql_where=sa.text("returned_at IS NULL"),
    )


def _create_rental_item() -> None:
    """Create rental_item, one physical asset handed over on a rental."""
    op.create_table(
        "rental_item",
        uuid_pk(),
        uuid_fk("rental_id", "rental.id"),
        # Unique, because an allocation is collected once.
        uuid_column("asset_allocation_id", unique=True),
        uuid_column("asset_id"),
        enum("condition_grade", "condition_out"),
        enum("condition_grade", "condition_in", nullable=True),
        sa.Column("hour_meter_out", sa.Integer(), nullable=True),
        sa.Column("hour_meter_in", sa.Integer(), nullable=True),
        sa.Column("accessories_out", sa.String(200), nullable=True),
        sa.Column("accessories_in", sa.String(200), nullable=True),
        timestamp("checked_out_at", nullable=False),
        timestamp("returned_at"),
        sa.Column("days_late", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("notes", sa.Text(), nullable=True),
        *timestamps(),
        # Composite, so the asset copy kept for reporting cannot disagree with
        # the allocation the item came from.
        sa.ForeignKeyConstraint(
            ["asset_allocation_id", "asset_id"],
            ["asset_allocation.id", "asset_allocation.asset_id"],
            name="fk_rental_item_allocation_asset",
            ondelete=ON_DELETE,
        ),
        sa.CheckConstraint("hour_meter_in >= hour_meter_out", name="ck_rental_item_hour_meter"),
    )
    # Revenue and cost attributed to one unit, for the utilisation report.
    op.create_index("ix_rental_item_asset", "rental_item", ["asset_id"])
    # Every checkout sheet and return screen loads the items of one rental.
    op.create_index("ix_rental_item_rental", "rental_item", ["rental_id"])


def _create_damage_report() -> None:
    """Create damage_report, the record that a specific asset came back damaged."""
    op.create_table(
        "damage_report",
        uuid_pk(),
        sa.Column("reference", sa.String(16), nullable=False, unique=True),
        uuid_fk("asset_id", "asset.id"),
        # Null when the damage was found outside a hire.
        uuid_fk("rental_item_id", "rental_item.id", nullable=True),
        enum("damage_severity", "severity"),
        enum("damage_status"),
        sa.Column("description", sa.Text(), nullable=False),
        # An object key in the private photograph bucket, never a public path.
        sa.Column("photo_path", sa.String(200), nullable=True),
        money("repair_estimate"),
        money("actual_repair_cost", nullable=True),
        # No default. Fair wear and tear is not charged, and whether this is
        # that is an explicit decision on every report (BR-40).
        flag("chargeable_to_customer", default=None),
        uuid_fk("reported_by_user_id", "user_account.id"),
        timestamp("reported_at", nullable=False),
        timestamp("resolved_at"),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        *timestamps(),
        # The actual repair cost is the figure gross contribution subtracts,
        # so a resolved report may not leave it out.
        sa.CheckConstraint(
            "status <> 'RESOLVED' OR actual_repair_cost IS NOT NULL",
            name="ck_damage_report_resolved_cost",
        ),
        non_negative("damage_report", "money", "repair_estimate", "actual_repair_cost"),
    )


def _create_charge() -> None:
    """Create charge, every money line on a rental, positive or negative."""
    op.create_table(
        "charge",
        uuid_pk(),
        uuid_fk("rental_id", "rental.id"),
        # Set when the charge is attributable to one asset. Null is hire level.
        uuid_fk("rental_item_id", "rental_item.id", nullable=True),
        uuid_fk("damage_report_id", "damage_report.id", nullable=True),
        enum("charge_type", "charge_type"),
        sa.Column("description", sa.String(200), nullable=False),
        # Signed. A refund or a deposit release is a negative amount, so the
        # three amount columns are the only money in the schema with no floor.
        money("amount_ex_vat"),
        percent("vat_rate"),
        money("vat_amount"),
        money("amount_inc_vat"),
        enum("charge_status"),
        timestamp("raised_at", nullable=False),
        uuid_fk("raised_by_user_id", "user_account.id"),
        timestamp("settled_at"),
        sa.Column("payment_reference", sa.String(40), nullable=True),
        # A correction is a new row that points back at the one it corrects.
        uuid_fk("reverses_charge_id", "charge.id", nullable=True),
        sa.Column("waiver_reason", sa.String(200), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "amount_inc_vat = amount_ex_vat + vat_amount", name="ck_charge_inclusive_amount"
        ),
        # A deposit held against a future supply is not consideration, so a
        # deposit movement carries no VAT. A withholding is a separate row.
        sa.CheckConstraint(
            f"charge_type NOT IN ({DEPOSIT_CHARGE_TYPES}) OR (vat_rate = 0 AND vat_amount = 0)",
            name="ck_charge_deposit_zero_vat",
        ),
        sa.CheckConstraint(
            "status <> 'WAIVED' OR waiver_reason IS NOT NULL", name="ck_charge_waiver_reason"
        ),
        non_negative("charge", "vat_rate", "vat_rate"),
    )
    # Settlement reads every charge on a rental. Gross contribution reads the
    # charges on one item, and that index is partial because a hire level
    # charge attributes to no unit.
    op.create_index("ix_charge_rental", "charge", ["rental_id"])
    op.create_index(
        "ix_charge_rental_item",
        "charge",
        ["rental_item_id"],
        postgresql_where=sa.text("rental_item_id IS NOT NULL"),
    )
