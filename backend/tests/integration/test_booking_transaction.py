"""One booking, one transaction, proved from a second connection.

A booking writes a reservation, a line, an allocation for every unit, an audit
event and a queued notification. BR-09 and BR-49 say those commit together or
not at all.

An in memory test can show that the code asks for that. Only a real database
can show that it happens, because the claim is about what another connection
can see. So the use case here runs in a unit of work that opens its own
connection, and every assertion is made through a different one. A row that
connection can read has been committed. A row it cannot read never was.

The audit failure in this file is a genuine one. The audit log is handed an
action name longer than the column, PostgreSQL refuses the insert, and the
booking that was already written in the same transaction goes with it.

What happens to the notification after the commit is in
test_notification_outbox.py.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from ipaddress import ip_address
from typing import Final, Self
from uuid import UUID

import pytest
from sqlalchemy import Engine, func
from sqlalchemy.exc import DataError
from sqlmodel import Session, select

from app.domain.audit import AuditEvent as DomainAuditEvent
from app.domain.enums import UserRole
from app.domain.identity import Actor
from app.domain.period import BookingPeriod
from app.infrastructure.audit import SqlAuditLog
from app.infrastructure.models import (
    AssetAllocation,
    AuditEvent,
    Notification,
    Reservation,
    ReservationLine,
)
from app.infrastructure.notification import FakeEmailGateway
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.request_context import RequestContext, bind_request_context, release_request_context
from tests.support.booking import (
    CommitFailed,
    UnitOfWorkThatCannotCommit,
    command_for,
    opening,
    sql_use_case,
)
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.pg import count_active_allocations
from tests.support.scenarios import AllocationScenario, build_allocation_scenario

pytestmark = pytest.mark.postgres

FIRST_HIRE: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 9), date(2026, 3, 12))
REQUEST_ID: Final[str] = "6f1c2b9e-3d4a-4c5b-8e7f-0a1b2c3d4e5f"
# From the block reserved for documentation, so it is nobody's real address.
CLIENT_ADDRESS: Final[str] = "203.0.113.9"
ACTION_COLUMN_WIDTH: Final[int] = 60
OCCURRED_AT: Final[datetime] = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
# The tables a booking writes to, with the rows the scenario itself puts in each.
ROWS_BEFORE_ANY_BOOKING: Final[dict[str, int]] = {
    "reservation": 1,
    "reservation_line": 1,
    "asset_allocation": 0,
    "audit_event": 0,
    "notification": 0,
}


class OverlongActionAuditLog(SqlAuditLog):
    """The real audit log, handed an action name the column cannot hold."""

    def record(self, event: DomainAuditEvent) -> None:
        """Write the event with an action one character longer than the column."""
        super().record(replace(event, action="x" * (ACTION_COLUMN_WIDTH + 1)))


class UnitOfWorkWhoseAuditInsertIsRefused(SqlAlchemyUnitOfWork):
    """The real unit of work, with the audit log above over the same session."""

    def __enter__(self) -> Self:
        """Open the real transaction, then swap in the audit log that will be refused."""
        entered = super().__enter__()
        self.audit = OverlongActionAuditLog(self._open_session())
        return entered


@pytest.fixture
def scenario(postgres_session: Session, postgres_factory: Factory) -> AllocationScenario:
    """Return a committed branch, product model, unit and customer."""
    built = build_allocation_scenario(postgres_factory, FIRST_HIRE)
    postgres_session.commit()
    return built


def row_counts(session: Session) -> dict[str, int]:
    """Return how many committed rows each table a booking writes to holds."""
    session.rollback()
    tables = (Reservation, ReservationLine, AssetAllocation, AuditEvent, Notification)
    return {
        str(table.__tablename__): int(session.exec(select(func.count()).select_from(table)).one())
        for table in tables
    }


class TestABookingCommitsEverythingTogether:
    """The reservation, its line, its allocation, its audit event and its notification."""

    def test_one_booking_adds_one_row_to_each_table_it_writes(
        self, postgres_engine: Engine, postgres_session: Session, scenario: AllocationScenario
    ) -> None:
        use_case = sql_use_case(opening(postgres_engine), FakeEmailGateway(), FixedClock())
        use_case.execute(command_for(scenario, FIRST_HIRE))
        assert row_counts(postgres_session) == {
            table: count + 1 for table, count in ROWS_BEFORE_ANY_BOOKING.items()
        }

    def test_the_audit_event_is_stored_with_the_actor_the_role_the_request_and_the_address(
        self,
        postgres_engine: Engine,
        postgres_session: Session,
        postgres_factory: Factory,
        scenario: AllocationScenario,
    ) -> None:
        assistant = postgres_factory.user(role=UserRole.COUNTER_STAFF, branch=scenario.branch)
        postgres_session.commit()
        actor = Actor(user_id=assistant.id, role=UserRole.COUNTER_STAFF)
        use_case = sql_use_case(opening(postgres_engine), FakeEmailGateway(), FixedClock())

        token = bind_request_context(
            RequestContext(request_id=REQUEST_ID, client_address=ip_address(CLIENT_ADDRESS))
        )
        try:
            view = use_case.execute(command_for(scenario, FIRST_HIRE, actor=actor))
        finally:
            release_request_context(token)

        (event,) = postgres_session.exec(select(AuditEvent)).all()
        assert event.action == "reservation.held"
        assert event.entity_type == "reservation"
        assert event.entity_id == view.reservation_id
        assert event.actor_user_id == assistant.id
        assert event.actor_role is UserRole.COUNTER_STAFF
        assert event.request_id == UUID(REQUEST_ID)
        assert event.ip_address == ip_address(CLIENT_ADDRESS)
        assert event.before_state is None
        assert event.after_state == {
            "status": "HELD",
            "reference": view.reference,
            "customer_profile_id": str(scenario.profile.id),
            "branch_id": str(scenario.branch.id),
            "start_date": "2026-03-09",
            "end_date": "2026-03-12",
            "product_model_id": str(scenario.product_model.id),
            "quantity": 1,
            "asset_tags": [scenario.asset.asset_tag],
        }

    def test_the_event_is_timed_by_the_clock_the_use_case_was_given(
        self, postgres_engine: Engine, postgres_session: Session, scenario: AllocationScenario
    ) -> None:
        clock = FixedClock(OCCURRED_AT)
        use_case = sql_use_case(opening(postgres_engine), FakeEmailGateway(), clock)
        use_case.execute(command_for(scenario, FIRST_HIRE))
        (event,) = postgres_session.exec(select(AuditEvent)).all()
        assert event.occurred_at == OCCURRED_AT


class TestABookingThatFailsLeavesNothingBehind:
    """Whatever was written before the failure is rolled back with it."""

    def test_an_audit_insert_the_database_refuses_rolls_the_whole_booking_back(
        self, postgres_engine: Engine, postgres_session: Session, scenario: AllocationScenario
    ) -> None:
        use_case = sql_use_case(
            opening(postgres_engine, UnitOfWorkWhoseAuditInsertIsRefused),
            FakeEmailGateway(),
            FixedClock(),
        )
        with pytest.raises(DataError):
            use_case.execute(command_for(scenario, FIRST_HIRE))
        assert row_counts(postgres_session) == ROWS_BEFORE_ANY_BOOKING

    def test_a_refused_audit_insert_sends_no_email(
        self, postgres_engine: Engine, scenario: AllocationScenario
    ) -> None:
        gateway = FakeEmailGateway()
        use_case = sql_use_case(
            opening(postgres_engine, UnitOfWorkWhoseAuditInsertIsRefused),
            gateway,
            FixedClock(),
        )
        with pytest.raises(DataError):
            use_case.execute(command_for(scenario, FIRST_HIRE))
        assert gateway.sent == []

    def test_the_unit_is_free_again_once_the_failed_booking_has_rolled_back(
        self, postgres_engine: Engine, postgres_session: Session, scenario: AllocationScenario
    ) -> None:
        """The row lock and the allocation both go with the transaction."""
        broken = sql_use_case(
            opening(postgres_engine, UnitOfWorkWhoseAuditInsertIsRefused),
            FakeEmailGateway(),
            FixedClock(),
        )
        with pytest.raises(DataError):
            broken.execute(command_for(scenario, FIRST_HIRE))
        assert count_active_allocations(postgres_session, scenario.asset.id) == 0

        working = sql_use_case(opening(postgres_engine), FakeEmailGateway(), FixedClock())
        view = working.execute(command_for(scenario, FIRST_HIRE))
        assert [item.asset_tag for item in view.allocated] == [scenario.asset.asset_tag]

    def test_a_failure_after_the_notification_was_queued_keeps_neither_it_nor_the_booking(
        self, postgres_engine: Engine, postgres_session: Session, scenario: AllocationScenario
    ) -> None:
        """The outbox row is in the booking's transaction, so it shares the booking's fate."""
        gateway = FakeEmailGateway()
        use_case = sql_use_case(
            opening(postgres_engine, UnitOfWorkThatCannotCommit), gateway, FixedClock()
        )
        with pytest.raises(CommitFailed):
            use_case.execute(command_for(scenario, FIRST_HIRE))
        assert row_counts(postgres_session) == ROWS_BEFORE_ANY_BOOKING
        assert gateway.sent == []
