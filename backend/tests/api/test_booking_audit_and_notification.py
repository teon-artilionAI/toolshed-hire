"""What a reservation leaves behind besides the reservation, seen through the API.

Every change of status leaves one audit event that names the caller, the role
the caller held and the request it happened in (BR-49). There are four through
the routes, which are `reservation.created`, `reservation.held`,
`reservation.confirmed` and `reservation.cancelled`, and the sweep writes the
fifth, `reservation.expired`, with no actor.

The booking confirmation is queued with the confirmation and sent after it
(BR-19). Holding writes no notification row and confirming writes exactly one.
That moved in this change. It used to be queued when the hold was made,
because there was no confirm step to queue it at.

The request id is the thread that ties these together. The value a caller sends
in `X-Request-ID` is the value in the response header, on every log line of the
request and in the audit event, so one id finds all of it.

These run against the in memory database, like the rest of tests/api, on a
clock that stands still, and the email gateway is the fake one from the
`email_gateway` fixture.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final
from uuid import UUID

import pytest
from fastapi import FastAPI, Request, status
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.api.deps import get_notification_gateway
from app.application.notification.ports import NotificationGateway
from app.config import Environment
from app.domain.enums import NotificationStatus, UserRole
from app.infrastructure.models import AuditEvent, Notification
from app.infrastructure.notification import FakeEmailGateway, UnconfiguredEmailGateway
from tests.support.booking_api import (
    BookingClient,
    BookingWorld,
    answered,
    build_booking_world,
    created,
)
from tests.support.factories import Factory

REQUEST_ID: Final[str] = "6f1c2b9e-3d4a-4c5b-8e7f-0a1b2c3d4e5f"
# From the block reserved for documentation, so it is nobody's real address.
CLIENT_ADDRESS: Final[str] = "203.0.113.9"
CLIENT_PORT: Final[int] = 50_000
PROVIDER_FAILURE: Final[str] = "Resend answered 500 (Internal Server Error)."
JUST_PAST_THE_HOLD: Final[timedelta] = timedelta(minutes=30, seconds=1)


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed branch, product model, unit and customer."""
    built = build_booking_world(factory)
    session.commit()
    return built


def events(session: Session) -> list[AuditEvent]:
    """Return every audit event, in the order it was written."""
    return list(session.exec(select(AuditEvent).order_by(col(AuditEvent.id))).all())


def actions(session: Session) -> list[str]:
    """Return the action of every audit event, in the order it was written."""
    return [event.action for event in events(session)]


class TestEveryChangeOfStatusLeavesOneAuditEvent:
    """BR-49. The state change and its record commit together."""

    def test_the_four_moves_a_caller_makes_write_four_events_in_order(
        self, booking: BookingClient, session: Session, world: BookingWorld
    ) -> None:
        confirmed = booking.confirmed(world)
        answered(booking.cancel(world.customer, confirmed["id"]))
        assert actions(session) == [
            "reservation.created",
            "reservation.held",
            "reservation.confirmed",
            "reservation.cancelled",
        ]
        assert {str(event.entity_id) for event in events(session)} == {confirmed["id"]}
        assert {event.entity_type for event in events(session)} == {"reservation"}

    def test_a_hold_that_ran_out_is_expired_by_the_sweep_with_no_actor(
        self, booking: BookingClient, session: Session, world: BookingWorld
    ) -> None:
        held = booking.held(world)
        booking.clock.advance(JUST_PAST_THE_HOLD)
        answered(booking.read(world.customer, held["id"]))
        expired = events(session)[-1]
        assert expired.action == "reservation.expired"
        assert expired.actor_user_id is None
        assert expired.actor_role is None
        assert expired.before_state is not None
        assert expired.before_state["status"] == "HELD"
        assert expired.after_state is not None
        assert expired.after_state["status"] == "EXPIRED"

    def test_each_event_records_the_status_before_and_after(
        self, booking: BookingClient, session: Session, world: BookingWorld
    ) -> None:
        booking.confirmed(world)
        moves = [
            (
                event.before_state["status"] if event.before_state else None,
                event.after_state["status"] if event.after_state else None,
            )
            for event in events(session)
        ]
        assert moves == [(None, "DRAFT"), ("DRAFT", "HELD"), ("HELD", "CONFIRMED")]

    def test_the_event_names_the_caller_and_the_role_read_from_the_database(
        self, booking: BookingClient, session: Session, world: BookingWorld
    ) -> None:
        booking.drafted(world)
        (event,) = events(session)
        assert event.actor_user_id == world.customer.id
        assert event.actor_role is UserRole.CUSTOMER

    def test_a_counter_booking_names_the_assistant_and_not_the_customer(
        self, booking: BookingClient, session: Session, factory: Factory, world: BookingWorld
    ) -> None:
        assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
        session.commit()
        created(
            booking.create(assistant, world.payload(customer_profile_id=world.profile.id))
        )
        (event,) = events(session)
        assert event.actor_user_id == assistant.id
        assert event.actor_role is UserRole.COUNTER_STAFF

    def test_the_event_carries_the_request_id_the_caller_sent(
        self, booking: BookingClient, session: Session, world: BookingWorld
    ) -> None:
        created(booking.create(world.customer, world.payload(), REQUEST_ID))
        (event,) = events(session)
        assert event.request_id == UUID(REQUEST_ID)

    def test_the_event_carries_the_client_address_when_the_server_knows_one(
        self, booking: BookingClient, session: Session, world: BookingWorld
    ) -> None:
        from_an_address = TestClient(booking.client.app, client=(CLIENT_ADDRESS, CLIENT_PORT))
        elsewhere = BookingClient(from_an_address, booking.clock)
        created(elsewhere.create(world.customer, world.payload()))
        (event,) = events(session)
        assert str(event.ip_address) == CLIENT_ADDRESS

    def test_a_client_host_that_is_not_an_address_is_recorded_as_unknown(
        self, booking: BookingClient, session: Session, world: BookingWorld
    ) -> None:
        """The test client calls itself `testclient`, which is no address at all."""
        booking.drafted(world)
        (event,) = events(session)
        assert event.ip_address is None

    def test_a_refused_hold_leaves_no_event_and_no_notification(
        self, booking: BookingClient, session: Session, world: BookingWorld
    ) -> None:
        booking.held(world)
        second = booking.drafted(world)
        events_before = len(events(session))
        refused = booking.hold(world.customer, second["id"])
        assert refused.status_code == status.HTTP_409_CONFLICT
        assert len(events(session)) == events_before
        assert session.exec(select(Notification)).all() == []


