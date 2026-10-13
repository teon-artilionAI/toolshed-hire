"""Give each branch a trading week and a record of the days it closes.

The design has the branches trading 07:00 to 17:00 from Monday to Friday and
07:00 to 13:00 on a Saturday, closed on a Sunday and on public holidays. The
branch table holds one opening and one closing time, which every day shared,
so a booking for a Sunday was accepted and the no show sweep waited until 17:00
on a Saturday. Two tables put that right.

`branch_trading_hours` holds a branch's hours for each ISO weekday, Monday 1 to
Sunday 7. A weekday with no row is a day the branch never opens, so Sunday has
none. The primary key is the branch and the weekday, so a branch cannot have two
sets of hours for one day, and a check keeps the closing time after the opening
time. The application only reads it, so it is granted SELECT and nothing more.
Hours change rarely, by a migration or by the operator.

`closure_day` records a day a branch does not trade although its week says it
would, a stocktake or a day the government declares. A null branch means every
branch. The reason is required because a customer reads it. A closure is
cancelled, never deleted (BR-51), and a partial unique index allows one live
closure per branch and day. A closure for every branch is keyed on the nil UUID
in that index, because two nulls never collide in a unique index. The owner
writes these, so the application is granted SELECT, INSERT and UPDATE.

Public holidays are not stored. They follow from the Public Holidays Act and are
worked out in app/domain/public_holidays.py for any year.

The upgrade gives every existing branch the design's week, taking its weekday
hours from the branch's own `opens_at` and `closes_at` and closing at 13:00 on a
Saturday. `branch.opens_at` and `branch.closes_at` stay, unread by the new code,
so the release still serving while this runs keeps working. A later revision can
drop them once no release reads them.

The downgrade revokes the grants and drops both tables, and with them every
closure day recorded since.

Revision ID: 0013
Revises: 0012
Created: 2026-10-13
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import sqlalchemy as sa

from alembic import op

# Alembic loads this file by its path, so the alembic directory is put on the
# import path from here, as revisions 0001 and 0002 do.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import role_grants  # noqa: E402
from baseline.columns import timestamp, timestamps, uuid_fk, uuid_pk  # noqa: E402

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.revision_0013")

HOURS_TABLE: Final[str] = "branch_trading_hours"
CLOSURE_TABLE: Final[str] = "closure_day"
REASON_MAX_LENGTH: Final[int] = 120
# The key a closure for every branch takes in the unique index.
EVERY_BRANCH_KEY: Final[str] = "00000000-0000-0000-0000-000000000000"
SATURDAY: Final[int] = 6
SATURDAY_CLOSES_AT: Final[str] = "13:00"

GIVE_EXISTING_BRANCHES_THE_DESIGN_WEEK: Final[str] = f"""
INSERT INTO {HOURS_TABLE} (branch_id, weekday, opens_at, closes_at)
SELECT branch.id, weekday.number, branch.opens_at,
       CASE WHEN weekday.number = {SATURDAY}
            THEN LEAST(branch.closes_at, TIME '{SATURDAY_CLOSES_AT}')
            ELSE branch.closes_at END
FROM branch
CROSS JOIN generate_series(1, {SATURDAY}) AS weekday(number)
"""


def upgrade() -> None:
    """Create both tables, give every branch its week and grant the application role."""
    op.create_table(
        HOURS_TABLE,
        uuid_fk("branch_id", "branch.id"),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("opens_at", sa.Time(), nullable=False),
        sa.Column("closes_at", sa.Time(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("branch_id", "weekday", name="pk_branch_trading_hours"),
        sa.CheckConstraint("weekday BETWEEN 1 AND 7", name="ck_branch_trading_hours_weekday"),
        sa.CheckConstraint("closes_at > opens_at", name="ck_branch_trading_hours_order"),
    )
    op.create_table(
        CLOSURE_TABLE,
        uuid_pk(),
        uuid_fk("branch_id", "branch.id", nullable=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(REASON_MAX_LENGTH), nullable=False),
        uuid_fk("created_by_user_id", "user_account.id"),
        timestamp("created_at", nullable=False, default_now=True),
        timestamp("cancelled_at"),
        uuid_fk("cancelled_by_user_id", "user_account.id", nullable=True),
        sa.CheckConstraint("length(btrim(reason)) > 0", name="ck_closure_day_reason"),
        sa.CheckConstraint(
            "(cancelled_at IS NULL) = (cancelled_by_user_id IS NULL)",
            name="ck_closure_day_cancellation",
        ),
    )
    op.create_index(
        "uq_closure_day_live",
        CLOSURE_TABLE,
        [sa.text(f"coalesce(branch_id, '{EVERY_BRANCH_KEY}'::uuid)"), "day"],
        unique=True,
        postgresql_where=sa.text("cancelled_at IS NULL"),
    )
    # Every question asks for the live closures in a range of days.
    op.create_index(
        "ix_closure_day_live_day",
        CLOSURE_TABLE,
        ["day"],
        postgresql_where=sa.text("cancelled_at IS NULL"),
    )
    logger.info("Created %s and %s", HOURS_TABLE, CLOSURE_TABLE)

    connection = op.get_bind()
    inserted = connection.execute(sa.text(GIVE_EXISTING_BRANCHES_THE_DESIGN_WEEK)).rowcount
    logger.info("Gave the existing branches the design's week, %d rows of hours", inserted)

    role_grants.grant_on_new_tables(connection, role_grants.READ_ONLY, [HOURS_TABLE])
    role_grants.grant_on_new_tables(connection, role_grants.READ_WRITE, [CLOSURE_TABLE])


def downgrade() -> None:
    """Revoke the grants and drop both tables."""
    connection = op.get_bind()
    role_grants.revoke_on_new_tables(connection, role_grants.READ_WRITE, [CLOSURE_TABLE])
    role_grants.revoke_on_new_tables(connection, role_grants.READ_ONLY, [HOURS_TABLE])
    op.drop_index("ix_closure_day_live_day", table_name=CLOSURE_TABLE)
    op.drop_index("uq_closure_day_live", table_name=CLOSURE_TABLE)
    op.drop_table(CLOSURE_TABLE)
    op.drop_table(HOURS_TABLE)
    logger.info("Dropped %s and %s", CLOSURE_TABLE, HOURS_TABLE)

