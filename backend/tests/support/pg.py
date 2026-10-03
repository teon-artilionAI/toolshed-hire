"""PostgreSQL only helpers.

Kept apart from the rest of the support package so that a test run with no
database never imports anything that assumes one.

The SQLSTATE reader is written here rather than imported from the application,
deliberately. The point of the exclusion constraint tests is that the driver
itself reports `23P01`, and asserting that through the application's own reader
would prove only that the reader agrees with itself.
"""

from __future__ import annotations

import logging
from typing import Final
from uuid import UUID

from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.infrastructure.schema_ddl import TABLE_NAMES

logger = logging.getLogger(__name__)

# PostgreSQL exclusion_violation.
EXCLUSION_VIOLATION_SQLSTATE: Final[str] = "23P01"
CHECK_VIOLATION_SQLSTATE: Final[str] = "23514"
EXCLUSION_CONSTRAINT_TYPE: Final[str] = "x"
# Longer than any transaction this suite opens deliberately, short enough that a
# leaked one is reported rather than waited on.
TRUNCATE_LOCK_TIMEOUT_SECONDS: Final[int] = 20

ENUM_TYPE_KIND: Final[str] = "e"
BASE_TABLE_KIND: Final[str] = "BASE TABLE"

# Every table of the documented schema is disposable to this suite. They are
# truncated children first, although CASCADE makes the order cosmetic.
SCHEMA_TABLES: Final[tuple[str, ...]] = tuple(reversed(TABLE_NAMES))


def sqlstate_of(error: IntegrityError) -> str | None:
    """Return the five character SQLSTATE the driver attached to the error.

    Args:
        error: The IntegrityError raised by the flush.

    Returns:
        The SQLSTATE, or None if the driver reported none, which is itself a
        failure worth seeing in an assertion message.

    """
    original = error.orig
    state = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    return str(state) if state is not None else None


def constraint_name_of(error: IntegrityError) -> str | None:
    """Return the constraint name from the driver diagnostics, never from the message."""
    diagnostics = getattr(error.orig, "diag", None)
    name = getattr(diagnostics, "constraint_name", None) if diagnostics is not None else None
    return str(name) if name else None


def installed_extensions(session: Session) -> set[str]:
    """Return the names of every extension installed in the connected database."""
    logger.debug("test.extension_query_started")
    rows = session.execute(text("SELECT extname FROM pg_extension")).scalars().all()
    logger.debug("test.extension_query_finished", extra={"extension_count": len(rows)})
    return {str(row) for row in rows}


def exclusion_constraint_names(session: Session, table_name: str) -> set[str]:
    """Return the names of every exclusion constraint on a table.

    Read from `pg_constraint` with `contype = 'x'`, which is the catalogue's own
    answer to "is this an exclusion constraint", rather than from a parsed
    definition string.
    """
    logger.debug("test.constraint_query_started", extra={"table": table_name})
    rows = (
        session.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = to_regclass(:table) AND contype = :contype"
            ),
            {"table": table_name, "contype": EXCLUSION_CONSTRAINT_TYPE},
        )
        .scalars()
        .all()
    )
    logger.debug(
        "test.constraint_query_finished",
        extra={"table": table_name, "constraint_count": len(rows)},
    )
    return {str(row) for row in rows}


def constraint_definition(session: Session, table_name: str, constraint_name: str) -> str | None:
    """Return a constraint as PostgreSQL itself prints it back, or None if absent.

    `pg_get_constraintdef` is the catalogue's own rendering, so the comparison
    is against what the database is enforcing and not against the text the
    migration happened to send.
    """
    logger.debug(
        "test.constraint_definition_query_started",
        extra={"table": table_name, "constraint": constraint_name},
    )
    definition = session.execute(
        text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = to_regclass(:table) AND conname = :name"
        ),
        {"table": table_name, "name": constraint_name},
    ).scalar_one_or_none()
    logger.debug(
        "test.constraint_definition_query_finished",
        extra={"constraint": constraint_name, "found": definition is not None},
    )
    return str(definition) if definition is not None else None


def table_names(session: Session) -> set[str]:
    """Return the name of every ordinary table in the connected schema."""
    logger.debug("test.table_query_started")
    rows = (
        session.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_type = :kind"
            ),
            {"kind": BASE_TABLE_KIND},
        )
        .scalars()
        .all()
    )
    logger.debug("test.table_query_finished", extra={"table_count": len(rows)})
    return {str(row) for row in rows}


