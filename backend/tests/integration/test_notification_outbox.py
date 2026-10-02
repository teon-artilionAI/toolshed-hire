"""The outbox on PostgreSQL. Queued with the confirmation, sent after the commit.

BR-19 makes two promises. The booking confirmation is written in the same
transaction as the confirmation of the reservation, and it is sent only once
that transaction has committed. A provider failure then marks the notification
failed and leaves the booking alone.

"After the commit" is a claim about what another connection can see, so the
gateway in the first test opens a connection of its own at the moment it is
called and writes down what is visible. If it can read the confirmed
reservation and its queued notification, both were committed before the send
began.

Holding a reservation queues nothing. That the notification shares the fate of
a confirmation that fails is in test_booking_transaction.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.application.booking.confirm_reservation import ConfirmReservationUseCase
from app.application.booking.expire_holds import ExpireHoldsAndNoShowsUseCase
from app.application.notification.dispatcher import (
    DEFAULT_DISPATCH_LIMIT,
    NotificationDispatcher,
)
from app.application.notification.ports import DeliveryReceipt
from app.domain.enums import NotificationStatus, ReservationStatus
from app.domain.notification import EmailMessage
from app.infrastructure.models import AuditEvent, Notification, Reservation
from app.infrastructure.notification import FakeEmailGateway
from tests.support.booking import customer_of, draft_command, move_on, opening, sql_desk
from tests.support.booking_api import BookingWorld, build_booking_world
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.pg import count_active_allocations

pytestmark = pytest.mark.postgres

PROVIDER_FAILURE: Final[str] = "Resend answered 500 (Internal Server Error)."
PROVIDER_MESSAGE_ID: Final[str] = "made-up-provider-message-id"
SENT_AT: Final[datetime] = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)


class DispatcherThatNeverRuns(NotificationDispatcher):
    """Stands for a request that ended between its commit and its dispatch."""

    def dispatch_due(self, limit: int = DEFAULT_DISPATCH_LIMIT) -> int:
        """Send nothing, as a process that was stopped at that moment would."""
        return 0


class ObservingGateway:
    """A gateway that looks at the database through its own connection when called."""

    def __init__(self, engine: Engine) -> None:
        """Keep the engine the observation connection is opened on."""
        self._engine = engine
        self.seen: list[tuple[str, NotificationStatus, ReservationStatus]] = []

    def send(self, message: EmailMessage) -> DeliveryReceipt:
        """Record every notification another connection can see, with its booking."""
        with Session(self._engine) as observer:
            rows = observer.exec(
                select(Reservation.reference, Notification.status, Reservation.status).join(
                    Notification, col(Notification.reservation_id) == col(Reservation.id)
                )
            ).all()
        self.seen = [tuple(row) for row in rows]
        return DeliveryReceipt.delivered(PROVIDER_MESSAGE_ID)


@pytest.fixture
def world(postgres_session: Session, postgres_factory: Factory) -> BookingWorld:
    """Return a committed branch, a model with two units and a customer."""
    built = build_booking_world(postgres_factory, asset_count=2)
    postgres_session.commit()
    return built


class TestTheConfirmationIsSentAfterTheCommit:
    """BR-19. Queued in the confirmation's transaction, dispatched once it is committed."""

    def test_a_hold_queues_nothing_and_calls_no_gateway(
        self, postgres_engine: Engine, postgres_session: Session, world: BookingWorld
    ) -> None:
        gateway = ObservingGateway(postgres_engine)
        sql_desk(opening(postgres_engine), gateway, FixedClock()).held(draft_command(world))
        assert postgres_session.exec(select(Notification)).all() == []
        assert gateway.seen == []

    def test_when_the_gateway_is_called_another_connection_can_already_see_the_confirmation(
        self, postgres_engine: Engine, world: BookingWorld
    ) -> None:
        gateway = ObservingGateway(postgres_engine)
        confirmed = sql_desk(opening(postgres_engine), gateway, FixedClock()).confirmed(
            draft_command(world)
        )
        assert gateway.seen == [
            (confirmed.detail.reference, NotificationStatus.QUEUED, ReservationStatus.CONFIRMED)
        ]

    def test_a_delivered_confirmation_is_marked_sent_with_the_provider_id(
        self, postgres_engine: Engine, postgres_session: Session, world: BookingWorld
    ) -> None:
        email = world.customer.email
        gateway = ObservingGateway(postgres_engine)
        confirmed = sql_desk(opening(postgres_engine), gateway, FixedClock(SENT_AT)).confirmed(
            draft_command(world)
        )

        (notification,) = postgres_session.exec(select(Notification)).all()
        assert notification.reservation_id == confirmed.detail.id
        assert notification.recipient_email == email
        assert notification.status is NotificationStatus.SENT
        assert notification.provider == "resend"
        assert notification.provider_message_id == PROVIDER_MESSAGE_ID
        assert notification.queued_at == SENT_AT
        assert notification.sent_at == SENT_AT
        assert notification.attempts == 1
        assert notification.last_error is None

    def test_a_provider_failure_marks_the_notification_failed_with_the_reason(
        self, postgres_engine: Engine, postgres_session: Session, world: BookingWorld
    ) -> None:
        gateway = FakeEmailGateway(PROVIDER_FAILURE)
        sql_desk(opening(postgres_engine), gateway, FixedClock()).confirmed(draft_command(world))

        (notification,) = postgres_session.exec(select(Notification)).all()
        assert notification.status is NotificationStatus.FAILED
        assert notification.last_error == PROVIDER_FAILURE
        assert notification.sent_at is None
        assert notification.provider_message_id is None
        assert notification.attempts == 1

    def test_a_provider_failure_leaves_the_booking_exactly_as_it_was_committed(
        self, postgres_engine: Engine, postgres_session: Session, world: BookingWorld
    ) -> None:
        asset_id = world.assets[0].id
        gateway = FakeEmailGateway(PROVIDER_FAILURE)
        confirmed = sql_desk(opening(postgres_engine), gateway, FixedClock()).confirmed(
            draft_command(world)
        )

        reservation = postgres_session.get(Reservation, confirmed.detail.id)
        assert reservation is not None
        assert reservation.status is ReservationStatus.CONFIRMED
        assert count_active_allocations(postgres_session, asset_id) == 1
        assert len(postgres_session.exec(select(AuditEvent)).all()) == 3

    def test_a_notification_left_queued_by_an_earlier_request_is_sent_by_the_next_one(
        self, postgres_engine: Engine, postgres_session: Session, world: BookingWorld
    ) -> None:
        """A request that died between its commit and its dispatch strands nothing."""
        customer = customer_of(world)
        unit_of_work = opening(postgres_engine)
        clock = FixedClock()
        desk = sql_desk(unit_of_work, FakeEmailGateway(), clock)
        first = desk.held(draft_command(world))
        # The first confirmation commits and its dispatch never runs.
        stranded = ConfirmReservationUseCase(
            unit_of_work(),
            clock,
            ExpireHoldsAndNoShowsUseCase(unit_of_work(), clock),
            DispatcherThatNeverRuns(unit_of_work(), FakeEmailGateway(), clock),
        )
        stranded.execute(move_on(first, customer))
        statuses = [n.status for n in postgres_session.exec(select(Notification)).all()]
        assert statuses == [NotificationStatus.QUEUED]

        gateway = FakeEmailGateway()
        sql_desk(unit_of_work, gateway, clock).confirmed(draft_command(world))
        postgres_session.rollback()
        statuses = [n.status for n in postgres_session.exec(select(Notification)).all()]
        assert statuses == [NotificationStatus.SENT, NotificationStatus.SENT]
        assert len(gateway.sent) == 2
