"""The dispatcher, run against the in memory outbox.

The dispatcher sends what is queued and records what became of each message.
The rule these tests exist for is that it never raises. By the time it runs the
booking is committed, so a fault in the gateway or in the outbox is logged and
recorded and is never allowed to turn a successful booking into an error.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import uuid4

import pytest

from app.application.notification.dispatcher import (
    UNEXPECTED_FAULT_REASON,
    NotificationDispatcher,
)
from app.application.notification.ports import DeliveryReceipt, NotificationGateway
from app.domain.enums import NotificationStatus
from app.domain.notification import EmailMessage, Notification
from app.infrastructure.notification import FakeEmailGateway
from tests.support.clock import FixedClock
from tests.support.memory import InMemoryUnitOfWork, MemoryStore

QUEUED_AT: Final[datetime] = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
SENT_AT: Final[datetime] = datetime(2026, 3, 2, 8, 0, 5, tzinfo=UTC)
PROVIDER_FAILURE: Final[str] = "Resend answered 429 (Too Many Requests)."
SECRET_IN_A_FAULT: Final[str] = "made-up-resend-key-for-this-test"


class RaisingGateway:
    """A gateway that breaks its contract by raising instead of returning a receipt."""

    def send(self, message: EmailMessage) -> DeliveryReceipt:
        """Fail the way a defect fails."""
        raise RuntimeError(f"unexpected fault quoting {SECRET_IN_A_FAULT}")


class EmptyHandedGateway:
    """A gateway that reports an outcome with nothing attached to it."""

    def __init__(self, *, accepted: bool) -> None:
        """Choose which bare outcome to report."""
        self._accepted = accepted

    def send(self, message: EmailMessage) -> DeliveryReceipt:
        """Return a receipt with no message id and no reason."""
        return DeliveryReceipt(accepted=self._accepted)


def queue(store: MemoryStore, *, minutes_ago: int = 0) -> Notification:
    """Commit one queued confirmation into the store and return it."""
    notification = Notification.booking_confirmation(
        reservation_id=uuid4(),
        reservation_reference=f"TSH-R-26-{minutes_ago:06d}",
        recipient_email=f"customer{minutes_ago}@example.co.za",
        queued_at=QUEUED_AT - timedelta(minutes=minutes_ago),
    )
    with InMemoryUnitOfWork(store) as uow:
        uow.notifications.enqueue(notification)
        uow.commit()
    return notification


def dispatcher_for(store: MemoryStore, gateway: NotificationGateway) -> NotificationDispatcher:
    """Wire a dispatcher to the store, the given gateway and a fixed clock."""
    return NotificationDispatcher(InMemoryUnitOfWork(store), gateway, FixedClock(SENT_AT))


def stored(store: MemoryStore, notification: Notification) -> Notification:
    """Return the committed copy of a notification."""
    return store.committed.notifications[notification.id]


class TestSendingWhatIsQueued:
    """Each queued notification is sent once and its outcome is written down."""

    def test_nothing_queued_means_nothing_sent(self) -> None:
        store = MemoryStore()
        gateway = FakeEmailGateway()
        assert dispatcher_for(store, gateway).dispatch_due() == 0
        assert gateway.sent == []

    def test_a_delivered_notification_is_marked_sent_with_the_provider_id(self) -> None:
        store = MemoryStore()
        notification = queue(store)
        assert dispatcher_for(store, FakeEmailGateway()).dispatch_due() == 1
        kept = stored(store, notification)
        assert kept.status is NotificationStatus.SENT
        assert kept.provider_message_id == "fake-message-1"
        assert kept.sent_at == SENT_AT
        assert kept.attempts == 1

    def test_a_refused_notification_is_marked_failed_with_the_reason(self) -> None:
        store = MemoryStore()
        notification = queue(store)
        assert dispatcher_for(store, FakeEmailGateway(PROVIDER_FAILURE)).dispatch_due() == 0
        kept = stored(store, notification)
        assert kept.status is NotificationStatus.FAILED
        assert kept.last_error == PROVIDER_FAILURE
        assert kept.attempts == 1

    def test_the_message_carries_the_idempotency_key_of_its_notification(self) -> None:
        store = MemoryStore()
        notification = queue(store)
        gateway = FakeEmailGateway()
        dispatcher_for(store, gateway).dispatch_due()
        (message,) = gateway.sent
        assert message.idempotency_key == f"notification-{notification.id}"

    def test_the_oldest_are_sent_first_and_the_limit_is_kept(self) -> None:
        store = MemoryStore()
        newest = queue(store, minutes_ago=1)
        oldest = queue(store, minutes_ago=30)
        middle = queue(store, minutes_ago=10)
        gateway = FakeEmailGateway()
        assert dispatcher_for(store, gateway).dispatch_due(limit=2) == 2
        assert [message.to for message in gateway.sent] == [
            oldest.recipient_email,
            middle.recipient_email,
        ]
        assert stored(store, newest).status is NotificationStatus.QUEUED

    def test_a_failed_notification_is_not_sent_again_by_a_later_dispatch(self) -> None:
        """Sending a failed one again is a decision for a person, not for the next request."""
        store = MemoryStore()
        queue(store)
        gateway = FakeEmailGateway(PROVIDER_FAILURE)
        dispatcher = dispatcher_for(store, gateway)
        dispatcher.dispatch_due()
        dispatcher.dispatch_due()
        assert len(gateway.sent) == 1

    def test_an_acceptance_with_no_message_id_is_still_recorded_as_sent(self) -> None:
        store = MemoryStore()
        notification = queue(store)
        assert dispatcher_for(store, EmptyHandedGateway(accepted=True)).dispatch_due() == 1
        kept = stored(store, notification)
        assert kept.status is NotificationStatus.SENT
        assert kept.provider_message_id == "unknown"

    def test_a_failure_with_no_reason_is_recorded_with_one(self) -> None:
        store = MemoryStore()
        notification = queue(store)
        dispatcher_for(store, EmptyHandedGateway(accepted=False)).dispatch_due()
        kept = stored(store, notification)
        assert kept.status is NotificationStatus.FAILED
        assert kept.last_error == "The email gateway gave no reason for the failure."


class TestTheDispatcherNeverRaises:
    """The booking is already committed, so no fault here may reach the caller."""

    def test_a_gateway_that_raises_marks_the_notification_failed(self) -> None:
        store = MemoryStore()
        notification = queue(store)
        assert dispatcher_for(store, RaisingGateway()).dispatch_due() == 0
        kept = stored(store, notification)
        assert kept.status is NotificationStatus.FAILED
        assert kept.last_error == UNEXPECTED_FAULT_REASON

    def test_the_text_of_the_fault_is_not_stored_against_the_notification(self) -> None:
        store = MemoryStore()
        notification = queue(store)
        dispatcher_for(store, RaisingGateway()).dispatch_due()
        assert SECRET_IN_A_FAULT not in str(stored(store, notification).last_error)

    def test_a_gateway_fault_is_logged_with_its_traceback(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        store = MemoryStore()
        queue(store)
        with caplog.at_level(logging.ERROR):
            dispatcher_for(store, RaisingGateway()).dispatch_due()
        (record,) = [r for r in caplog.records if r.getMessage() == "notification.gateway_fault"]
        assert record.exc_info is not None

    def test_one_broken_send_does_not_stop_the_rest_of_the_batch(self) -> None:
        store = MemoryStore()
        first = queue(store, minutes_ago=20)
        second = queue(store, minutes_ago=10)

        class FailsOnce:
            """Raises for the first message and accepts every one after it."""

            def __init__(self) -> None:
                """Start with no calls made."""
                self.calls = 0

            def send(self, message: EmailMessage) -> DeliveryReceipt:
                """Break on the first call only."""
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("the first send broke")
                return DeliveryReceipt.delivered("made-up-provider-message-id")

        assert dispatcher_for(store, FailsOnce()).dispatch_due() == 1
        assert stored(store, first).status is NotificationStatus.FAILED
        assert stored(store, second).status is NotificationStatus.SENT

    def test_an_outbox_that_cannot_be_read_sends_nothing_and_raises_nothing(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        store = MemoryStore()
        notification = queue(store)
        store.fail_outbox_read = True
        gateway = FakeEmailGateway()
        with caplog.at_level(logging.ERROR):
            assert dispatcher_for(store, gateway).dispatch_due() == 0
        assert gateway.sent == []
        assert stored(store, notification).status is NotificationStatus.QUEUED
        assert "notification.outbox_read_failed" in [r.getMessage() for r in caplog.records]

    def test_an_outcome_that_cannot_be_written_leaves_the_notification_queued(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """It is sent again later, and the idempotency key stops a second delivery."""
        store = MemoryStore()
        notification = queue(store)
        store.fail_outbox_write = True
        gateway = FakeEmailGateway()
        with caplog.at_level(logging.ERROR):
            dispatcher_for(store, gateway).dispatch_due()
        assert len(gateway.sent) == 1
        assert stored(store, notification).status is NotificationStatus.QUEUED
        assert "notification.outcome_not_recorded" in [r.getMessage() for r in caplog.records]
