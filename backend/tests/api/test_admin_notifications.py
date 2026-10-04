"""The notification log and the re-send of a failed confirmation, through HTTP (FR-27, US-36).

A customer confirms a booking while the email gateway refuses every message,
so the confirmation is FAILED. The administrator lists the log, narrows it to
the failures and sends the failed one again, which writes a new notification
and leaves the failed one exactly as it was. A gateway that only sends to one
allowed address still refuses the re-send to any other. These run against the
in memory database on the still clock of the booking tests.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Final
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import status
from pydantic import SecretStr
from sqlmodel import Session, select

from app.api.deps import get_notification_gateway
from app.application.notification.ports import NotificationGateway
from app.domain.enums import NotificationStatus, UserRole
from app.infrastructure.models import AuditEvent, Notification, UserAccount
from app.infrastructure.notification import FakeEmailGateway, ResendEmailAdapter
from app.main import app as production_app
from tests.support.admin_api import (
    NOTIFICATION_MEMBERS,
    NOTIFICATIONS_PATH,
    PAGE_MEMBERS,
    read_notifications,
    resend,
    resend_path,
)
from tests.support.booking_api import BookingClient, BookingWorld, answered, build_booking_world
from tests.support.factories import Factory
from tests.support.http import problem_code, problem_of
from tests.support.report_api import refused_fields

FAILURE: Final[str] = "The provider refused the message."
ALREADY_SENT: Final[str] = (
    "Only a notification that failed can be sent again. This one is already sent."
)
ALLOWED_ONLY: Final[str] = "owner@example.co.za"
TEST_ONLY_KEY: Final[str] = "test-only-not-a-real-key"
SENDER: Final[str] = "Toolshed Hire <onboarding@resend.dev>"
# How long after the failure the administrator sends it again.
LATER: Final[timedelta] = timedelta(minutes=20)

type GatewaySwitch = Callable[[NotificationGateway], None]


@pytest.fixture
def world(session: Session, factory: Factory) -> BookingWorld:
    """Return a committed world with one unit."""
    built = build_booking_world(factory)
    session.commit()
    return built


@pytest.fixture
def administrator(session: Session, factory: Factory) -> UserAccount:
    """Return a committed administrator."""
    account = factory.user(role=UserRole.ADMIN)
    session.commit()
    return account


@pytest.fixture
def use_gateway(booking: BookingClient, monkeypatch: pytest.MonkeyPatch) -> GatewaySwitch:
    """Return a call that makes the application send through the gateway it is given."""

    def _use(gateway: NotificationGateway) -> None:
        """Send everything that follows through `gateway`."""
        monkeypatch.setitem(
            production_app.dependency_overrides, get_notification_gateway, lambda: gateway
        )

    return _use


class TestTheLog:
    """Every confirmation, newest first, narrowed by status."""

    def test_a_failed_confirmation_is_listed_with_why_it_failed(
        self,
        booking: BookingClient,
        world: BookingWorld,
        administrator: UserAccount,
        use_gateway: GatewaySwitch,
    ) -> None:
        use_gateway(FakeEmailGateway(failure_reason=FAILURE))
        confirmed = booking.confirmed(world)
        page = answered(read_notifications(booking, administrator))

        assert page.keys() == PAGE_MEMBERS
        assert (page["page"], page["pageSize"], page["total"]) == (1, 20, 1)
        (failed,) = page["items"]
        assert failed.keys() == NOTIFICATION_MEMBERS
        assert (failed["reservationId"], failed["reservationReference"]) == (
            confirmed["id"], confirmed["reference"]
        )
        assert (failed["type"], failed["status"], failed["attempts"]) == (
            "BOOKING_CONFIRMATION", "FAILED", 1
        )
        assert (failed["lastError"], failed["sentAt"], failed["resendOf"]) == (
            FAILURE, None, None
        )
        assert failed["recipientEmail"] == world.customer.email
        assert failed["queuedAt"] == "2026-03-02T10:00:00+02:00"

    def test_the_log_is_narrowed_by_status(
        self,
        booking: BookingClient,
        world: BookingWorld,
        administrator: UserAccount,
        use_gateway: GatewaySwitch,
        session: Session,
        factory: Factory,
    ) -> None:
        use_gateway(FakeEmailGateway(failure_reason=FAILURE))
        booking.confirmed(world)
        use_gateway(FakeEmailGateway())
        factory.asset(product_model=world.product_model, branch=world.branch)
        session.commit()
        booking.confirmed(world)

        assert answered(read_notifications(booking, administrator))["total"] == 2
        for wanted in (NotificationStatus.FAILED, NotificationStatus.SENT):
            page = answered(read_notifications(booking, administrator, status=wanted.value))
            assert [item["status"] for item in page["items"]] == [wanted.value]
        queued = answered(read_notifications(booking, administrator, status="QUEUED"))
        assert queued["total"] == 0


class TestTheResend:
    """A new notification is written and sent, and the failed one is never changed."""

    def test_a_failed_confirmation_is_sent_again_as_a_new_notification(
        self,
        booking: BookingClient,
        world: BookingWorld,
        administrator: UserAccount,
        use_gateway: GatewaySwitch,
        session: Session,
    ) -> None:
        use_gateway(FakeEmailGateway(failure_reason=FAILURE))
        booking.confirmed(world)
        (failed,) = answered(read_notifications(booking, administrator))["items"]
        gateway = FakeEmailGateway()
        use_gateway(gateway)
        booking.clock.advance(LATER)

        response = resend(booking, administrator, failed["id"])
        assert response.status_code == status.HTTP_201_CREATED, response.text
        again = response.json()
        assert again.keys() == NOTIFICATION_MEMBERS
        assert again["id"] != failed["id"]
        assert (again["resendOf"], again["status"], again["attempts"]) == (failed["id"], "SENT", 1)
        assert (again["reservationId"], again["recipientEmail"], again["subject"]) == (
            failed["reservationId"], failed["recipientEmail"], failed["subject"]
        )
        assert [message.to for message in gateway.sent] == [failed["recipientEmail"]]

        log = answered(read_notifications(booking, administrator))
        assert [item["id"] for item in log["items"]] == [again["id"], failed["id"]]
        assert log["items"][1] == failed
        stored = session.get(Notification, UUID(str(failed["id"])))
        assert stored is not None
        session.refresh(stored)
        assert (stored.status, stored.attempts, stored.last_error) == (
            NotificationStatus.FAILED, 1, FAILURE
        )
        (event,) = [
            e for e in session.exec(select(AuditEvent)) if e.action == "notification.resent"
        ]
        assert (str(event.entity_id), event.actor_user_id) == (again["id"], administrator.id)
        assert (event.after_state or {})["resend_of"] == failed["id"]

    def test_the_allowed_recipient_of_the_resend_adapter_still_applies(
        self,
        booking: BookingClient,
        world: BookingWorld,
        administrator: UserAccount,
        use_gateway: GatewaySwitch,
    ) -> None:
        def provider(request: httpx.Request) -> httpx.Response:
            """Fail the test, because no message may reach the provider."""
            raise AssertionError(f"A message reached the provider at {request.url}.")

        adapter = ResendEmailAdapter(
            api_key=SecretStr(TEST_ONLY_KEY),
            sender=SENDER,
            allowed_recipient=ALLOWED_ONLY,
            transport=httpx.MockTransport(provider),
        )
        use_gateway(adapter)
        booking.confirmed(world)
        (failed,) = answered(read_notifications(booking, administrator))["items"]

        response = resend(booking, administrator, failed["id"])
        assert response.status_code == status.HTTP_201_CREATED, response.text
        again = response.json()
        assert (again["status"], again["lastError"]) == ("FAILED", failed["lastError"])
        assert again["resendOf"] == failed["id"]

    def test_a_notification_that_was_sent_is_refused(
        self,
        booking: BookingClient,
        world: BookingWorld,
        administrator: UserAccount,
    ) -> None:
        booking.confirmed(world)
        (sent,) = answered(read_notifications(booking, administrator))["items"]
        refused = resend(booking, administrator, sent["id"])
        assert refused.status_code == status.HTTP_409_CONFLICT
        assert problem_code(refused) == "state-transition"
        assert problem_of(refused)["detail"] == ALREADY_SENT

    def test_a_notification_that_does_not_exist_is_not_found(
        self, booking: BookingClient, administrator: UserAccount
    ) -> None:
        refused = resend(booking, administrator, uuid4())
        assert refused.status_code == status.HTTP_404_NOT_FOUND
        assert problem_of(refused)["detail"] == "We could not find that notification."


class TestTheRefusals:
    """A refused parameter is named, and only an administrator may read or re-send."""

    @pytest.mark.parametrize(
        ("params", "field"),
        [
            ({"status": "LOST"}, "query.status"),
            ({"page": 0}, "query.page"),
            ({"pageSize": 101}, "query.pageSize"),
        ],
    )
    def test_a_value_that_cannot_be_read_is_refused_naming_it(
        self,
        booking: BookingClient,
        administrator: UserAccount,
        params: dict[str, object],
        field: str,
    ) -> None:
        assert refused_fields(read_notifications(booking, administrator, **params)) == {field}

    def test_a_key_that_is_not_a_key_is_refused_naming_it(
        self, booking: BookingClient, administrator: UserAccount
    ) -> None:
        assert refused_fields(resend(booking, administrator, "not-a-key")) == {"path.id"}

    @pytest.mark.parametrize("role", [UserRole.COUNTER_STAFF, UserRole.CUSTOMER])
    def test_anybody_but_an_administrator_is_refused(
        self, booking: BookingClient, session: Session, factory: Factory, role: UserRole
    ) -> None:
        account = factory.user(
            role=role, branch=factory.branch() if role is UserRole.COUNTER_STAFF else None
        )
        session.commit()
        assert read_notifications(booking, account).status_code == status.HTTP_403_FORBIDDEN
        assert resend(booking, account, uuid4()).status_code == status.HTTP_403_FORBIDDEN

    def test_a_caller_with_no_credential_is_refused(self, booking: BookingClient) -> None:
        assert booking.client.get(NOTIFICATIONS_PATH).status_code == status.HTTP_401_UNAUTHORIZED
        assert booking.client.post(resend_path(uuid4())).status_code == (
            status.HTTP_401_UNAUTHORIZED
        )
