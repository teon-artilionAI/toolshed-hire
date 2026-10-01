"""Column builders shared by the model modules.

The conventions of the schema are stated once here rather than on every field.
Every primary key is a UUID the application generates, apart from the two
BIGSERIAL keys. Every foreign key restricts on delete. Money is NUMERIC(12,2).
Every timestamp carries a time zone.

A builder returns a fresh column on every call, because a SQLAlchemy column
belongs to exactly one table.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Final
from uuid import UUID

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.domain.enums import DomainEnum

MONEY_PRECISION: Final[int] = 12
MONEY_SCALE: Final[int] = 2
PERCENT_PRECISION: Final[int] = 5
PERCENT_SCALE: Final[int] = 2
ON_DELETE: Final[str] = "RESTRICT"
# A SHA-256 digest written as hexadecimal. A token or a rate limit bucket key
# is stored as this and never as itself.
SHA256_HEX_LENGTH: Final[int] = 64


def uuid_pk() -> Column[UUID]:
    """Return a fresh application generated UUID primary key column."""
    return Column(PGUUID(as_uuid=True), primary_key=True, nullable=False)


def bigserial_pk() -> Column[int]:
    """Return a BIGSERIAL primary key, which the database numbers on insert."""
    return Column(BigInteger, primary_key=True, autoincrement=True, nullable=False)


def uuid_column(*, nullable: bool = False, unique: bool = False) -> Column[UUID]:
    """Return a UUID column that carries no single column foreign key."""
    return Column(PGUUID(as_uuid=True), nullable=nullable, unique=unique)


def uuid_fk(target: str, *, nullable: bool = False, unique: bool = False) -> Column[UUID]:
    """Return a UUID foreign key column with ON DELETE RESTRICT.

    Nothing in Toolshed Hire is ever hard deleted (BR-51), so every foreign key
    restricts rather than cascades. A cascade would be a delete path by another
    name.
    """
    return Column(
        PGUUID(as_uuid=True),
        ForeignKey(target, ondelete=ON_DELETE),
        nullable=nullable,
        unique=unique,
    )


def enum_column(
    python_enum: type[DomainEnum], type_name: str, *, nullable: bool = False
) -> Column[str]:
    """Return a column bound to an existing native PostgreSQL enum type."""
    return Column(
        ENUM(
            python_enum,
            name=type_name,
            create_type=False,
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=nullable,
    )


def money(*, nullable: bool = False, default: str | None = None) -> Column[Decimal]:
    """Return a NUMERIC(12,2) column. Money is never floating point (BR-22)."""
    return Column(
        Numeric(MONEY_PRECISION, MONEY_SCALE),
        nullable=nullable,
        server_default=text(default) if default is not None else None,
    )


def percent(*, default: str | None = None) -> Column[Decimal]:
    """Return a NOT NULL NUMERIC(5,2) column for a rate or a discount percentage."""
    return Column(
        Numeric(PERCENT_PRECISION, PERCENT_SCALE),
        nullable=False,
        server_default=text(default) if default is not None else None,
    )


def flag(*, default: bool | None) -> Column[bool]:
    """Return a NOT NULL boolean column.

    Args:
        default: The database side default, or None when the value has to be
            an explicit decision on every row.

    """
    server_default = None if default is None else text("true" if default else "false")
    return Column(Boolean, nullable=False, server_default=server_default)


def small_int(*, default: str = "0") -> Column[int]:
    """Return a NOT NULL SMALLINT column with a database side default, zero unless stated."""
    return Column(SmallInteger, nullable=False, server_default=text(default))


def varchar(length: int, *, nullable: bool = False, unique: bool = False) -> Column[str]:
    """Return a VARCHAR column of the given length."""
    return Column(String(length), nullable=nullable, unique=unique)


def sha256_hex(*, nullable: bool = True, unique: bool = False) -> Column[str]:
    """Return a CHAR(64) column holding a SHA-256 digest, never the value it was made from."""
    return Column(CHAR(SHA256_HEX_LENGTH), nullable=nullable, unique=unique)


def timestamp(*, nullable: bool = True, default_now: bool = False) -> Column[datetime]:
    """Return a TIMESTAMPTZ column, optionally defaulted by the database."""
    return Column(
        DateTime(timezone=True),
        nullable=nullable,
        server_default=func.now() if default_now else None,
    )


def created_at_column() -> Column[datetime]:
    """Return the standard creation timestamp column, defaulted by the database."""
    return Column(DateTime(timezone=True), nullable=False, server_default=func.now())


def updated_at_column() -> Column[datetime]:
    """Return the standard update timestamp column, defaulted by the database."""
    return Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
