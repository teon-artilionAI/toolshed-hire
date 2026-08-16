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

logger = logging.getLogger(__name__)

# PostgreSQL exclusion_violation.
EXCLUSION_VIOLATION_SQLSTATE: Final[str] = "23P01"
CHECK_VIOLATION_SQLSTATE: Final[str] = "23514"
EXCLUSION_CONSTRAINT_TYPE: Final[str] = "x"
# Longer than any transaction this suite opens deliberately, short enough that a
# leaked one is reported rather than waited on.
TRUNCATE_LOCK_TIMEOUT_SECONDS: Final[int] = 20

# Truncated in dependency order, although CASCADE makes the order cosmetic. It
# is written out anyway so a reader can see exactly which tables the suite
# considers disposable.
SKELETON_TABLES: Final[tuple[str, ...]] = (
    "asset_allocations",
    "reservation_lines",
    "reservations",
    "assets",
    "product_models",
    "user_accounts",
    "branches",
)


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


def count_active_allocations(session: Session, asset_id: UUID) -> int:
    """Return how many unreleased allocations the database holds for one asset.

    Read with a fresh statement rather than through the identity map, because
    the question being asked is what is committed, not what this session thinks.
    """
    result = session.execute(
        text(
            "SELECT count(*) FROM asset_allocations "
            "WHERE asset_id = :asset_id AND released_at IS NULL"
        ),
        {"asset_id": asset_id},
    ).scalar_one()
    return int(result)


def truncate_skeleton_tables(engine: Engine) -> None:
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
    statement = f"TRUNCATE TABLE {', '.join(SKELETON_TABLES)} RESTART IDENTITY CASCADE"
    logger.debug("test.truncate_started", extra={"table_count": len(SKELETON_TABLES)})
    with engine.begin() as connection:
        connection.execute(text(f"SET LOCAL lock_timeout = '{TRUNCATE_LOCK_TIMEOUT_SECONDS}s'"))
        connection.execute(text(statement))
    logger.debug("test.truncate_finished", extra={"table_count": len(SKELETON_TABLES)})


__all__ = [
    "CHECK_VIOLATION_SQLSTATE",
    "EXCLUSION_VIOLATION_SQLSTATE",
    "SKELETON_TABLES",
    "constraint_name_of",
    "count_active_allocations",
    "exclusion_constraint_names",
    "installed_extensions",
    "sqlstate_of",
    "truncate_skeleton_tables",
]
