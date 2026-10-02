"""The moves of a reservation made through the SQL unit of work.

These run the real `SqlAlchemyUnitOfWork`, the real repositories, the real
audit log and the real outbox, against the in memory database. The transaction
is a real one, so a rollback here genuinely removes rows. The boundary itself
is pinned in test_unit_of_work.py.

Three promises are pinned. A move whose audit event cannot be written does not
happen, in any table (BR-49). A move that succeeds leaves exactly one audit
event. And a confirmation leaves one notification, written with it and sent
after it (BR-19), where a hold leaves none.

What SQLite cannot show is two connections. That a rolled back move is
invisible to everybody else, and that a confirmation is only sent once another
connection can see it, is proved on PostgreSQL in
tests/integration/test_booking_transaction.py.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

import pytest
from sqlmodel import Session, col, select

from app.domain.enums import NotificationStatus, ReservationStatus, UserRole
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
    SqlDesk,
    UnitOfWorkWithBrokenAudit,
    actor_of,
    borrowing,
    cancellation_of,
    customer_of,
    draft_command,
    move_on,
    sql_desk,
)
from tests.support.booking_api import BookingWorld, build_booking_world
from tests.support.clock import FixedClock
from tests.support.factories import Factory

REQUEST_ID: Final[str] = "6f1c2b9e-3d4a-4c5b-8e7f-0a1b2c3d4e5f"
PROVIDER_FAILURE: Final[str] = "Resend answered 500 (Internal Server Error)."


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed branch, product model, unit and customer."""
    built = build_booking_world(factory)
    session.commit()
    return built


@pytest.fixture
def desk(session: Session) -> SqlDesk:
    """Return the booking use cases over the session of the test."""
    return sql_desk(borrowing(session), FakeEmailGateway(), FixedClock())


@pytest.fixture
def without_an_audit_log(session: Session) -> SqlDesk:
    """Return the booking use cases over a unit of work whose audit log always fails."""
    return sql_desk(
        lambda: UnitOfWorkWithBrokenAudit(lambda: session, close_on_exit=False),
        FakeEmailGateway(),
        FixedClock(),
    )


def actions_in(session: Session) -> list[str]:
    """Return the action of every audit event, in the order it was written."""
    return [
        event.action for event in session.exec(select(AuditEvent).order_by(col(AuditEvent.id)))
    ]


def status_of(session: Session, reservation_id: UUID) -> ReservationStatus:
    """Return the stored status of one reservation, read again from the database."""
    session.expire_all()
    row = session.get(Reservation, reservation_id)
    assert row is not None
    return row.status


class TestAMoveThatCannotBeAuditedDoesNotHappen:
    """BR-49. The audit write fails, so the operation fails and nothing is committed."""

    def test_a_draft_is_rolled_back_with_its_lines(
        self, session: Session, world: BookingWorld, without_an_audit_log: SqlDesk
    ) -> None:
        with pytest.raises(AuditWriteFailed):
            without_an_audit_log.drafted(draft_command(world))
        assert session.exec(select(Reservation)).all() == []
        assert session.exec(select(ReservationLine)).all() == []

    def test_a_hold_is_rolled_back_with_its_allocations(
        self, session: Session, world: BookingWorld, desk: SqlDesk, without_an_audit_log: SqlDesk
    ) -> None:
        customer = customer_of(world)
        draft = desk.drafted(draft_command(world))
        with pytest.raises(AuditWriteFailed):
            without_an_audit_log.hold.execute(move_on(draft, customer))
        assert session.exec(select(AssetAllocation)).all() == []
        assert status_of(session, draft.detail.id) is ReservationStatus.DRAFT

    def test_the_unit_can_be_held_once_the_audit_log_is_back(
        self, session: Session, world: BookingWorld, desk: SqlDesk, without_an_audit_log: SqlDesk
    ) -> None:
        customer = customer_of(world)
        asset_id = world.assets[0].id
        draft = desk.drafted(draft_command(world))
        with pytest.raises(AuditWriteFailed):
            without_an_audit_log.hold.execute(move_on(draft, customer))
        held = desk.hold.execute(move_on(draft, customer))
        assert held.detail.lines[0].allocated_count == 1
        (allocation,) = session.exec(select(AssetAllocation)).all()
        assert allocation.asset_id == asset_id

    def test_a_confirmation_is_rolled_back_with_its_notification(
        self, session: Session, world: BookingWorld, desk: SqlDesk, without_an_audit_log: SqlDesk
    ) -> None:
        customer = customer_of(world)
        held = desk.held(draft_command(world))
        with pytest.raises(AuditWriteFailed):
            without_an_audit_log.confirm.execute(move_on(held, customer))
        assert session.exec(select(Notification)).all() == []
        assert status_of(session, held.detail.id) is ReservationStatus.HELD

    def test_a_cancellation_is_rolled_back_and_the_units_stay_held(
        self, session: Session, world: BookingWorld, desk: SqlDesk, without_an_audit_log: SqlDesk
    ) -> None:
        customer = customer_of(world)
        held = desk.held(draft_command(world))
        with pytest.raises(AuditWriteFailed):
            without_an_audit_log.cancel.execute(cancellation_of(held, customer))
        assert status_of(session, held.detail.id) is ReservationStatus.HELD
        (allocation,) = session.exec(select(AssetAllocation)).all()
        assert allocation.released_at is None


