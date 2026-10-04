"""The audit log and the notification log read on PostgreSQL, in a bounded number of statements.

An administrator reads both logs a page at a time, newest first (FR-26,
US-36). Each page is counted in statements with a few rows and again with
many more, and the count does not move. That each filter stands on its index
is in tests/integration/test_admin_log_indexes.py.

The reads themselves are checked as well. The newest event comes first, the
account that acted is named, an event the sweep wrote has no actor, the days
of a search are business days in Cape Town with both ends included, and the
notification that re-sends a failed one names it through the audit event its
re-send wrote, because the table has no column for it. The rows are written
by tests/support/admin_log_pg.py.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Final
from uuid import uuid4

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from app.application.audit_reads import AuditLogRequest, AuditSearch, ReadAuditLog
from app.application.notification.log import NotificationSearch
from app.domain.enums import NotificationStatus, UserRole
from app.domain.identity import Actor
from app.infrastructure.audit_query import SqlAuditEventReads
from app.infrastructure.models import Reservation, UserAccount
from app.infrastructure.notification.log_query import SqlNotificationLog
from tests.support.admin_log_pg import (
    CONFIRMED,
    EXPIRED,
    FIRST_PAGE,
    NOTIFICATION_ENTITY,
    ONE_MINUTE,
    PAGE_SIZE,
    RESENT,
    RESERVATION_ENTITY,
    START,
    committed_reservation,
    events_of,
    every_event,
    write_event,
    write_notification,
)
from tests.support.factories import Factory
from tests.support.statements import recorded_statements

pytestmark = pytest.mark.postgres

PAGE_STATEMENTS: Final[int] = 2
ONE_STATEMENT: Final[int] = 1
MORE_ROWS: Final[int] = 60
ACTOR_NAME: Final[str] = "Wesley Adonis"
# Half past eleven at night in Cape Town on the second, and ten past midnight
# on the third, which is still the second in UTC.
LATE_ON_THE_SECOND: Final[datetime] = datetime(2026, 3, 2, 21, 30, tzinfo=UTC)
EARLY_ON_THE_THIRD: Final[datetime] = datetime(2026, 3, 2, 22, 10, tzinfo=UTC)
THE_SECOND: Final[date] = date(2026, 3, 2)


@pytest.fixture
def administrator(postgres_session: Session, postgres_factory: Factory) -> UserAccount:
    """Return a committed administrator."""
    account = postgres_factory.user(role=UserRole.ADMIN)
    postgres_session.commit()
    return account


@pytest.fixture
def reservation(
    postgres_session: Session, postgres_factory: Factory, administrator: UserAccount
) -> Reservation:
    """Return a committed reservation the notifications are about."""
    return committed_reservation(postgres_session, postgres_factory, administrator)


def counted_audit_page(engine: Engine, search: AuditSearch) -> int:
    """Return how many statements one page of the audit log sent."""
    with Session(engine) as reader, recorded_statements(engine) as statements:
        SqlAuditEventReads(reader).page(search)
    return len(statements)


class TestTheStatementsDoNotGrowWithTheLog:
    """Two statements a page and one for a notification, however long the logs grow."""

    def test_a_page_of_the_audit_log_is_two_statements_with_few_events_or_many(
        self, postgres_engine: Engine, postgres_session: Session, administrator: UserAccount
    ) -> None:
        events_of(postgres_session, administrator, 3)
        actor_id = administrator.id
        few = counted_audit_page(postgres_engine, every_event())
        events_of(postgres_session, administrator, MORE_ROWS, offset=3)
        many = counted_audit_page(postgres_engine, every_event())
        by_actor = counted_audit_page(postgres_engine, every_event(actor_user_id=actor_id))
        assert few == many == by_actor == PAGE_STATEMENTS

    def test_a_page_of_the_notification_log_is_two_statements_and_one_is_one(
        self, postgres_engine: Engine, postgres_session: Session, reservation: Reservation
    ) -> None:
        first = write_notification(
            postgres_session, reservation, queued_at=START, status=NotificationStatus.FAILED
        )
        postgres_session.commit()
        search = NotificationSearch(status=None, page=FIRST_PAGE, page_size=PAGE_SIZE)
        with Session(postgres_engine) as reader, recorded_statements(postgres_engine) as few:
            SqlNotificationLog(reader).page(search)
        for number in range(MORE_ROWS):
            write_notification(
                postgres_session,
                reservation,
                queued_at=START + (number + 1) * ONE_MINUTE,
                status=NotificationStatus.SENT,
            )
        postgres_session.commit()
        with Session(postgres_engine) as reader, recorded_statements(postgres_engine) as many:
            found = SqlNotificationLog(reader).page(search)
        with Session(postgres_engine) as reader, recorded_statements(postgres_engine) as one:
            SqlNotificationLog(reader).one(first)
        assert len(few) == len(many) == PAGE_STATEMENTS
        assert len(one) == ONE_STATEMENT
        assert (len(found.items), found.total) == (PAGE_SIZE, MORE_ROWS + 1)


class TestTheAuditLogAsItIsRead:
    """Newest first, the actor named, the sweep anonymous, and the days of Cape Town."""

    def test_the_newest_event_comes_first_and_names_its_actor(
        self, postgres_engine: Engine, postgres_session: Session, administrator: UserAccount
    ) -> None:
        events_of(postgres_session, administrator, 3)
        actor_id = administrator.id
        with Session(postgres_engine) as reader:
            found = SqlAuditEventReads(reader).page(every_event())
        newest, middle, oldest = found.items
        assert newest.occurred_at > middle.occurred_at > oldest.occurred_at
        assert (newest.actor_user_id, newest.actor_name, newest.actor_role) == (
            actor_id, ACTOR_NAME, UserRole.ADMIN
        )
        assert (oldest.action, oldest.actor_user_id, oldest.actor_name, oldest.actor_role) == (
            EXPIRED, None, None, None
        )
        assert (oldest.before_state, oldest.after_state) == ({}, {})

    def test_the_filters_narrow_the_log_and_the_total_counts_what_matches(
        self, postgres_engine: Engine, postgres_session: Session, administrator: UserAccount
    ) -> None:
        events_of(postgres_session, administrator, 6)
        actor_id = administrator.id
        with Session(postgres_engine) as reader:
            reads = SqlAuditEventReads(reader)
            by_actor = reads.page(every_event(actor_user_id=actor_id))
            by_action = reads.page(every_event(action=EXPIRED))
            one = by_action.items[0]
            by_key = reads.page(every_event(entity_id=one.entity_id))
        assert by_actor.total == 4
        assert {entry.action for entry in by_action.items} == {EXPIRED}
        assert by_action.total == 2
        assert [entry.id for entry in by_key.items] == [one.id]

    def test_a_span_of_days_includes_both_ends_in_business_time(
        self, postgres_engine: Engine, postgres_session: Session, administrator: UserAccount
    ) -> None:
        late = write_event(
            postgres_session,
            occurred_at=LATE_ON_THE_SECOND,
            action=CONFIRMED,
            entity_type=RESERVATION_ENTITY,
            entity_id=uuid4(),
        )
        write_event(
            postgres_session,
            occurred_at=EARLY_ON_THE_THIRD,
            action=CONFIRMED,
            entity_type=RESERVATION_ENTITY,
            entity_id=uuid4(),
        )
        postgres_session.commit()
        reader_actor = Actor(user_id=administrator.id, role=UserRole.ADMIN)
        with Session(postgres_engine) as reader:
            found = ReadAuditLog(SqlAuditEventReads(reader)).page(
                AuditLogRequest(
                    actor=reader_actor,
                    entity_type=None,
                    entity_id=None,
                    action=None,
                    actor_user_id=None,
                    from_day=THE_SECOND,
                    to_day=THE_SECOND,
                    page=FIRST_PAGE,
                    page_size=PAGE_SIZE,
                )
            )
        assert [entry.id for entry in found.items] == [late]


class TestAReSendNamesTheNotificationItSendsAgain:
    """`resendOf` is read from the audit event of the re-send, newest first."""

    def test_the_new_notification_names_the_failed_one_and_the_failed_one_names_none(
        self, postgres_engine: Engine, postgres_session: Session, reservation: Reservation
    ) -> None:
        failed = write_notification(
            postgres_session, reservation, queued_at=START, status=NotificationStatus.FAILED
        )
        again = write_notification(
            postgres_session,
            reservation,
            queued_at=START + ONE_MINUTE,
            status=NotificationStatus.SENT,
        )
        write_event(
            postgres_session,
            occurred_at=START + ONE_MINUTE,
            action=RESENT,
            entity_type=NOTIFICATION_ENTITY,
            entity_id=again,
            after_state={"resend_of": str(failed), "status": "QUEUED"},
        )
        postgres_session.commit()
        reference = reservation.reference
        with Session(postgres_engine) as reader:
            log = SqlNotificationLog(reader)
            page = log.page(NotificationSearch(status=None, page=FIRST_PAGE, page_size=PAGE_SIZE))
            failed_only = log.page(
                NotificationSearch(
                    status=NotificationStatus.FAILED, page=FIRST_PAGE, page_size=PAGE_SIZE
                )
            )
            entry = log.one(again)
            missing = log.one(uuid4())
        assert [(item.id, item.resend_of) for item in page.items] == [
            (again, failed), (failed, None)
        ]
        assert [item.id for item in failed_only.items] == [failed]
        assert entry is not None and entry.resend_of == failed
        assert (entry.reservation_reference, entry.sent_at) == (reference, START + ONE_MINUTE)
        assert missing is None
