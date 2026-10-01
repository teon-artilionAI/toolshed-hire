"""The running application cannot rewrite the audit trail or hard delete a row.

The design document gives the API its own database role, `toolshed_app`, with
less authority than the role that runs the migrations. Two of the business
rules are only true if that restriction is real. BR-49 says the audit log is
append only, and BR-51 says nothing is ever hard deleted. Application code that
never issues an UPDATE on `audit_event` is a habit. A database that refuses one
is a guarantee, and it still holds when the application has a bug or somebody
reuses its credentials.

Every statement below is sent on a connection signed in as the restricted role,
and a refusal is asserted by SQLSTATE 42501 from the driver, never by the
message.

The module provisions the roles itself through `scripts/provision_roles.py` and
applies the grants through the function migration 0002 calls. The tables are
emptied around every test by the owner, because the restricted role is exactly
the one that may not do it.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Final

import pytest
from sqlalchemy import Engine, Executable, delete, func, select, table, text
from sqlalchemy.exc import ProgrammingError

from app.infrastructure.schema_ddl import TABLE_NAMES
from tests.support.roles import (
    APPLICATION_ROLE,
    APPLICATION_ROLE_PASSWORD,
    INSUFFICIENT_PRIVILEGE_SQLSTATE,
    MIGRATION_ROLE,
    MIGRATION_ROLE_PASSWORD,
    engine_as,
    provision_restricted_roles,
    sqlstate_of_refusal,
)

pytestmark = [pytest.mark.postgres, pytest.mark.usefixtures("postgres_session")]

AUDIT_TABLE: Final[str] = "audit_event"
SWEPT_TABLE: Final[str] = "rate_limit_counter"
# Every table but the one whose expired windows are swept.
NEVER_DELETED_TABLES: Final[tuple[str, ...]] = tuple(
    name for name in TABLE_NAMES if name != SWEPT_TABLE
)

INSERT_AUDIT_EVENT: Final[str] = (
    "INSERT INTO audit_event (entity_type, entity_id, action) "
    "VALUES ('branch', gen_random_uuid(), :action)"
)
INSERT_BRANCH: Final[str] = (
    "INSERT INTO branch (id, code, name, street_address, suburb, city, postal_code, phone, "
    "opens_at, closes_at) VALUES (gen_random_uuid(), 'TST', 'Role test branch', "
    "'1 Test Road', 'Woodstock', 'Cape Town', '7925', '021 555 0100', '07:00', '17:00')"
)
INSERT_RATE_LIMIT_WINDOW: Final[str] = (
    "INSERT INTO rate_limit_counter (bucket_key_hash, window_started_at, request_count) "
    "VALUES (repeat('a', 64), now() - interval '1 hour', 3)"
)


@pytest.fixture(scope="module")
def provisioned(postgres_engine: Engine, postgres_url: str) -> None:
    """Create both roles and apply the application grants, once for the module."""
    provision_restricted_roles(postgres_engine, postgres_url)


@pytest.fixture(scope="module")
def application_engine(provisioned: None, postgres_url: str) -> Iterator[Engine]:
    """Yield an engine signed in as the restricted application role."""
    engine = engine_as(postgres_url, APPLICATION_ROLE, APPLICATION_ROLE_PASSWORD)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def migration_engine(provisioned: None, postgres_url: str) -> Iterator[Engine]:
    """Yield an engine signed in as the migration role."""
    engine = engine_as(postgres_url, MIGRATION_ROLE, MIGRATION_ROLE_PASSWORD)
    try:
        yield engine
    finally:
        engine.dispose()


def refused_sqlstate(engine: Engine, statement: Executable) -> str | None:
    """Run a statement that must be refused and return the SQLSTATE of the refusal."""
    with engine.connect() as connection, pytest.raises(ProgrammingError) as caught:
        connection.execute(statement)
    return sqlstate_of_refusal(caught.value)


def count_rows(engine: Engine, table_name: str) -> int:
    """Return how many rows a table holds, as seen by the given role."""
    statement = select(func.count()).select_from(table(table_name))
    with engine.connect() as connection:
        return int(connection.execute(statement).scalar_one())


class TestTheApplicationRoleCanAppendToTheAuditTrailAndReadIt:
    """The two things the application legitimately does with the audit log."""

    def test_it_signs_in_as_the_restricted_role(self, application_engine: Engine) -> None:
        with application_engine.connect() as connection:
            assert connection.execute(text("SELECT current_user")).scalar_one() == APPLICATION_ROLE

    def test_an_insert_succeeds_and_the_row_can_be_read_back(
        self, application_engine: Engine
    ) -> None:
        with application_engine.begin() as connection:
            connection.execute(text(INSERT_AUDIT_EVENT), {"action": "ROLE_PROBE"})
        with application_engine.connect() as connection:
            actions = (
                connection.execute(text("SELECT action FROM audit_event")).scalars().all()
            )
        assert actions == ["ROLE_PROBE"]


class TestTheApplicationRoleCannotRewriteTheAuditTrail:
    """BR-49. An audit row is written once and is never changed or removed."""

    def test_an_update_is_refused(self, application_engine: Engine) -> None:
        with application_engine.begin() as connection:
            connection.execute(text(INSERT_AUDIT_EVENT), {"action": "ORIGINAL"})

        state = refused_sqlstate(
            application_engine, text("UPDATE audit_event SET action = 'REWRITTEN'")
        )

        assert state == INSUFFICIENT_PRIVILEGE_SQLSTATE
        with application_engine.connect() as connection:
            assert connection.execute(text("SELECT action FROM audit_event")).scalar_one() == (
                "ORIGINAL"
            )

    def test_a_delete_is_refused(self, application_engine: Engine) -> None:
        with application_engine.begin() as connection:
            connection.execute(text(INSERT_AUDIT_EVENT), {"action": "ORIGINAL"})

        state = refused_sqlstate(application_engine, delete(table(AUDIT_TABLE)))

        assert state == INSUFFICIENT_PRIVILEGE_SQLSTATE
        assert count_rows(application_engine, AUDIT_TABLE) == 1

    def test_a_truncate_is_refused(self, application_engine: Engine) -> None:
        """Emptying the table is the bluntest rewrite there is."""
        state = refused_sqlstate(application_engine, text("TRUNCATE TABLE audit_event"))
        assert state == INSUFFICIENT_PRIVILEGE_SQLSTATE


class TestTheApplicationRoleCannotHardDelete:
    """BR-51. Rows are released, cancelled, retired or deactivated, never removed."""

    @pytest.mark.parametrize("table_name", NEVER_DELETED_TABLES)
    def test_a_delete_is_refused_on_every_table_but_the_rate_limit_counters(
        self, application_engine: Engine, table_name: str
    ) -> None:
        state = refused_sqlstate(application_engine, delete(table(table_name)))
        assert state == INSUFFICIENT_PRIVILEGE_SQLSTATE, (
            f"{APPLICATION_ROLE} was allowed to remove rows of {table_name}, or was refused "
            f"with SQLSTATE {state} when {INSUFFICIENT_PRIVILEGE_SQLSTATE} was expected."
        )

    def test_an_expired_rate_limit_window_can_be_deleted(self, application_engine: Engine) -> None:
        """The one delete the application performs, so the one delete it is given."""
        with application_engine.begin() as connection:
            connection.execute(text(INSERT_RATE_LIMIT_WINDOW))
        with application_engine.begin() as connection:
            connection.execute(delete(table(SWEPT_TABLE)))
        assert count_rows(application_engine, SWEPT_TABLE) == 0


class TestTheApplicationRoleCanStillDoItsWork:
    """A restriction that stopped ordinary reads and writes would be no use."""

    def test_it_can_insert_update_and_read_an_ordinary_row(
        self, application_engine: Engine
    ) -> None:
        with application_engine.begin() as connection:
            connection.execute(text(INSERT_BRANCH))
            connection.execute(text("UPDATE branch SET name = 'Renamed' WHERE code = 'TST'"))
        with application_engine.connect() as connection:
            name = connection.execute(
                text("SELECT name FROM branch WHERE code = 'TST'")
            ).scalar_one()
        assert name == "Renamed"

    def test_it_can_draw_the_next_reservation_reference(self, application_engine: Engine) -> None:
        with application_engine.connect() as connection:
            value = connection.execute(
                text("SELECT nextval('reservation_reference_seq')")
            ).scalar_one()
        assert int(value) > 0

    def test_it_cannot_change_the_schema(self, application_engine: Engine) -> None:
        state = refused_sqlstate(
            application_engine, text("CREATE TABLE role_probe (id integer PRIMARY KEY)")
        )
        assert state == INSUFFICIENT_PRIVILEGE_SQLSTATE


class TestTheMigrationRoleCanBuildTheSchema:
    """The other half of the split. The role that runs migrations may run DDL."""

    def test_it_can_create_a_table_in_the_public_schema(self, migration_engine: Engine) -> None:
        """Created and rolled back in one transaction, so nothing is left behind."""
        with migration_engine.connect() as connection:
            assert connection.execute(text("SELECT current_user")).scalar_one() == MIGRATION_ROLE
            connection.execute(text("CREATE TABLE role_probe (id integer PRIMARY KEY)"))
            found = connection.execute(text("SELECT to_regclass('role_probe')")).scalar_one()
            connection.rollback()
        assert found is not None