class TestTheConfirmationIsQueuedAtConfirmationAndSentBeforeTheAnswer:
    """BR-19. Queued with the confirmation, sent after the commit, inside the request."""

    def test_creating_and_holding_write_no_notification_row(
        self,
        booking: BookingClient,
        session: Session,
        world: BookingWorld,
        email_gateway: FakeEmailGateway,
    ) -> None:
        booking.held(world)
        assert session.exec(select(Notification)).all() == []
        assert email_gateway.sent == []

    def test_confirming_writes_exactly_one_and_sends_it_to_the_customer(
        self,
        booking: BookingClient,
        session: Session,
        world: BookingWorld,
        email_gateway: FakeEmailGateway,
    ) -> None:
        confirmed = booking.confirmed(world)
        (message,) = email_gateway.sent_to(world.customer.email)
        assert str(confirmed["reference"]) in message.subject
        (notification,) = session.exec(select(Notification)).all()
        assert str(notification.reservation_id) == confirmed["id"]
        assert notification.status is NotificationStatus.SENT
        assert notification.provider_message_id == "fake-message-1"

    def test_cancelling_a_confirmed_reservation_sends_nothing_more(
        self,
        booking: BookingClient,
        session: Session,
        world: BookingWorld,
        email_gateway: FakeEmailGateway,
    ) -> None:
        confirmed = booking.confirmed(world)
        answered(booking.cancel(world.customer, confirmed["id"]))
        assert len(session.exec(select(Notification)).all()) == 1
        assert len(email_gateway.sent) == 1

    def test_a_counter_confirmation_is_sent_to_the_customer_and_not_to_the_assistant(
        self,
        booking: BookingClient,
        session: Session,
        factory: Factory,
        world: BookingWorld,
        email_gateway: FakeEmailGateway,
    ) -> None:
        assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=world.branch)
        session.commit()
        draft = created(
            booking.create(assistant, world.payload(customer_profile_id=world.profile.id))
        )
        answered(booking.hold(assistant, draft["id"]))
        answered(booking.confirm(assistant, draft["id"]))
        assert [message.to for message in email_gateway.sent] == [world.customer.email]

    def test_a_provider_failure_still_answers_200_and_marks_the_notification_failed(
        self, booking: BookingClient, session: Session, world: BookingWorld
    ) -> None:
        held = booking.held(world)
        booking.client.app.dependency_overrides[get_notification_gateway] = (
            lambda: FakeEmailGateway(PROVIDER_FAILURE)
        )
        confirmed = answered(booking.confirm(world.customer, held["id"]))
        assert confirmed["status"] == "CONFIRMED"
        (notification,) = session.exec(select(Notification)).all()
        assert notification.status is NotificationStatus.FAILED
        assert notification.last_error == PROVIDER_FAILURE

    def test_with_email_not_configured_the_confirmation_succeeds_and_says_why_nothing_was_sent(
        self, booking: BookingClient, session: Session, world: BookingWorld
    ) -> None:
        held = booking.held(world)
        booking.client.app.dependency_overrides[get_notification_gateway] = (
            UnconfiguredEmailGateway
        )
        answered(booking.confirm(world.customer, held["id"]))
        (notification,) = session.exec(select(Notification)).all()
        assert notification.status is NotificationStatus.FAILED
        assert notification.last_error == "Email is not configured in this environment."


class TestTheApplicationCarriesItsGateway:
    """The application factory chooses the gateway once, when the application is built."""

    def test_every_environment_the_suite_builds_has_one(
        self, applications_by_environment: dict[Environment, FastAPI]
    ) -> None:
        for application in applications_by_environment.values():
            assert isinstance(application.state.notification_gateway, NotificationGateway)

    def test_an_application_assembled_without_one_fails_with_a_reason(self) -> None:
        bare = FastAPI()
        request = Request({"type": "http", "app": bare})
        with pytest.raises(RuntimeError, match="built without an email gateway"):
            get_notification_gateway(request)
