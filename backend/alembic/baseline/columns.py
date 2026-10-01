"""Column builders shared by the baseline table modules.

The conventions of the schema are stated once here. Every primary key is a UUID
the application generates, apart from the two BIGSERIAL keys. Every foreign key
restricts on delete, because nothing in Toolshed Hire is ever hard deleted
(BR-51) and a cascade would be a delete path by another name. Money is
NUMERIC(12,2) and never floating point (BR-22). Every timestamp carries a time
zone.

A builder returns a fresh column on every call. A SQLAlchemy column belongs to
exactly one table, so the table modules never share an instance.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Final
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from .prerequisites import ENUM_TYPES

MONEY_PRECISION: Final[int] = 12
MONEY_SCALE: Final[int] = 2
PERCENT_PRECISION: Final[int] = 5
PERCENT_SCALE: Final[int] = 2
ON_DELETE: Final[str] = "RESTRICT"
# A SHA-256 digest written as hexadecimal. A token or a rate limit bucket key
# is stored as this and never as itself.
SHA256_HEX_LENGTH: Final[int] = 64


def uuid_pk() -> sa.Column[UUID]:
    """Return the standard application generated UUID primary key column."""
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False)


def bigserial_pk() -> sa.Column[int]:
    """Return a BIGSERIAL primary key, used by the two append heavy tables."""
    return sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False)


def uuid_column(name: str, *, nullable: bool = False, unique: bool = False) -> sa.Column[UUID]:
    """Return a UUID column that carries no single column foreign key."""
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable, unique=unique)


def uuid_fk(
    name: str, target: str, *, nullable: bool = False, unique: bool = False
) -> sa.Column[UUID]:
    """Return a UUID foreign key column that restricts on delete."""
    return sa.Column(
        name,
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey(target, ondelete=ON_DELETE),
        nullable=nullable,
        unique=unique,
    )


def enum(type_name: str, column_name: str = "status", *, nullable: bool = False) -> sa.Column[str]:
    """Return a column bound to an enumerated type the baseline already created."""
    return sa.Column(
        column_name,
        postgresql.ENUM(*ENUM_TYPES[type_name], name=type_name, create_type=False),
        nullable=nullable,
    )


def money(name: str, *, nullable: bool = False, default: str | None = None) -> sa.Column[Decimal]:
    """Return a NUMERIC(12,2) column, optionally with a database side default."""
    return sa.Column(
        name,
        sa.Numeric(MONEY_PRECISION, MONEY_SCALE),
        nullable=nullable,
        server_default=sa.text(default) if default is not None else None,
    )


def percent(name: str, *, default: str | None = None) -> sa.Column[Decimal]:
    """Return a NOT NULL NUMERIC(5,2) column for a rate or a discount percentage."""
    return sa.Column(
        name,
        sa.Numeric(PERCENT_PRECISION, PERCENT_SCALE),
        nullable=False,
        server_default=sa.text(default) if default is not None else None,
    )


def flag(name: str, *, default: bool | None) -> sa.Column[bool]:
    """Return a NOT NULL boolean column.

    Args:
        name: The column name.
        default: The database side default, or None when the value has to be
            an explicit decision on every row.

    """
    server_default = None if default is None else sa.text("true" if default else "false")
    return sa.Column(name, sa.Boolean(), nullable=False, server_default=server_default)


def small_int(name: str, *, default: str = "0") -> sa.Column[int]:
    """Return a NOT NULL SMALLINT column with a database side default, zero unless stated."""
    return sa.Column(name, sa.SmallInteger(), nullable=False, server_default=sa.text(default))


def timestamp(
    name: str, *, nullable: bool = True, default_now: bool = False
) -> sa.Column[datetime]:
    """Return a TIMESTAMPTZ column, optionally defaulted to the transaction time."""
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=nullable,
        server_default=sa.text("now()") if default_now else None,
    )


def timestamps() -> list[sa.Column[datetime]]:
    """Return the created_at and updated_at pair every mutable table carries."""
    return [
        timestamp("created_at", nullable=False, default_now=True),
        timestamp("updated_at", nullable=False, default_now=True),
    ]


def sha256_hex(name: str, *, nullable: bool = True, unique: bool = False) -> sa.Column[str]:
    """Return a CHAR(64) column holding a SHA-256 digest, never the value it was made from."""
    return sa.Column(name, sa.CHAR(SHA256_HEX_LENGTH), nullable=nullable, unique=unique)


def non_negative(table_name: str, label: str, *column_names: str) -> sa.CheckConstraint:
    """Return one named CHECK that keeps every listed column at zero or above.

    Args:
        table_name: The table the constraint belongs to, used in its name.
        label: What the columns have in common, for example `money`.
        column_names: The columns that may not go negative.

    """
    condition = " AND ".join(f"{column} >= 0" for column in column_names)
    return sa.CheckConstraint(condition, name=f"ck_{table_name}_{label}_non_negative")
