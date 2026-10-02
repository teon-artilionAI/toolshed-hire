"""A booking made through the SQL unit of work.

These run the real `SqlAlchemyUnitOfWork`, the real repositories, the real
audit log and the real outbox, against the in memory database. The transaction
is a real one, so a rollback here genuinely removes rows. The boundary itself
is pinned in test_unit_of_work.py.

Two promises are pinned. A booking whose audit event cannot be written does not
exist afterwards, in any table (BR-49). And a booking that succeeds leaves
exactly one audit event and one notification, written with it and sent after it
(BR-19).

What SQLite cannot show is two connections. That a rolled back booking is
invisible to everybody else, and that a confirmation is only sent once another
connection can see the booking, is proved on PostgreSQL in
tests/integration/test_booking_transaction.py.
"""

from __future__ import annotations

from datetime import date
from typing import Final
from uuid import UUID

import pytest
from sqlmodel import Session, select

from app.domain.enums import NotificationStatus, ReservationStatus, UserRole
from app.domain.identity import Actor
from app.domain.period import BookingPeriod
from app.infrastructure.models import (
    AssetAllocation,
    AuditEvent,
    Notification,
    Reservation,
    ReservationLine,
)
from app.infrastructure.notification import FakeEmailGateway
from app.request_context import RequestContext, bind_request_context, release_request_context
from tests.support.booking import (
    AuditWriteFailed,
    UnitOfWorkWithBrokenAudit,
    borrowing,
    command_for,
    sql_use_case,
)
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.scenarios import AllocationScenario, build_allocation_scenario

FIRST_HIRE: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 9), date(2026, 3, 12))
REQUEST_ID: Final[str] = "6f1c2b9e-3d4a-4c5b-8e7f-0a1b2c3d4e5f"
PROVIDER_FAILURE: Final[str] = "Resend answered 500 (Internal Server Error)."


@pytest.fixture
def scenario(session: Session, factory: Factory) -> AllocationScenario:
    """Return a committed branch, product model, unit and customer."""
    built = build_allocation_scenario(factory, FIRST_HIRE)
    session.commit()
    return built


def references_in(session: Session) -> set[str]:
    """Return the reference of every stored reservation."""
    return {reservation.reference for reservation in session.exec(select(Reservation)).all()}


class TestABookingThatCannotBeAuditedDoesNotHappen:
    """BR-49. The audit write fails, so the operation fails and nothing is committed."""

    def book_with_a_broken_audit_log(self, session: Session, scenario: AllocationScenario) -> None:
        """Run the use case over a unit of work whose audit log always fails."""
        use_case = sql_use_case(
            lambda: UnitOfWorkWithBrokenAudit(lambda: session, close_on_exit=False),
            FakeEmailGateway(),
            FixedClock(),
        )
        with pytest.raises(AuditWriteFailed):
            use_case.execute(command_for(scenario, FIRST_HIRE))

    def test_the_reservation_is_rolled_back(
        self, session: Session, scenario: AllocationScenario
    ) -> None:
        self.book_with_a_broken_audit_log(session, scenario)
        # The scenario builds exactly one reservation of its own.
        assert references_in(session) == {scenario.reservation.reference}

    def test_no_line_no_allocation_and_no_notification_are_left_behind(
        self, session: Session, scenario: AllocationScenario
    ) -> None:
        self.book_with_a_broken_audit_log(session, scenario)
        assert [line.id for line in session.exec(select(ReservationLine)).all()] == [
            scenario.line.id
        ]
        assert session.exec(select(AssetAllocation)).all() == []
        assert session.exec(select(Notification)).all() == []
        assert session.exec(select(AuditEvent)).all() == []

    def test_the_unit_can_be_booked_once_the_audit_log_is_back(
        self, session: Session, scenario: AllocationScenario
    ) -> None:
        self.book_with_a_broken_audit_log(session, scenario)
        use_case = sql_use_case(borrowing(session), FakeEmailGateway(), FixedClock())
        view = use_case.execute(command_for(scenario, FIRST_HIRE))
        assert [item.asset_tag for item in view.allocated] == [scenario.asset.asset_tag]