def column_nullability(session: Session, table_name: str) -> dict[str, bool]:
    """Return every column of a table with whether it accepts NULL."""
    logger.debug("test.column_query_started", extra={"table": table_name})
    rows = session.execute(
        text(
            "SELECT column_name, is_nullable = 'YES' FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = :table"
        ),
        {"table": table_name},
    ).all()
    logger.debug(
        "test.column_query_finished", extra={"table": table_name, "column_count": len(rows)}
    )
    return {str(name): bool(nullable) for name, nullable in rows}


def column_default(session: Session, table_name: str, column_name: str) -> str | None:
    """Return the default of one column as PostgreSQL prints it back, or None when it has none."""
    logger.debug(
        "test.column_default_query_started", extra={"table": table_name, "column": column_name}
    )
    default = session.execute(
        text(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = :table "
            "AND column_name = :column"
        ),
        {"table": table_name, "column": column_name},
    ).scalar_one_or_none()
    logger.debug(
        "test.column_default_query_finished",
        extra={"table": table_name, "column": column_name, "default": default},
    )
    return str(default) if default is not None else None


def partial_index_predicates(session: Session) -> dict[str, str]:
    """Return every partial index in the connected schema with its predicate.

    Read from `pg_index.indpred`, which is null for an ordinary index. An index
    that kept its name and lost its WHERE clause is therefore absent from the
    result, which is exactly the failure worth catching.
    """
    logger.debug("test.partial_index_query_started")
    rows = session.execute(
        text(
            "SELECT c.relname, pg_get_expr(i.indpred, i.indrelid) "
            "FROM pg_index i "
            "JOIN pg_class c ON c.oid = i.indexrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = current_schema() AND i.indpred IS NOT NULL"
        )
    ).all()
    logger.debug("test.partial_index_query_finished", extra={"index_count": len(rows)})
    return {str(name): str(predicate) for name, predicate in rows}


def enum_type_labels(session: Session) -> dict[str, tuple[str, ...]]:
    """Return every native enumerated type with its labels in their stored order."""
    logger.debug("test.enum_query_started")
    rows = session.execute(
        text(
            "SELECT t.typname, e.enumlabel "
            "FROM pg_type t "
            "JOIN pg_enum e ON e.enumtypid = t.oid "
            "JOIN pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname = current_schema() AND t.typtype = :kind "
            "ORDER BY t.typname, e.enumsortorder"
        ),
        {"kind": ENUM_TYPE_KIND},
    ).all()
    labels: dict[str, list[str]] = {}
    for type_name, label in rows:
        labels.setdefault(str(type_name), []).append(str(label))
    logger.debug("test.enum_query_finished", extra={"type_count": len(labels)})
    return {type_name: tuple(values) for type_name, values in labels.items()}


def count_active_allocations(session: Session, asset_id: UUID) -> int:
    """Return how many unreleased allocations the database holds for one asset.

    Read with a fresh statement rather than through the identity map, because
    the question being asked is what is committed, not what this session thinks.
    """
    result = session.execute(
        text(
            "SELECT count(*) FROM asset_allocation "
            "WHERE asset_id = :asset_id AND released_at IS NULL"
        ),
        {"asset_id": asset_id},
    ).scalar_one()
    return int(result)


def truncate_schema_tables(engine: Engine) -> None:
    """Empty every table the suite writes to, in one statement.

    TRUNCATE with CASCADE is used rather than DELETE because it is one round
    trip and because it cannot leave a half emptied table behind if a test
    aborted mid transaction. The caller is responsible for having checked that
    this database is disposable.

    A lock timeout is set first. TRUNCATE needs ACCESS EXCLUSIVE on every table,
    so a connection left open by a concurrency test that failed part way through
    would otherwise block this statement forever, and every later test would
    queue behind it. The suite would then hang until the pipeline killed it,
    reporting nothing about the test that actually broke. With the timeout the
    first run to misbehave says so.

    Args:
        engine: The engine pointing at the test database.

    """
    statement = f"TRUNCATE TABLE {', '.join(SCHEMA_TABLES)} RESTART IDENTITY CASCADE"
    logger.debug("test.truncate_started", extra={"table_count": len(SCHEMA_TABLES)})
    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL lock_timeout = '{TRUNCATE_LOCK_TIMEOUT_SECONDS}s'"))
        connection.execute(text(statement))
    logger.debug("test.truncate_finished", extra={"table_count": len(SCHEMA_TABLES)})


__all__ = [
    "CHECK_VIOLATION_SQLSTATE",
    "EXCLUSION_VIOLATION_SQLSTATE",
    "SCHEMA_TABLES",
    "column_nullability",
    "constraint_definition",
    "constraint_name_of",
    "count_active_allocations",
    "enum_type_labels",
    "exclusion_constraint_names",
    "installed_extensions",
    "partial_index_predicates",
    "sqlstate_of",
    "table_names",
    "truncate_schema_tables",
]
