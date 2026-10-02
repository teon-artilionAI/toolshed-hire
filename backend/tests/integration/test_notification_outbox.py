"""The outbox on PostgreSQL. Queued with the booking, sent after the commit.

BR-19 makes two promises. The confirmation is written in the same transaction
as the booking, and it is sent only once that transaction has committed. A
provider failure then marks the notification failed and leaves the booking
alone.

"After the commit" is a claim about what another connection can see, so the
gateway in the first test opens a connection of its own at the moment it is
called and writes down what is visible. If it can read the booking and its
queued notification, both were committed before the send began.

That the notification shares the fate of a booking that fails is in
test_booking_transaction.py.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Final

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.application.booking.create_reservation import CreateReservationUseCase
from app.application.notification.dispatcher import (
    DEFAULT_DISPATCH_LIMIT,
    NotificationDispatcher,
)
from app.application.notification.ports import DeliveryReceipt
from app.domain.enums import NotificationStatus, ReservationStatus
from app.domain.notification import EmailMessage
from app.domain.period import BookingPeriod
from app.infrastructure.models import AuditEvent, Notification, Reservation
from app.infrastructure.notification import FakeEmailGateway
from tests.support.booking import command_for, opening, sql_use_case
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.pg import count_active_allocations
from tests.support.scenarios import AllocationScenario, build_allocation_scenario

pytestmark = pytest.mark.postgres

FIRST_HIRE: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 9), date(2026, 3, 12))
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
def scenario(postgres_session: Session, postgres_factory: Factory) -> AllocationScenario:
    """Return a committed branch, product model, unit and customer."""
    built = build_allocation_scenario(postgres_factory, FIRST_HIRE)
    postgres_session.commit()
    return built


class TestTheConfirmationIsSentAfterTheCommit:
    """BR-19. Queued in the booking's transaction, dispatched once it is committed."""

    def test_when_the_gateway_is_called_another_connection_can_already_see_the_booking(
        self, postgres_engine: Engine, scenario: AllocationScenario
    ) -> None:
        gateway = ObservingGateway(postgres_engine)
        use_case = sql_use_case(opening(postgres_engine), gateway, FixedClock())
        view = use_case.execute(command_for(scenario, FIRST_HIRE))
        assert gateway.seen == [
            (view.reference, NotificationStatus.QUEUED, ReservationStatus.HELD)
        ]

    def test_a_delivered_confirmation_is_marked_sent_with_the_provider_id(
        self, postgres_engine: Engine, postgres_session: Session, scenario: AllocationScenario
    ) -> None:
        clock = FixedClock(SENT_AT)
        gateway = ObservingGateway(postgres_engine)
        use_case = sql_use_case(opening(postgres_engine), gateway, clock)
        view = use_case.execute(command_for(scenario, FIRST_HIRE))

        (notification,) = postgres_session.exec(select(Notification)).all()
        assert notification.reservation_id == view.reservation_id
        assert notification.recipient_email == scenario.customer.email
        assert notification.status is NotificationStatus.SENT
        assert notification.provider == "resend"
        assert notification.provider_message_id == PROVIDER_MESSAGE_ID
        assert notification.queued_at == SENT_AT
        assert notification.sent_at == SENT_AT
        assert notification.attempts == 1
        assert notification.last_error is None

    def test_a_provider_failure_marks_the_notification_failed_with_the_reason(
        self, postgres_engine: Engine, postgres_session: Session, scenario: AllocationScenario
    ) -> None:
        gateway = FakeEmailGateway(PROVIDER_FAILURE)
        use_case = sql_use_case(opening(postgres_engine), gateway, FixedClock())
        use_case.execute(command_for(scenario, FIRST_HIRE))

        (notification,) = postgres_session.exec(select(Notification)).all()
        assert notification.status is NotificationStatus.FAILED
        assert notification.last_error == PROVIDER_FAILURE
        assert notification.sent_at is None
        assert notification.provider_message_id is None
        assert notification.attempts == 1

    def test_a_provider_failure_leaves_the_booking_exactly_as_it_was_committed(
        self, postgres_engine: Engine, postgres_session: Session, scenario: AllocationScenario
    ) -> None:
        gateway = FakeEmailGateway(PROVIDER_FAILURE)
        use_case = sql_use_case(opening(postgres_engine), gateway, FixedClock())
        view = use_case.execute(command_for(scenario, FIRST_HIRE))

        reservation = postgres_session.get(Reservation, view.reservation_id)
        assert reservation is not None
        assert reservation.status is ReservationStatus.HELD
        assert count_active_allocations(postgres_session, scenario.asset.id) == 1
        assert len(postgres_session.exec(select(AuditEvent)).all()) == 1

    def test_a_notification_left_queued_by_an_earlier_request_is_sent_by_the_next_one(
        self, postgres_engine: Engine, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        """A request that died between its commit and its dispatch strands nothing."""
        scenario = build_allocation_scenario(postgres_factory, FIRST_HIRE, asset_count=2)
        postgres_session.commit()
        unit_of_work = opening(postgres_engine)
        clock = FixedClock()
        # The first booking commits and its dispatch never runs.
        stranded = CreateReservationUseCase(
            unit_of_work(),
            clock,
            DispatcherThatNeverRuns(unit_of_work(), FakeEmailGateway(), clock),
        )
        stranded.execute(command_for(scenario, FIRST_HIRE))
        statuses = [n.status for n in postgres_session.exec(select(Notification)).all()]
        assert statuses == [NotificationStatus.QUEUED]

        gateway = FakeEmailGateway()
        following = sql_use_case(unit_of_work, gateway, clock)
        following.execute(command_for(scenario, FIRST_HIRE))
        postgres_session.rollback()
        statuses = [n.status for n in postgres_session.exec(select(Notification)).all()]
        assert statuses == [NotificationStatus.SENT, NotificationStatus.SENT]
        assert len(gateway.sent) == 2
