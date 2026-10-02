"""What a booking leaves behind besides the booking, seen through the API.

`POST /api/allocations` answers exactly as it did before. What changed is what
is in the database afterwards. Every booking now leaves one audit event that
names the caller, the role the caller held and the request it happened in
(BR-49), and one notification that was queued with the booking and sent after
it (BR-19).

The request id is the thread that ties these together. The value a caller sends
in `X-Request-ID` is the value in the response header, on every log line of the
request and in the audit event, so one id finds all of it.

These run against the in memory database, like the rest of tests/api, and the
email gateway is the fake one from the `email_gateway` fixture.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

import pytest
from fastapi import FastAPI, Request, status
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.api.deps import get_notification_gateway
from app.application.notification.ports import NotificationGateway
from app.config import Environment
from app.domain.enums import NotificationStatus, UserRole
from app.infrastructure.models import AuditEvent, Notification, UserAccount
from app.infrastructure.notification import FakeEmailGateway, UnconfiguredEmailGateway
from tests.support.factories import Factory
from tests.support.http import booking_payload, future_period
from tests.support.scenarios import AllocationScenario, build_allocation_scenario
from tests.support.tokens import authorization_header, mint_access_token

ALLOCATIONS_PATH: Final[str] = "/api/allocations"
REQUEST_ID_HEADER: Final[str] = "X-Request-ID"
REQUEST_ID: Final[str] = "6f1c2b9e-3d4a-4c5b-8e7f-0a1b2c3d4e5f"
# From the block reserved for documentation, so it is nobody's real address.
CLIENT_ADDRESS: Final[str] = "203.0.113.9"
CLIENT_PORT: Final[int] = 50_000
PROVIDER_FAILURE: Final[str] = "Resend answered 500 (Internal Server Error)."


@pytest.fixture
def scenario(session: Session, factory: Factory) -> AllocationScenario:
    """Return a committed branch, product model, unit and customer."""
    built = build_allocation_scenario(factory, future_period())
    session.commit()
    return built


def book(
    client: TestClient, scenario: AllocationScenario, account: UserAccount, **body: str
) -> dict[str, object]:
    """Post a booking as `account`, assert it was created and return the response body."""
    payload = booking_payload(
        product_model_id=scenario.product_model.id,
        branch_id=scenario.branch.id,
        period=future_period(),
    )
    headers = authorization_header(mint_access_token(account.id))
    headers[REQUEST_ID_HEADER] = REQUEST_ID
    response = client.post(ALLOCATIONS_PATH, json={**payload, **body}, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    created: dict[str, object] = response.json()
    return created


class TestABookingLeavesOneAuditEvent:
    """BR-49. The state change and its record commit together."""

    def test_the_event_names_the_reservation_and_the_action(
        self, client: TestClient, session: Session, scenario: AllocationScenario
    ) -> None:
        created = book(client, scenario, scenario.customer)
        (event,) = session.exec(select(AuditEvent)).all()
        assert event.action == "reservation.held"
        assert event.entity_type == "reservation"
        assert str(event.entity_id) == created["reservationId"]

    def test_the_event_names_the_caller_and_the_role_read_from_the_database(
        self, client: TestClient, session: Session, scenario: AllocationScenario
    ) -> None:
        book(client, scenario, scenario.customer)
        (event,) = session.exec(select(AuditEvent)).all()
        assert event.actor_user_id == scenario.customer.id
        assert event.actor_role is UserRole.CUSTOMER

    def test_a_counter_booking_names_the_assistant_and_not_the_customer(
        self, client: TestClient, session: Session, factory: Factory, scenario: AllocationScenario
    ) -> None:
        assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=scenario.branch)
        session.commit()
        book(client, scenario, assistant, customerUserId=str(scenario.customer.id))
        (event,) = session.exec(select(AuditEvent)).all()
        assert event.actor_user_id == assistant.id
        assert event.actor_role is UserRole.COUNTER_STAFF

    def test_the_event_carries_the_request_id_the_caller_sent(
        self, client: TestClient, session: Session, scenario: AllocationScenario
    ) -> None:
        book(client, scenario, scenario.customer)
        (event,) = session.exec(select(AuditEvent)).all()
        assert event.request_id == UUID(REQUEST_ID)

    def test_the_event_carries_the_client_address_when_the_server_knows_one(
        self, client: TestClient, session: Session, scenario: AllocationScenario
    ) -> None:
        from_an_address = TestClient(client.app, client=(CLIENT_ADDRESS, CLIENT_PORT))
        book(from_an_address, scenario, scenario.customer)
        (event,) = session.exec(select(AuditEvent)).all()
        assert str(event.ip_address) == CLIENT_ADDRESS

    def test_a_client_host_that_is_not_an_address_is_recorded_as_unknown(
        self, client: TestClient, session: Session, scenario: AllocationScenario
    ) -> None:
        """The test client calls itself `testclient`, which is no address at all."""
        book(client, scenario, scenario.customer)
        (event,) = session.exec(select(AuditEvent)).all()
        assert event.ip_address is None

    def test_a_refused_booking_leaves_no_event_and_no_notification(
        self, client: TestClient, session: Session, scenario: AllocationScenario
    ) -> None:
        book(client, scenario, scenario.customer)
        refused = client.post(
            ALLOCATIONS_PATH,
            json=booking_payload(
                product_model_id=scenario.product_model.id,
                branch_id=scenario.branch.id,
                period=future_period(),
            ),
            headers=authorization_header(mint_access_token(scenario.customer.id)),
        )
        assert refused.status_code == status.HTTP_409_CONFLICT
        assert len(session.exec(select(AuditEvent)).all()) == 1
        assert len(session.exec(select(Notification)).all()) == 1


class TestABookingSendsItsConfirmationBeforeItAnswers:
    """BR-19. Queued with the booking, sent after the commit, inside the request."""

    def test_the_confirmation_goes_to_the_customers_address_and_is_marked_sent(
        self,
        client: TestClient,
        session: Session,
        scenario: AllocationScenario,
        email_gateway: FakeEmailGateway,
    ) -> None:
        created = book(client, scenario, scenario.customer)
        (message,) = email_gateway.sent_to(scenario.customer.email)
        assert str(created["reference"]) in message.subject
        (notification,) = session.exec(select(Notification)).all()
        assert str(notification.reservation_id) == created["reservationId"]
        assert notification.status is NotificationStatus.SENT
        assert notification.provider_message_id == "fake-message-1"

    def test_a_counter_booking_is_confirmed_to_the_customer_and_not_to_the_assistant(
        self,
        client: TestClient,
        session: Session,
        factory: Factory,
        scenario: AllocationScenario,
        email_gateway: FakeEmailGateway,
    ) -> None:
        assistant = factory.user(role=UserRole.COUNTER_STAFF, branch=scenario.branch)
        session.commit()
        book(client, scenario, assistant, customerUserId=str(scenario.customer.id))
        assert [message.to for message in email_gateway.sent] == [scenario.customer.email]

    def test_a_provider_failure_still_answers_201_and_marks_the_notification_failed(
        self, client: TestClient, session: Session, scenario: AllocationScenario
    ) -> None:
        client.app.dependency_overrides[get_notification_gateway] = lambda: FakeEmailGateway(
            PROVIDER_FAILURE
        )
        created = book(client, scenario, scenario.customer)
        assert created["status"] == "HELD"
        (notification,) = session.exec(select(Notification)).all()
        assert notification.status is NotificationStatus.FAILED
        assert notification.last_error == PROVIDER_FAILURE

    def test_with_email_not_configured_the_booking_succeeds_and_says_why_nothing_was_sent(
        self, client: TestClient, session: Session, scenario: AllocationScenario
    ) -> None:
        client.app.dependency_overrides[get_notification_gateway] = UnconfiguredEmailGateway
        book(client, scenario, scenario.customer)
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