class TestEachMoveLeavesExactlyOneAuditEvent:
    """Who did it, in what role, to which reservation, during which request."""

    def test_the_moves_of_one_reservation_are_recorded_in_order(
        self, session: Session, world: BookingWorld, desk: SqlDesk
    ) -> None:
        customer = customer_of(world)
        confirmed = desk.confirmed(draft_command(world))
        desk.cancel.execute(cancellation_of(confirmed, customer))
        assert actions_in(session) == [
            "reservation.created",
            "reservation.held",
            "reservation.confirmed",
            "reservation.cancelled",
        ]

    def test_the_event_names_the_actor_the_role_the_request_and_the_units(
        self, session: Session, world: BookingWorld, desk: SqlDesk, factory: Factory
    ) -> None:
        assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
        session.commit()
        actor = actor_of(assistant)
        tag = world.assets[0].asset_tag
        draft = desk.drafted(
            draft_command(world, actor=actor, customer_profile_id=world.profile.id)
        )

        token = bind_request_context(RequestContext(request_id=REQUEST_ID))
        try:
            held = desk.hold.execute(move_on(draft, actor))
        finally:
            release_request_context(token)

        event = session.exec(select(AuditEvent).order_by(col(AuditEvent.id))).all()[-1]
        assert event.action == "reservation.held"
        assert event.entity_type == "reservation"
        assert event.entity_id == held.detail.id
        assert event.actor_user_id == actor.user_id
        assert event.actor_role is UserRole.COUNTER_STAFF
        assert event.request_id == UUID(REQUEST_ID)
        assert event.before_state is not None
        assert event.before_state["status"] == ReservationStatus.DRAFT.value
        assert event.after_state is not None
        assert event.after_state["status"] == ReservationStatus.HELD.value
        assert event.after_state["asset_tags"] == [tag]

    def test_the_event_keeps_the_role_held_at_the_time_after_a_later_change(
        self, session: Session, world: BookingWorld, desk: SqlDesk
    ) -> None:
        desk.drafted(draft_command(world))
        world.customer.role = UserRole.ADMIN
        session.add(world.customer)
        session.commit()
        (event,) = session.exec(select(AuditEvent)).all()
        assert event.actor_role is UserRole.CUSTOMER


class TestTheOutboxRow:
    """BR-19. Queued with the confirmation, then sent, and the outcome written back."""

    def test_a_hold_writes_no_outbox_row(
        self, session: Session, world: BookingWorld, desk: SqlDesk
    ) -> None:
        desk.held(draft_command(world))
        assert session.exec(select(Notification)).all() == []

    def test_a_delivered_confirmation_is_sent_with_the_provider_id(
        self, session: Session, world: BookingWorld
    ) -> None:
        gateway = FakeEmailGateway()
        email = world.customer.email
        confirmed = sql_desk(borrowing(session), gateway, FixedClock()).confirmed(
            draft_command(world)
        )

        (notification,) = session.exec(select(Notification)).all()
        assert notification.reservation_id == confirmed.detail.id
        assert notification.recipient_email == email
        assert notification.status is NotificationStatus.SENT
        assert notification.provider == "resend"
        assert notification.provider_message_id == "fake-message-1"
        assert notification.sent_at is not None
        assert notification.attempts == 1
        (message,) = gateway.sent_to(email)
        assert confirmed.detail.reference in message.text_body
        assert message.idempotency_key == f"notification-{notification.id}"

    def test_a_provider_failure_marks_the_row_failed_and_leaves_the_booking_alone(
        self, session: Session, world: BookingWorld
    ) -> None:
        gateway = FakeEmailGateway(PROVIDER_FAILURE)
        confirmed = sql_desk(borrowing(session), gateway, FixedClock()).confirmed(
            draft_command(world)
        )

        (notification,) = session.exec(select(Notification)).all()
        assert notification.status is NotificationStatus.FAILED
        assert notification.last_error == PROVIDER_FAILURE
        assert notification.sent_at is None
        assert notification.attempts == 1

        assert status_of(session, confirmed.detail.id) is ReservationStatus.CONFIRMED
        (allocation,) = session.exec(select(AssetAllocation)).all()
        assert allocation.released_at is None

    def test_recording_an_outcome_for_a_notification_that_was_never_queued_is_refused(
        self, session: Session, world: BookingWorld
    ) -> None:
        with (
            borrowing(session)() as uow,
            pytest.raises(LookupError, match="is not in the outbox"),
        ):
            uow.notifications.mark_failed(world.profile.id, PROVIDER_FAILURE)
