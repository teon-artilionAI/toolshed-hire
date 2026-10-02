"""What the restricted application role may do to the baseline schema.

The running API connects as `toolshed_app`. It reads, inserts and updates
rows, and that is all. It may not delete, because nothing in Toolshed Hire is
ever hard deleted (BR-51), with one exception. `rate_limit_counter` holds
windows that expire, and removing an expired window is the only delete the
application performs. `audit_event` is tighter still. The role may insert into
it and read it, and may not update or delete a row, so the application that
writes the audit trail cannot rewrite it (BR-49).

Migration 0002 calls `grant_application_privileges`, and so does the test
that proves the restriction, so what is tested is what is deployed. Like the
`baseline` package this module is a snapshot. It reads the table names from
the baseline and imports nothing from the application. A later migration that
creates a table or a sequence grants on it in its own file and leaves this one
as it is.

The role itself is created by `scripts/provision_roles.py`, before the
migrations run. If it is absent the grants are skipped and logged, so a plain
local database with a single owner still migrates.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa
from baseline import booking, catalogue, evidence, hire, identity
from psycopg import sql

logger = logging.getLogger("alembic.role_grants")

APPLICATION_ROLE: Final[str] = "toolshed_app"

# The seventeen tables of migration 0001, parents before children.
BASELINE_TABLES: Final[tuple[str, ...]] = (
    *identity.TABLES,
    *catalogue.TABLES,
    *booking.TABLES,
    *hire.TABLES,
    *evidence.TABLES,
)
# The sequences behind reservation, rental and damage report references and
# the two behind the BIGSERIAL keys. Inserting a row draws from a sequence,
# which needs USAGE on it.
BASELINE_SEQUENCES: Final[tuple[str, ...]] = (
    booking.REFERENCE_SEQUENCE,
    hire.RENTAL_REFERENCE_SEQUENCE,
    hire.DAMAGE_REPORT_REFERENCE_SEQUENCE,
    "audit_event_id_seq",
    "rate_limit_counter_id_seq",
)
APPEND_ONLY_TABLE: Final[str] = "audit_event"
SWEPT_TABLE: Final[str] = "rate_limit_counter"

READ_WRITE: Final[sql.SQL] = sql.SQL("SELECT, INSERT, UPDATE")
APPEND_ONLY: Final[sql.SQL] = sql.SQL("SELECT, INSERT")
SWEEP: Final[sql.SQL] = sql.SQL("DELETE")
SEQUENCE_USE: Final[sql.SQL] = sql.SQL("USAGE, SELECT")
EVERYTHING: Final[sql.SQL] = sql.SQL("ALL PRIVILEGES")

GRANT_ON_TABLES: Final[sql.SQL] = sql.SQL("GRANT {privileges} ON TABLE {objects} TO {role}")
REVOKE_ON_TABLES: Final[sql.SQL] = sql.SQL("REVOKE {privileges} ON TABLE {objects} FROM {role}")
GRANT_ON_SEQUENCES: Final[sql.SQL] = sql.SQL("GRANT {privileges} ON SEQUENCE {objects} TO {role}")
REVOKE_ON_SEQUENCES: Final[sql.SQL] = sql.SQL(
    "REVOKE {privileges} ON SEQUENCE {objects} FROM {role}"
)


def role_exists(connection: sa.Connection, role_name: str = APPLICATION_ROLE) -> bool:
    """Return True when the named role exists in the cluster."""
    found = connection.execute(
        sa.text("SELECT 1 FROM pg_roles WHERE rolname = :name"), {"name": role_name}
    ).first()
    return found is not None


def grant_application_privileges(connection: sa.Connection) -> bool:
    """Give `toolshed_app` its privileges on the baseline tables and sequences.

    Safe to run more than once. `audit_event` is stripped before its two
    privileges are granted, so the outcome is the same whatever the role held
    on it before.

    Args:
        connection: A connection as the owner of the tables, inside a
            transaction the caller commits.

    Returns:
        True when the grants were applied, False when the role does not exist
        and nothing was done.

    """
    if not role_exists(connection):
        logger.info(
            "Skipped the grants for %s because the role does not exist. To restrict the "
            "application, run scripts/provision_roles.py, then downgrade to 0001 and "
            "upgrade again.",
            APPLICATION_ROLE,
        )
        return False
    ordinary_tables = [table for table in BASELINE_TABLES if table != APPEND_ONLY_TABLE]
    _run(connection, GRANT_ON_TABLES, READ_WRITE, ordinary_tables)
    _run(connection, REVOKE_ON_TABLES, EVERYTHING, [APPEND_ONLY_TABLE])
    _run(connection, GRANT_ON_TABLES, APPEND_ONLY, [APPEND_ONLY_TABLE])
    _run(connection, GRANT_ON_TABLES, SWEEP, [SWEPT_TABLE])
    _run(connection, GRANT_ON_SEQUENCES, SEQUENCE_USE, BASELINE_SEQUENCES)
    logger.info(
        "Granted %s its privileges on %d tables and %d sequences. %s is select and insert "
        "only, and %s alone allows delete",
        APPLICATION_ROLE,
        len(BASELINE_TABLES),
        len(BASELINE_SEQUENCES),
        APPEND_ONLY_TABLE,
        SWEPT_TABLE,
    )
    return True


def revoke_application_privileges(connection: sa.Connection) -> bool:
    """Take back exactly what `grant_application_privileges` gave.

    Args:
        connection: A connection as the owner of the tables, inside a
            transaction the caller commits.

    Returns:
        True when the privileges were revoked, False when the role does not
        exist and there was nothing to revoke.

    """
    if not role_exists(connection):
        logger.info(
            "Skipped revoking from %s because the role does not exist.", APPLICATION_ROLE
        )
        return False
    _run(connection, REVOKE_ON_SEQUENCES, SEQUENCE_USE, BASELINE_SEQUENCES)
    _run(connection, REVOKE_ON_TABLES, SWEEP, [SWEPT_TABLE])
    _run(connection, REVOKE_ON_TABLES, READ_WRITE, BASELINE_TABLES)
    logger.info(
        "Revoked the privileges of %s on %d tables and %d sequences",
        APPLICATION_ROLE,
        len(BASELINE_TABLES),
        len(BASELINE_SEQUENCES),
    )
    return True


def _run(
    connection: sa.Connection, template: sql.SQL, privileges: sql.SQL, objects: Sequence[str]
) -> None:
    """Compose one grant or revoke statement and execute it.

    The object names and the role are quoted as identifiers by the driver's
    own composition, so no name is ever pasted into the statement as text.
    """
    statement = template.format(
        privileges=privileges,
        objects=sql.SQL(", ").join(sql.Identifier(name) for name in objects),
        role=sql.Identifier(APPLICATION_ROLE),
    )
    connection.exec_driver_sql(statement.as_string())
