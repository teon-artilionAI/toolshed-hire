"""Each filter of the audit log, and each order of the notification log, stands on its index.

An administrator reads both logs newest first, narrowed by filters (FR-26,
US-36). Each filter of the audit log, and the two orders of the notification
log, are explained with sequential scans switched off, which shows whether the
condition matches the index it was written for, on a log of a few hundred
events and a run of notifications that have been analysed. An empty table
gives the planner no figures, and it then takes any index as good as any
other. Every value in an explained statement is bound, except the status of a
notification, which the query object writes as the literal the partial index
is filtered on.

That a page takes the same number of statements however long the logs grow is
in tests/integration/test_admin_log_reads.py.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlmodel import Session

from app.domain.enums import NotificationStatus, UserRole
from app.infrastructure.schema_ddl import (
    AUDIT_ACTION_INDEX,
    AUDIT_ACTOR_INDEX,
    AUDIT_ENTITY_ID_INDEX,
    AUDIT_ENTITY_INDEX,
    AUDIT_OCCURRED_INDEX,
    NOTIFICATION_FAILED_INDEX,
    NOTIFICATION_QUEUED_INDEX,
)
from tests.support.admin_log_pg import (
    CONFIRMED,
    EXPIRED,
    ONE_MINUTE,
    RESENT,
    RESERVATION_ENTITY,
    START,
    WAIVED,
    committed_reservation,
    write_event,
    write_notification,
)
from tests.support.factories import Factory

pytestmark = pytest.mark.postgres

EXPLAIN_PREFIX: Final[str] = "EXPLAIN "
ONE_HOUR: Final[timedelta] = timedelta(hours=1)
BUSY_EVENTS: Final[int] = 400
BUSY_NOTIFICATIONS: Final[int] = 60
# Every tenth notification of the run failed, and every third event is the sweep's.
FAILED_EVERY: Final[int] = 10
SWEEP_EVERY: Final[int] = 3

ENTITY_AND_KEY: Final[str] = (
    "SELECT id FROM audit_event WHERE entity_type = :entity_type AND entity_id = :entity_id"
)
KEY_ALONE: Final[str] = "SELECT id FROM audit_event WHERE entity_id = :entity_id"
# The query object adds the second condition for any action but a change of
# status, as a literal, so the partial index of an action can be matched.
ONE_ACTION: Final[str] = (
    "SELECT id FROM audit_event WHERE action = :action AND action <> 'asset.status_changed'"
)
ONE_ACTOR: Final[str] = "SELECT id FROM audit_event WHERE actor_user_id = :actor"
A_SPAN: Final[str] = (
    "SELECT id FROM audit_event WHERE occurred_at >= :starts AND occurred_at < :ends"
)
NEWEST_EVENTS: Final[str] = (
    "SELECT id FROM audit_event ORDER BY occurred_at DESC, id DESC LIMIT 20"
)
FAILED_SENDS: Final[str] = (
    "SELECT id FROM notification WHERE status = 'FAILED' ORDER BY queued_at DESC, id DESC "
    "LIMIT 20"
)
NEWEST_NOTIFICATIONS: Final[str] = (
    "SELECT id FROM notification ORDER BY queued_at DESC, id DESC LIMIT 20"
)


@pytest.fixture
def busy_logs(postgres_session: Session, postgres_factory: Factory) -> None:
    """Commit a log of events spread over days and a run of notifications, and analyse both."""
    administrator = postgres_factory.user(role=UserRole.ADMIN)
    reservation = committed_reservation(postgres_session, postgres_factory, administrator)
    actions = (CONFIRMED, EXPIRED, WAIVED, RESENT)
    for number in range(BUSY_EVENTS):
        write_event(
            postgres_session,
            occurred_at=START + number * ONE_HOUR,
            action=actions[number % len(actions)],
            entity_type=RESERVATION_ENTITY,
            entity_id=uuid4(),
            actor=administrator if number % SWEEP_EVERY else None,
        )
    for number in range(BUSY_NOTIFICATIONS):
        failed = number % FAILED_EVERY == 0
        write_notification(
            postgres_session,
            reservation,
            queued_at=START + number * ONE_HOUR,
            status=NotificationStatus.FAILED if failed else NotificationStatus.SENT,
        )
    postgres_session.commit()
    postgres_session.execute(text("ANALYZE audit_event"))
    postgres_session.execute(text("ANALYZE notification"))
    postgres_session.commit()


def plan_of(session: Session, statement: str, **params: object) -> str:
    """Return the plan of a statement with sequential scans switched off, to see the choice."""
    session.execute(text("SET LOCAL enable_seqscan = off"))
    plan = session.execute(text(EXPLAIN_PREFIX + statement), params).all()
    return "\n".join(str(row[0]) for row in plan)


@pytest.mark.usefixtures("busy_logs")
class TestEachFilterStandsOnItsIndex:
    """The planner can answer each filter of the audit log from the index written for it."""

    def test_a_kind_of_record_and_its_key_are_found_through_the_entity_indexes(
        self, postgres_session: Session
    ) -> None:
        plan = plan_of(
            postgres_session, ENTITY_AND_KEY, entity_type=RESERVATION_ENTITY, entity_id=uuid4()
        )
        assert AUDIT_ENTITY_INDEX in plan or AUDIT_ENTITY_ID_INDEX in plan, plan

    def test_a_key_alone_is_found_through_the_index_that_leads_with_it(
        self, postgres_session: Session
    ) -> None:
        plan = plan_of(postgres_session, KEY_ALONE, entity_id=uuid4())
        assert AUDIT_ENTITY_ID_INDEX in plan, plan

    def test_an_action_is_found_through_its_index(self, postgres_session: Session) -> None:
        plan = plan_of(postgres_session, ONE_ACTION, action=WAIVED)
        assert AUDIT_ACTION_INDEX in plan, plan

    def test_an_actor_is_found_through_the_index_of_events_that_have_one(
        self, postgres_session: Session
    ) -> None:
        plan = plan_of(postgres_session, ONE_ACTOR, actor=uuid4())
        assert AUDIT_ACTOR_INDEX in plan, plan

    def test_a_span_of_days_is_found_through_when_the_events_happened(
        self, postgres_session: Session
    ) -> None:
        plan = plan_of(postgres_session, A_SPAN, starts=START, ends=START + ONE_MINUTE)
        assert AUDIT_OCCURRED_INDEX in plan, plan

    def test_the_newest_page_with_no_filter_is_read_off_the_end_of_the_index(
        self, postgres_session: Session
    ) -> None:
        plan = plan_of(postgres_session, NEWEST_EVENTS)
        assert AUDIT_OCCURRED_INDEX in plan, plan


@pytest.mark.usefixtures("busy_logs")
class TestEachOrderOfTheNotificationLogStandsOnItsIndex:
    """The failed sends come from the partial index, and the whole log from the index on time."""

    def test_the_failed_sends_are_read_through_the_partial_index_that_holds_them(
        self, postgres_session: Session
    ) -> None:
        plan = plan_of(postgres_session, FAILED_SENDS)
        assert NOTIFICATION_FAILED_INDEX in plan, plan

    def test_every_notification_is_read_newest_first_through_its_index(
        self, postgres_session: Session
    ) -> None:
        plan = plan_of(postgres_session, NEWEST_NOTIFICATIONS)
        assert NOTIFICATION_QUEUED_INDEX in plan, plan
