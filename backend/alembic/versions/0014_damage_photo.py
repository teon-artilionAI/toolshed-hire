"""Record the photographs attached to a damage report (#83).

`damage_photo` holds one row for each photograph the counter attaches to a
report. The photograph itself is in a private bucket. The row holds the name
it is stored under, its media type and size, who attached it and when. The
name is unique, so two rows can never point at one object, and a check keeps
the media type to the two formats a photograph is stored as.

A report is read with its photographs, and the photographs counted before one
more is attached, so `ix_damage_photo_report` is a btree on the report. A hire's
photographs are reached through the reports that name its items, which
`ix_damage_report_rental_item` of revision 0005 already serves.

A photograph is evidence for a deduction from a deposit, so a row is written
once and never changed. The application role is granted SELECT and INSERT, as
it is on the audit trail, and may not update or delete one. Nothing is ever
hard deleted (BR-51), and the bucket's lifecycle rule ends the photograph
itself after the retention period.

`damage_report.photo_path` from the baseline stays as it is and unused. A report
can hold up to six photographs, which one column could not.

The downgrade revokes the grant and drops the table, and with it the record of
every photograph attached since. The objects in the bucket are not touched.

Revision ID: 0014
Revises: 0013
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
# import path from here, as revisions 0001, 0002 and 0013 do.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import role_grants  # noqa: E402
from baseline.columns import timestamp, uuid_fk, uuid_pk  # noqa: E402

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.revision_0014")

PHOTO_TABLE: Final[str] = "damage_photo"
REPORT_INDEX: Final[str] = "ix_damage_photo_report"
OBJECT_KEY_MAX_LENGTH: Final[int] = 200
CONTENT_TYPE_MAX_LENGTH: Final[int] = 32


def upgrade() -> None:
    """Create the table and its index, and let the application insert and read."""
    op.create_table(
        PHOTO_TABLE,
        uuid_pk(),
        uuid_fk("damage_report_id", "damage_report.id"),
        sa.Column("object_key", sa.String(OBJECT_KEY_MAX_LENGTH), nullable=False),
        sa.Column("content_type", sa.String(CONTENT_TYPE_MAX_LENGTH), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        uuid_fk("uploaded_by_user_id", "user_account.id"),
        timestamp("uploaded_at", nullable=False),
        sa.UniqueConstraint("object_key", name="uq_damage_photo_object_key"),
        sa.CheckConstraint(
            "content_type IN ('image/jpeg', 'image/png')", name="ck_damage_photo_content_type"
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_damage_photo_size"),
    )
    op.create_index(REPORT_INDEX, PHOTO_TABLE, ["damage_report_id"])
    logger.info("Created %s and %s", PHOTO_TABLE, REPORT_INDEX)

    role_grants.grant_on_new_tables(op.get_bind(), role_grants.APPEND_ONLY, [PHOTO_TABLE])


def downgrade() -> None:
    """Revoke the grant and drop the table with its index."""
    role_grants.revoke_on_new_tables(op.get_bind(), role_grants.APPEND_ONLY, [PHOTO_TABLE])
    op.drop_index(REPORT_INDEX, table_name=PHOTO_TABLE)
    op.drop_table(PHOTO_TABLE)
    logger.info("Dropped %s", PHOTO_TABLE)