class TestASuccessfulBookingLeavesExactlyOneAuditEvent:
    """Who did it, in what role, to which reservation, during which request."""

    def test_the_event_names_the_action_the_actor_the_role_and_the_request(
        self, session: Session, scenario: AllocationScenario, factory: Factory
    ) -> None:
        assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=scenario.branch)
        session.commit()
        actor = Actor(user_id=assistant.id, role=UserRole.COUNTER_STAFF)
        use_case = sql_use_case(borrowing(session), FakeEmailGateway(), FixedClock())

        token = bind_request_context(RequestContext(request_id=REQUEST_ID))
        try:
            view = use_case.execute(command_for(scenario, FIRST_HIRE, actor=actor))
        finally:
            release_request_context(token)

        (event,) = session.exec(select(AuditEvent)).all()
        assert event.action == "reservation.held"
        assert event.entity_type == "reservation"
        assert event.entity_id == view.reservation_id
        assert event.actor_user_id == assistant.id
        assert event.actor_role is UserRole.COUNTER_STAFF
        assert event.request_id == UUID(REQUEST_ID)
        assert event.before_state is None
        assert event.after_state is not None
        assert event.after_state["status"] == ReservationStatus.HELD.value
        assert event.after_state["asset_tags"] == [scenario.asset.asset_tag]

    def test_the_event_keeps_the_role_held_at_the_time_after_a_later_change(
        self, session: Session, scenario: AllocationScenario
    ) -> None:
        use_case = sql_use_case(borrowing(session), FakeEmailGateway(), FixedClock())
        use_case.execute(command_for(scenario, FIRST_HIRE))
        scenario.customer.role = UserRole.ADMIN
        session.add(scenario.customer)
        session.commit()
        (event,) = session.exec(select(AuditEvent)).all()
        assert event.actor_role is UserRole.CUSTOMER


class TestTheOutboxRow:
    """BR-19. Queued with the booking, then sent, and the outcome written back."""

    def test_a_delivered_confirmation_is_sent_with_the_provider_id(
        self, session: Session, scenario: AllocationScenario
    ) -> None:
        gateway = FakeEmailGateway()
        use_case = sql_use_case(borrowing(session), gateway, FixedClock())
        view = use_case.execute(command_for(scenario, FIRST_HIRE))

        (notification,) = session.exec(select(Notification)).all()
        assert notification.reservation_id == view.reservation_id
        assert notification.recipient_email == scenario.customer.email
        assert notification.status is NotificationStatus.SENT
        assert notification.provider == "resend"
        assert notification.provider_message_id == "fake-message-1"
        assert notification.sent_at is not None
        assert notification.attempts == 1
        (message,) = gateway.sent_to(scenario.customer.email)
        assert view.reference in message.text_body
        assert message.idempotency_key == f"notification-{notification.id}"

    def test_a_provider_failure_marks_the_row_failed_and_leaves_the_booking_alone(
        self, session: Session, scenario: AllocationScenario
    ) -> None:
        gateway = FakeEmailGateway(PROVIDER_FAILURE)
        use_case = sql_use_case(borrowing(session), gateway, FixedClock())
        view = use_case.execute(command_for(scenario, FIRST_HIRE))

        (notification,) = session.exec(select(Notification)).all()
        assert notification.status is NotificationStatus.FAILED
        assert notification.last_error == PROVIDER_FAILURE
        assert notification.sent_at is None
        assert notification.attempts == 1

        reservation = session.get(Reservation, view.reservation_id)
        assert reservation is not None
        assert reservation.status is ReservationStatus.HELD
        (allocation,) = session.exec(select(AssetAllocation)).all()
        assert allocation.released_at is None
        assert len(session.exec(select(AuditEvent)).all()) == 1

    def test_recording_an_outcome_for_a_notification_that_was_never_queued_is_refused(
        self, session: Session, scenario: AllocationScenario
    ) -> None:
        with (
            borrowing(session)() as uow,
            pytest.raises(LookupError, match="is not in the outbox"),
        ):
            uow.notifications.mark_failed(scenario.reservation.id, PROVIDER_FAILURE)
