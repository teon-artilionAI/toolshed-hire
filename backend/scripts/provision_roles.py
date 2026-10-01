"""Create the two database roles the design document describes.

`toolshed_migrate` runs the migrations, so it may create objects in this
database and in the `public` schema. `toolshed_app` is what the running API
connects as. It may connect and may use the schema, and nothing more is given
to it here. What it may do to each table is granted by the migrations, because
only they know which tables exist.

Whoever owns the database runs this once, before the first migration, as
`python scripts/provision_roles.py` from the backend directory. It reads three
environment variables. DATABASE_OWNER_URL is the owner's connection string.
APP_ROLE_PASSWORD and MIGRATE_ROLE_PASSWORD are the passwords the two roles
are given. Running it again is safe. A role that exists has its password set
again, which is also how a password is rotated, and a grant that is already in
place is a no operation.

Every statement is built with `psycopg.sql`, so a role name is quoted as an
identifier and a password as a literal, and neither is ever pasted into SQL as
text. The passwords are never logged here. A role definition takes no bound
parameters, so the password does travel inside the statement, and a server set
to log every statement would record it. That is worth knowing before turning
statement logging on for the owner.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Final

import psycopg
from psycopg import sql
from psycopg.rows import TupleRow

from app.logging_config import configure_logging

logger = logging.getLogger("provision_roles")

OWNER_URL_VARIABLE: Final[str] = "DATABASE_OWNER_URL"
APP_PASSWORD_VARIABLE: Final[str] = "APP_ROLE_PASSWORD"
MIGRATE_PASSWORD_VARIABLE: Final[str] = "MIGRATE_ROLE_PASSWORD"

APPLICATION_ROLE: Final[str] = "toolshed_app"
MIGRATION_ROLE: Final[str] = "toolshed_migrate"
SCHEMA_NAME: Final[str] = "public"
MINIMUM_ROLE_PASSWORD_LENGTH: Final[int] = 16

# The application writes its connection strings for SQLAlchemy. The driver
# itself wants the plain form, so the same value works in either variable.
SQLALCHEMY_URL_PREFIX: Final[str] = "postgresql+psycopg://"
DRIVER_URL_PREFIX: Final[str] = "postgresql://"
ACCEPTED_URL_PREFIXES: Final[tuple[str, ...]] = (DRIVER_URL_PREFIX, "postgres://")
URL_SCHEME_SEPARATOR: Final[str] = "://"

EXIT_FAILURE: Final[int] = 1
UNREACHABLE_DETAIL: Final[str] = (
    f"the server gave no message, so the connection named by {OWNER_URL_VARIABLE} could "
    "not be opened or was lost"
)

CREATE_ROLE: Final[sql.SQL] = sql.SQL("CREATE ROLE {role} LOGIN PASSWORD {password}")
ALTER_ROLE: Final[sql.SQL] = sql.SQL("ALTER ROLE {role} LOGIN PASSWORD {password}")
GRANT_ON_DATABASE: Final[sql.SQL] = sql.SQL("GRANT {privileges} ON DATABASE {database} TO {role}")
GRANT_ON_SCHEMA: Final[sql.SQL] = sql.SQL("GRANT {privileges} ON SCHEMA {schema} TO {role}")

# What each role is given on the database and on the schema. The migration
# role needs CREATE on the database for the three extensions and CREATE on the
# schema for the tables, the types and the sequence.
DATABASE_PRIVILEGES: Final[dict[str, sql.SQL]] = {
    MIGRATION_ROLE: sql.SQL("CONNECT, CREATE"),
    APPLICATION_ROLE: sql.SQL("CONNECT"),
}
SCHEMA_PRIVILEGES: Final[dict[str, sql.SQL]] = {
    MIGRATION_ROLE: sql.SQL("USAGE, CREATE"),
    APPLICATION_ROLE: sql.SQL("USAGE"),
}


@dataclass(frozen=True, slots=True)
class ProvisioningSettings:
    """The owner connection and the two role passwords, read from the environment.

    The three values are kept out of the representation, so an instance that
    ends up in a log line or a traceback gives nothing away.
    """

    owner_url: str = field(repr=False)
    app_password: str = field(repr=False)
    migrate_password: str = field(repr=False)


def driver_url(connection_url: str) -> str:
    """Return a connection string in the form the driver accepts.

    Args:
        connection_url: A PostgreSQL URL, with or without the SQLAlchemy driver
            suffix on its scheme.

    Raises:
        ValueError: If the value is not a PostgreSQL URL. The message names
            only the scheme, because the rest of the value holds a password.

    """
    candidate = connection_url.strip()
    if candidate.startswith(SQLALCHEMY_URL_PREFIX):
        return DRIVER_URL_PREFIX + candidate[len(SQLALCHEMY_URL_PREFIX) :]
    if candidate.startswith(ACCEPTED_URL_PREFIXES):
        return candidate
    scheme = ""
    if URL_SCHEME_SEPARATOR in candidate:
        scheme = candidate.split(URL_SCHEME_SEPARATOR, 1)[0]
    raise ValueError(
        f"{OWNER_URL_VARIABLE} must be a PostgreSQL connection string starting with "
        f"{SQLALCHEMY_URL_PREFIX!r}, {DRIVER_URL_PREFIX!r} or 'postgres://'. The value given "
        f"has scheme {scheme!r}."
    )


def read_settings() -> ProvisioningSettings:
    """Read the owner connection and the role passwords from the environment.

    Raises:
        ValueError: If a variable is unset or empty, the connection string is
            not a PostgreSQL URL, or a password is too short. The message names
            the variable and never the value.

    """
    values: dict[str, str] = {}
    for variable in (OWNER_URL_VARIABLE, APP_PASSWORD_VARIABLE, MIGRATE_PASSWORD_VARIABLE):
        value = os.environ.get(variable, "")
        if not value.strip():
            raise ValueError(
                f"{variable} is not set. Role provisioning reads {OWNER_URL_VARIABLE}, "
                f"{APP_PASSWORD_VARIABLE} and {MIGRATE_PASSWORD_VARIABLE} from the environment."
            )
        values[variable] = value
    return ProvisioningSettings(
        owner_url=driver_url(values[OWNER_URL_VARIABLE]),
        app_password=values[APP_PASSWORD_VARIABLE],
        migrate_password=values[MIGRATE_PASSWORD_VARIABLE],
    )


def provision_roles(
    connection: psycopg.Connection[TupleRow], *, app_password: str, migrate_password: str
) -> None:
    """Create or update the two login roles and grant them what they need.

    The statements run on the connection that is passed in and nothing is
    committed here, so the caller decides whether the whole change stands.

    Args:
        connection: An open connection as the owner of the database.
        app_password: The password `toolshed_app` signs in with.
        migrate_password: The password `toolshed_migrate` signs in with.

    Raises:
        ValueError: If a password is shorter than the minimum.
        psycopg.Error: If the connected role may not create roles or grant on
            the database.

    """
    passwords = {MIGRATION_ROLE: migrate_password, APPLICATION_ROLE: app_password}
    for role_name, password in passwords.items():
        _check_password(role_name, password)
    database_name = _current_database(connection)
    logger.info(
        "roles.provisioning_started",
        extra={"database": database_name, "roles": sorted(passwords)},
    )
    for role_name, password in passwords.items():
        created = _ensure_login_role(connection, role_name, password)
        connection.execute(
            GRANT_ON_DATABASE.format(
                privileges=DATABASE_PRIVILEGES[role_name],
                database=sql.Identifier(database_name),
                role=sql.Identifier(role_name),
            )
        )
        connection.execute(
            GRANT_ON_SCHEMA.format(
                privileges=SCHEMA_PRIVILEGES[role_name],
                schema=sql.Identifier(SCHEMA_NAME),
                role=sql.Identifier(role_name),
            )
        )
        logger.info(
            "roles.role_provisioned",
            extra={
                "role": role_name,
                "outcome": "created" if created else "already existed, password set again",
                "database_privileges": DATABASE_PRIVILEGES[role_name].as_string(),
                "schema_privileges": SCHEMA_PRIVILEGES[role_name].as_string(),
            },
        )
    logger.info("roles.provisioning_finished", extra={"database": database_name})


def _check_password(role_name: str, password: str) -> None:
    """Refuse a password too short to protect a login role."""
    if len(password) < MINIMUM_ROLE_PASSWORD_LENGTH:
        raise ValueError(
            f"The password for {role_name} is {len(password)} characters. The minimum is "
            f"{MINIMUM_ROLE_PASSWORD_LENGTH}."
        )


def _current_database(connection: psycopg.Connection[TupleRow]) -> str:
    """Return the name of the database the connection is attached to."""
    row = connection.execute("SELECT current_database()").fetchone()
    if row is None:
        raise RuntimeError(
            "Attempted to read current_database() and the server returned no row."
        )
    return str(row[0])


def _ensure_login_role(
    connection: psycopg.Connection[TupleRow], role_name: str, password: str
) -> bool:
    """Create the role if it is missing, otherwise set its password again.

    Returns:
        True when the role was created, False when it already existed.

    """
    exists = (
        connection.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role_name,)).fetchone()
        is not None
    )
    template = ALTER_ROLE if exists else CREATE_ROLE
    connection.execute(
        template.format(role=sql.Identifier(role_name), password=sql.Literal(password))
    )
    return not exists


def main() -> int:
    """Provision the roles against the database named by the environment.

    Returns:
        The process exit code, zero on success.

    """
    configure_logging()
    try:
        settings = read_settings()
        with psycopg.connect(settings.owner_url) as connection:
            provision_roles(
                connection,
                app_password=settings.app_password,
                migrate_password=settings.migrate_password,
            )
    except ValueError as exc:
        logger.error(
            "roles.provisioning_refused",
            extra={"error_type": type(exc).__name__, "detail": str(exc)},
        )
        return EXIT_FAILURE
    except psycopg.Error as exc:
        # The full text of a driver error can quote the statement that failed,
        # and a role statement holds a password. I log the SQLSTATE and the
        # server's one line summary, which never carry the statement.
        logger.error(
            "roles.provisioning_failed",
            extra={
                "error_type": type(exc).__name__,
                "sqlstate": exc.sqlstate,
                "detail": exc.diag.message_primary or UNREACHABLE_DETAIL,
            },
        )
        return EXIT_FAILURE
    return 0


if __name__ == "__main__":
    sys.exit(main())
