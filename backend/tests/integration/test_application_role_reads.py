"""The restricted role reads the two logs of the admin console, and cannot rewrite one event.

The administrator reads the audit log and the notification log through query
objects, and the API runs them on a connection signed in as `toolshed_app`.
These prove that both reads work within the grants revision 0002 gives that
role, the correlated read of the re-send's audit event included, and that one
audit event named by its number can no more be changed or removed than the
whole table can, which tests/integration/test_application_role.py proves
(BR-49, BR-50). A refusal is asserted by SQLSTATE 42501 from the driver, never
by the message.

The roles are provisioned through `scripts/provision_roles.py`, and the rows a
test reads are written by the owner, as in the other role tests.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Final

import pytest
from sqlalchemy import Engine, Executable, column, delete, func, select, table, text, update
from sqlalchemy.exc import ProgrammingError
from sqlmodel import Session

from app.application.audit_reads import AuditSearch
from app.application.notification.log import NotificationSearch
from app.domain.enums import NotificationStatus, UserRole
from app.infrastructure.audit_query import SqlAuditEventReads
from app.infrastructure.notification.log_query import SqlNotificationLog
from tests.support.admin_log_pg import committed_reservation, write_notification
from tests.support.factories import Factory
from tests.support.roles import (
    APPLICATION_ROLE,
    APPLICATION_ROLE_PASSWORD,
    INSUFFICIENT_PRIVILEGE_SQLSTATE,
    engine_as,
    provision_restricted_roles,
    sqlstate_of_refusal,
)

pytestmark = [pytest.mark.postgres, pytest.mark.usefixtures("postgres_session")]

AUDIT_TABLE: Final[str] = "audit_event"
# The audit table as the statements below name it, by the two columns they use.
AUDIT_COLUMNS: Final = table(AUDIT_TABLE, column("id"), column("action"))
INSERT_AUDIT_EVENT: Final[str] = (
    "INSERT INTO audit_event (entity_type, entity_id, action) "
    "VALUES ('branch', gen_random_uuid(), :action)"
)
QUEUED_AT: Final[datetime] = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
FIRST_PAGE: Final[int] = 1
PAGE_SIZE: Final[int] = 20
EVERY_EVENT: Final[AuditSearch] = AuditSearch(
    entity_type=None,
    entity_id=None,
    action=None,
    actor_user_id=None,
    occurred_from=None,
    occurred_before=None,
    page=FIRST_PAGE,
    page_size=PAGE_SIZE,
)
EVERY_NOTIFICATION: Final[NotificationSearch] = NotificationSearch(
    status=None, page=FIRST_PAGE, page_size=PAGE_SIZE
)


@pytest.fixture(scope="module")
def application_engine(postgres_engine: Engine, postgres_url: str) -> Iterator[Engine]:
    """Provision the roles once, and yield an engine signed in as the restricted one."""
    provision_restricted_roles(postgres_engine, postgres_url)
    engine = engine_as(postgres_url, APPLICATION_ROLE, APPLICATION_ROLE_PASSWORD)
    try:
        yield engine
    finally:
        engine.dispose()


def refused_sqlstate(engine: Engine, statement: Executable) -> str | None:
    """Run a statement that must be refused and return the SQLSTATE of the refusal."""
    with engine.connect() as connection, pytest.raises(ProgrammingError) as caught:
        connection.execute(statement)
    return sqlstate_of_refusal(caught.value)


def one_event(engine: Engine) -> int:
    """Write one audit event as the restricted role and return its number."""
    with engine.begin() as connection:
        connection.execute(text(INSERT_AUDIT_EVENT), {"action": "ORIGINAL"})
        return int(connection.execute(text("SELECT id FROM audit_event")).scalar_one())


class TestTheApplicationRoleReadsTheLogsOfTheAdminConsole:
    """The two reads of the admin console run within the grants of the restricted role."""

    def test_the_audit_log_is_read_through_its_query_object(
        self, application_engine: Engine
    ) -> None:
        with application_engine.begin() as connection:
            connection.execute(text(INSERT_AUDIT_EVENT), {"action": "ROLE_PROBE"})
        with Session(application_engine) as reader:
            found = SqlAuditEventReads(reader).page(EVERY_EVENT)
        (event,) = found.items
        assert (event.action, event.actor_user_id, event.actor_name) == ("ROLE_PROBE", None, None)

    def test_the_notification_log_and_its_re_sends_are_read_through_its_query_object(
        self, application_engine: Engine, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        staff = postgres_factory.user(role=UserRole.ADMIN)
        booked = committed_reservation(postgres_session, postgres_factory, staff)
        notification_id = write_notification(
            postgres_session, booked, queued_at=QUEUED_AT, status=NotificationStatus.FAILED
        )
        postgres_session.commit()
        with Session(application_engine) as reader:
            found = SqlNotificationLog(reader).page(EVERY_NOTIFICATION)
        assert [(entry.id, entry.resend_of) for entry in found.items] == [(notification_id, None)]


class TestTheApplicationRoleCannotRewriteOneEvent:
    """BR-49. One event named by its number is no more open to change than the table."""

    def test_one_event_cannot_be_updated_by_its_number(self, application_engine: Engine) -> None:
        event_id = one_event(application_engine)
        state = refused_sqlstate(
            application_engine,
            update(AUDIT_COLUMNS).where(AUDIT_COLUMNS.c.id == event_id).values(action="REWRITTEN"),
        )
        assert state == INSUFFICIENT_PRIVILEGE_SQLSTATE

    def test_one_event_cannot_be_deleted_by_its_number(self, application_engine: Engine) -> None:
        event_id = one_event(application_engine)
        state = refused_sqlstate(
            application_engine, delete(AUDIT_COLUMNS).where(AUDIT_COLUMNS.c.id == event_id)
        )
        assert state == INSUFFICIENT_PRIVILEGE_SQLSTATE
        statement = select(func.count()).select_from(table(AUDIT_TABLE))
        with application_engine.connect() as connection:
            assert int(connection.execute(statement).scalar_one()) == 1
