"""SQLite compatibility for the fast, database free test engine.

The schema is PostgreSQL specific on purpose, so three pieces of it have to be
taught to SQLite before an in memory engine can create the tables at all.

1. `postgresql.UUID` renders as `UUID`, which SQLite does not know. It is
   rendered as `CHAR(32)` instead, which is exactly what SQLAlchemy's own bind
   processor writes into a non native dialect, so the value round trips as a
   `uuid.UUID` either way.
2. `CITEXT` renders as `TEXT COLLATE NOCASE`. That keeps the property the
   column exists for, which is that two accounts cannot differ only by the
   capitalisation of an email address.
3. The native enum types render as `VARCHAR`. The application already binds
   them with `create_type=False`, so nothing tries to issue `CREATE TYPE`.

A default rendering is registered alongside every SQLite rendering. Registering
a dialect specific compiler for a class that does not declare its own
`__visit_name__` removes the inherited fallback, which would turn a perfectly
good PostgreSQL run into an `UnsupportedCompilationError` the moment this module
is imported. The defaults below reproduce what the PostgreSQL compiler already
produces, so importing this module changes nothing for a real database.

The reservation reference comes from a PostgreSQL sequence read with
`SELECT nextval(...)`. SQLite has no sequences, so a Python function of the same
name is registered on the connection. The application is not modified and not
mocked: it issues the same statement it issues in production.
"""

from __future__ import annotations

import itertools
import logging
import sqlite3
from collections.abc import Iterator
from typing import Final

from sqlalchemy import Engine, event
from sqlalchemy.dialects.postgresql import CITEXT, ENUM
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.compiler import GenericTypeCompiler
from sqlmodel import SQLModel, create_engine

from app.infrastructure import models  # noqa: F401  imported so the tables register
from app.infrastructure.schema_ddl import REFERENCE_SEQUENCE_START

logger = logging.getLogger(__name__)

# A shared in memory database. StaticPool is what makes every checkout return
# the one connection that holds it, so the schema created by the fixture is
# still there when the request handler asks for a session on another thread.
SQLITE_MEMORY_URL: Final[str] = "sqlite://"
UUID_SQLITE_TYPE: Final[str] = "CHAR(32)"
CITEXT_SQLITE_TYPE: Final[str] = "TEXT COLLATE NOCASE"
ENUM_SQLITE_TYPE: Final[str] = "VARCHAR(32)"
SEQUENCE_FUNCTION_NAME: Final[str] = "nextval"
SEQUENCE_FUNCTION_ARGUMENT_COUNT: Final[int] = 1


@compiles(PGUUID)
def render_uuid_default(
    type_: PGUUID, compiler: GenericTypeCompiler, **kw: object
) -> str:
    """Render a UUID column for every dialect other than SQLite."""
    return "UUID"


@compiles(PGUUID, "sqlite")
def render_uuid_for_sqlite(
    type_: PGUUID, compiler: GenericTypeCompiler, **kw: object
) -> str:
    """Render a UUID column as the 32 character form SQLAlchemy binds on SQLite."""
    return UUID_SQLITE_TYPE


@compiles(CITEXT)
def render_citext_default(
    type_: CITEXT, compiler: GenericTypeCompiler, **kw: object
) -> str:
    """Render a case insensitive text column for every dialect other than SQLite."""
    return "CITEXT"


@compiles(CITEXT, "sqlite")
def render_citext_for_sqlite(
    type_: CITEXT, compiler: GenericTypeCompiler, **kw: object
) -> str:
    """Render a case insensitive text column using the SQLite NOCASE collation."""
    return CITEXT_SQLITE_TYPE


@compiles(ENUM)
def render_enum_default(type_: ENUM, compiler: GenericTypeCompiler, **kw: object) -> str:
    """Render a native enum column by delegating to the dialect's own compiler."""
    return compiler.visit_ENUM(type_, **kw)


@compiles(ENUM, "sqlite")
def render_enum_for_sqlite(
    type_: ENUM, compiler: GenericTypeCompiler, **kw: object
) -> str:
    """Render a native enum column as plain text, which is all SQLite offers."""
    return ENUM_SQLITE_TYPE


def _install_connection_shims(engine: Engine) -> None:
    """Attach the per connection behaviour the application assumes exists.

    Two things are installed. Foreign keys are enforced, which SQLite leaves off
    by default and which would otherwise let a test insert an allocation against
    an asset that does not exist. And a `nextval` function is registered so the
    reservation reference query runs unchanged.

    Args:
        engine: The SQLite engine to attach the listener to.

    """
    counter: Iterator[int] = itertools.count(REFERENCE_SEQUENCE_START)

    @event.listens_for(engine, "connect")
    def _configure_connection(
        dbapi_connection: sqlite3.Connection, _connection_record: object
    ) -> None:
        """Enable foreign keys and register the sequence stand in."""
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()
        dbapi_connection.create_function(
            SEQUENCE_FUNCTION_NAME,
            SEQUENCE_FUNCTION_ARGUMENT_COUNT,
            lambda _sequence_name: next(counter),
        )
        logger.debug(
            "test.sqlite_connection_configured",
            extra={"foreign_keys": "on", "sequence_function": SEQUENCE_FUNCTION_NAME},
        )


def build_sqlite_engine() -> Engine:
    """Create a fresh in memory SQLite engine with the schema already created.

    Returns:
        An engine holding one connection, with every table in
        `SQLModel.metadata` created and the connection shims installed.

    """
    engine = create_engine(
        SQLITE_MEMORY_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    _install_connection_shims(engine)
    logger.debug("test.sqlite_engine_created", extra={"url": SQLITE_MEMORY_URL})
    SQLModel.metadata.create_all(engine)
    logger.debug(
        "test.sqlite_schema_created",
        extra={"table_count": len(SQLModel.metadata.tables)},
    )
    return engine


__all__ = ["SQLITE_MEMORY_URL", "build_sqlite_engine"]
