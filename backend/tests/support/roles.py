"""Helpers for the tests that connect as the two restricted database roles.

The roles are created through the same code the provisioning script runs, and
the table privileges are applied through the same function migration 0002
calls. Nothing is set up by hand, so the suite proves the restriction on a
laptop and in the pipeline alike, and it proves the code that will be deployed
and not a copy of it.

Roles belong to the PostgreSQL cluster and not to one database, so a role
survives a dropped schema and may or may not exist when the migrations run.
`provision_restricted_roles` therefore always does both steps. Each is safe to
repeat, and afterwards the privileges are in place whichever came first.

Importing this module opens no connection. The run with no database still
collects the test module that uses it, and nothing here reaches for PostgreSQL
until a fixture is asked for.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Final

import psycopg
from sqlalchemy import Engine, create_engine, make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from scripts.provision_roles import APPLICATION_ROLE, MIGRATION_ROLE, driver_url, provision_roles

# `role_grants` sits in the alembic directory, which is not a package. The
# migrations put that directory on the import path from their own location,
# and this does the same, so the import does not depend on a migration having
# been loaded first.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "alembic"))

import role_grants

logger = logging.getLogger(__name__)

# Throwaway values for the disposable test database. They protect nothing.
APPLICATION_ROLE_PASSWORD: Final[str] = "local_only_throwaway_app_role_password"
MIGRATION_ROLE_PASSWORD: Final[str] = "local_only_throwaway_migrate_role_password"

# PostgreSQL insufficient_privilege.
INSUFFICIENT_PRIVILEGE_SQLSTATE: Final[str] = "42501"


def provision_restricted_roles(owner_engine: Engine, owner_url: str) -> None:
    """Create both roles and give the application role its table privileges.

    Args:
        owner_engine: An engine connected as the owner of the test database.
        owner_url: The owner's connection string, as the application holds it.

    Raises:
        RuntimeError: If the grants were skipped, which would mean the role
            was not there straight after it was provisioned.

    """
    logger.info("test.role_provisioning_started")
    with psycopg.connect(driver_url(owner_url)) as connection:
        provision_roles(
            connection,
            app_password=APPLICATION_ROLE_PASSWORD,
            migrate_password=MIGRATION_ROLE_PASSWORD,
        )
    with owner_engine.begin() as connection:
        granted = role_grants.grant_application_privileges(connection)
    if not granted:
        raise RuntimeError(
            f"Attempted to grant privileges to {APPLICATION_ROLE} straight after provisioning "
            "it, and the grant function reported that the role does not exist."
        )
    logger.info(
        "test.role_provisioning_finished", extra={"roles": [APPLICATION_ROLE, MIGRATION_ROLE]}
    )


def engine_as(owner_url: str, role_name: str, password: str) -> Engine:
    """Return an engine on the same database, signed in as another role.

    NullPool, so every connection is closed when its block ends and none is
    left holding a lock when the tables are truncated between tests.
    """
    url = make_url(owner_url).set(username=role_name, password=password)
    return create_engine(url, poolclass=NullPool, echo=False)


def sqlstate_of_refusal(error: DBAPIError) -> str | None:
    """Return the SQLSTATE the driver attached to a refused statement.

    Read from the driver's own diagnostics and never from the message, for the
    reason given in `pg`. A message changes with a release or a locale.
    """
    state = getattr(error.orig, "sqlstate", None)
    return str(state) if state is not None else None


__all__ = [
    "APPLICATION_ROLE",
    "APPLICATION_ROLE_PASSWORD",
    "INSUFFICIENT_PRIVILEGE_SQLSTATE",
    "MIGRATION_ROLE",
    "MIGRATION_ROLE_PASSWORD",
    "engine_as",
    "provision_restricted_roles",
    "sqlstate_of_refusal",
]
