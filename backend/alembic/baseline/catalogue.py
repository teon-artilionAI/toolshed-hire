"""Catalogue and fleet: category, product_model and asset.

This is the entity split the whole design rests on. product_model is what a
customer shops for. asset is the individually tagged unit that is actually
allocated, collected and returned. Availability is allocation of specific
assets and never a quantity counter.
"""

from __future__ import annotations

import logging
from typing import Final

import sqlalchemy as sa

from alembic import op

from .columns import enum, flag, money, non_negative, small_int, timestamps, uuid_fk, uuid_pk

logger = logging.getLogger("alembic.baseline")

# Creation order. Dropped in reverse.
TABLES: Final[tuple[str, ...]] = ("category", "product_model", "asset")


def create() -> None:
    """Create the three catalogue and fleet tables and their indexes."""
    _create_category()
    _create_product_model()
    _create_asset()
    logger.info("Created catalogue and fleet tables: %s", ", ".join(TABLES))


def drop() -> None:
    """Drop the catalogue and fleet tables, children first."""
    for table in reversed(TABLES):
        op.drop_table(table)
    logger.info("Dropped catalogue and fleet tables: %s", ", ".join(reversed(TABLES)))


def _create_category() -> None:
    """Create category, with one optional level of nesting."""
    op.create_table(
        "category",
        uuid_pk(),
        sa.Column("code", sa.String(16), nullable=False, unique=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        uuid_fk("parent_category_id", "category.id", nullable=True),
        small_int("sort_order"),
        flag("is_active", default=True),
        *timestamps(),
        # A category may not parent itself. The cap of two levels is a domain
        # rule, because a check constraint cannot follow the chain.
        sa.CheckConstraint("parent_category_id <> id", name="ck_category_not_own_parent"),
    )


def _create_product_model() -> None:
    """Create product_model, the catalogue entry that carries the published rates."""
    op.create_table(
        "product_model",
        uuid_pk(),
        sa.Column("sku", sa.String(24), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(140), nullable=False, unique=True),
        uuid_fk("category_id", "category.id"),
        sa.Column("manufacturer", sa.String(80), nullable=False),
        sa.Column("model_number", sa.String(60), nullable=False),
        sa.Column("short_description", sa.String(300), nullable=False),
        sa.Column("long_description", sa.Text(), nullable=True),
        money("daily_rate"),
        money("weekly_rate"),
        money("deposit_amount"),
        money("late_fee_per_day"),
        money("replacement_value"),
        small_int("min_hire_days", default="1"),
        small_int("max_hire_days", default="28"),
        sa.Column("image_path", sa.String(200), nullable=True),
        flag("is_published", default=False),
        *timestamps(),
        sa.CheckConstraint("max_hire_days >= min_hire_days", name="ck_product_model_hire_days"),
        non_negative(
            "product_model",
            "money",
            "daily_rate",
            "weekly_rate",
            "deposit_amount",
            "late_fee_per_day",
            "replacement_value",
        ),
    )
    # Category browse and result ordering, without touching unpublished drafts.
    op.create_index(
        "ix_product_model_published",
        "product_model",
        ["category_id", "name"],
        postgresql_where=sa.text("is_published"),
    )


def _create_asset() -> None:
    """Create asset, one row per physical unit, and the two availability indexes."""
    op.create_table(
        "asset",
        uuid_pk(),
        # Painted on the machine, so it is unique across the business and the
        # domain refuses to change it once assigned (BR-34).
        sa.Column("asset_tag", sa.String(16), nullable=False, unique=True),
        uuid_fk("product_model_id", "product_model.id"),
        uuid_fk("branch_id", "branch.id"),
        sa.Column("serial_number", sa.String(60), nullable=True),
        enum("asset_status"),
        enum("condition_grade", "condition_grade"),
        sa.Column("acquired_on", sa.Date(), nullable=False),
        money("acquisition_cost"),
        sa.Column("hour_meter_reading", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("retired_on", sa.Date(), nullable=True),
        *timestamps(),
        # These two exist purely so a child table can carry a composite foreign
        # key and have the database refuse a denormalised copy that disagrees.
        # asset_allocation uses the first one (BR-06).
        sa.UniqueConstraint("id", "branch_id", name="uq_asset_id_branch"),
        sa.UniqueConstraint("id", "product_model_id", name="uq_asset_id_product_model"),
        sa.CheckConstraint(
            "(retired_on IS NOT NULL) = (status = 'RETIRED')", name="ck_asset_retired_on"
        ),
        non_negative("asset", "money", "acquisition_cost"),
    )
    # Reduces candidates to hireable units before any date work. Partial, so
    # quarantined, on hire, lost and retired units are not in the index.
    op.create_index(
        "ix_asset_available",
        "asset",
        ["product_model_id", "branch_id"],
        postgresql_where=sa.text("status = 'AVAILABLE'"),
    )
    # The branch stock picture behind the counter dashboard.
    op.create_index("ix_asset_branch_status", "asset", ["branch_id", "status"])
