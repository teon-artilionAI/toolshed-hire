"""The two logs of the admin console and the re-send, run against ports and nothing else.

The audit log is read through a query object, and the service turns a span of
business days into two instants in Cape Town, with both days included, and
refuses a span that ends before it begins. The notification log is read the
same way. A failed confirmation is sent again as a new notification through
the outbox and the dispatcher a confirmation uses, and the failed one is left
as it was. The unit of work is the in memory double from tests/support.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Final
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from app.application.audit_reads import (
    AuditEventPage,
    AuditLogRequest,
    AuditSearch,
    ReadAuditLog,
)
from app.application.notification.dispatcher import NotificationDispatcher
from app.application.notification.log import (
    NOTIFICATION_RESENT_ACTION,
    NotificationEntry,
    NotificationLogQueryRequest,
    NotificationPage,
    NotificationSearch,
    ReadNotificationLog,
)
from app.application.notification.resend import ResendCommand, ResendNotificationUseCase
from app.application.refusal import refused_parameter_of
from app.domain.enums import NotificationStatus, UserRole
from app.domain.errors import NotFound, StateTransitionError, ValidationFailure
from app.domain.identity import Actor
from app.infrastructure.notification import FakeEmailGateway
from tests.support.memory import InMemoryUnitOfWork, MemoryStore
from tests.support.memory_world import BookingDesk, build_memory_world, open_desk

CAPE_TOWN: Final[ZoneInfo] = ZoneInfo("Africa/Johannesburg")
ADMINISTRATOR: Final[Actor] = Actor(user_id=uuid4(), role=UserRole.ADMIN)
FAILURE: Final[str] = "The provider refused the message."


@dataclass
class AuditEvents:
    """An audit query object that keeps the search it was asked and finds nothing."""

    asked: list[AuditSearch] = field(default_factory=list)

    def page(self, search: AuditSearch) -> AuditEventPage:
        """Keep the search and answer with an empty page."""
        self.asked.append(search)
        return AuditEventPage(items=(), page=search.page, page_size=search.page_size, total=0)


@dataclass
class StoredNotifications:
    """A notification log over the committed notifications of an in memory store."""

    store: MemoryStore
    asked: list[NotificationSearch] = field(default_factory=list)
    answers: bool = True

    def page(self, search: NotificationSearch) -> NotificationPage:
        """Keep the search and answer with every notification, newest first."""
        self.asked.append(search)
        entries = sorted(
            (self._entry(key) for key in self.store.committed.notifications),
            key=lambda entry: entry.queued_at,
            reverse=True,
        )
        return NotificationPage(
            items=tuple(entries), page=search.page, page_size=search.page_size, total=len(entries)
        )

    def one(self, notification_id: UUID) -> NotificationEntry | None:
        """Return one committed notification, or None when told to find nothing."""
        if not self.answers or notification_id not in self.store.committed.notifications:
            return None
        return self._entry(notification_id)

    def _entry(self, notification_id: UUID) -> NotificationEntry:
        """Return a committed notification as the log shows it."""
        stored = self.store.committed.notifications[notification_id]
        resend_of = next(
            (
                (event.after_state or {}).get("resend_of")
                for event in self.store.committed.audit_events
                if event.action == NOTIFICATION_RESENT_ACTION
                and event.entity_id == notification_id
            ),
            None,
        )
        return NotificationEntry(
            id=stored.id,
            reservation_id=stored.reservation_id,
            reservation_reference=stored.reservation_reference,
            notification_type=stored.notification_type,
            recipient_email=stored.recipient_email,
            subject=stored.subject,
            status=stored.status,
            attempts=stored.attempts,
            last_error=stored.last_error,
            queued_at=stored.queued_at,
            sent_at=stored.sent_at,
            resend_of=UUID(str(resend_of)) if resend_of is not None else None,
        )


def a_request(**changes: object) -> AuditLogRequest:
    """Return a request for the first page of the whole log, changed as asked."""
    values: dict[str, object] = {
        "actor": ADMINISTRATOR,
        "entity_type": None,
        "entity_id": None,
        "action": None,
        "actor_user_id": None,
        "from_day": None,
        "to_day": None,
        "page": 1,
        "page_size": 20,
        **changes,
    }
    return AuditLogRequest(**values)


class TestTheAuditLog:
    """A span of business days becomes two instants, and every filter is passed on."""

    def test_both_days_of_the_span_are_included(self) -> None:
        events = AuditEvents()
        ReadAuditLog(events).page(a_request(from_day=date(2026, 3, 2), to_day=date(2026, 3, 4)))
        (search,) = events.asked
        assert search.occurred_from == datetime(2026, 3, 2, tzinfo=CAPE_TOWN)
        assert search.occurred_before == datetime(2026, 3, 5, tzinfo=CAPE_TOWN)

    def test_every_filter_is_passed_on_and_the_page_becomes_an_offset(self) -> None:
        events = AuditEvents()
        entity_id, actor_id = uuid4(), uuid4()
        ReadAuditLog(events).page(
            a_request(
                entity_type="charge",
                entity_id=entity_id,
                action="charge.waived",
                actor_user_id=actor_id,
                page=3,
            )
        )
        (search,) = events.asked
        assert (search.entity_type, search.entity_id, search.action, search.actor_user_id) == (
            "charge", entity_id, "charge.waived", actor_id
        )
        assert (search.occurred_from, search.occurred_before, search.offset) == (None, None, 40)

    def test_a_span_that_ends_before_it_begins_is_refused_naming_to(self) -> None:
        events = AuditEvents()
        with pytest.raises(ValidationFailure) as refused:
            ReadAuditLog(events).page(
                a_request(from_day=date(2026, 3, 4), to_day=date(2026, 3, 2))
            )
        assert refused_parameter_of(refused.value) == "to"
        assert events.asked == []

    def test_one_day_is_a_span_of_its_own(self) -> None:
        events = AuditEvents()
        ReadAuditLog(events).page(a_request(from_day=date(2026, 3, 2), to_day=date(2026, 3, 2)))
        (search,) = events.asked
        assert search.occurred_before == datetime(2026, 3, 3, tzinfo=CAPE_TOWN)


def failed_confirmation() -> tuple[BookingDesk, UUID]:
    """Confirm a booking whose confirmation the provider refuses, and return its key."""
    world = build_memory_world()
    desk = open_desk(world, gateway=FakeEmailGateway(failure_reason=FAILURE))
    desk.confirmed()
    (failed,) = world.store.committed.notifications.values()
    assert failed.status is NotificationStatus.FAILED
    return desk, failed.id


def resend(
    desk: BookingDesk, notification_id: UUID, *, gateway: FakeEmailGateway, answers: bool = True
) -> NotificationEntry:
    """Send a notification again as the administrator, through a dispatcher of its own."""
    store = desk.world.store
    dispatcher = NotificationDispatcher(InMemoryUnitOfWork(store), gateway, desk.clock)
    use_case = ResendNotificationUseCase(
        InMemoryUnitOfWork(store),
        desk.clock,
        dispatcher,
        StoredNotifications(store, answers=answers),
    )
    return use_case.execute(ResendCommand(actor=ADMINISTRATOR, notification_id=notification_id))


class TestTheResend:
    """A new notification is queued and sent, and the failed one is left as it was."""

    def test_a_failed_confirmation_is_sent_again_as_a_new_one(self) -> None:
        desk, failed_id = failed_confirmation()
        gateway = FakeEmailGateway()
        entry = resend(desk, failed_id, gateway=gateway)

        store = desk.world.store
        failed = store.committed.notifications[failed_id]
        assert (failed.status, failed.attempts, failed.last_error) == (
            NotificationStatus.FAILED, 1, FAILURE
        )
        assert entry.id != failed_id
        assert (entry.status, entry.resend_of, entry.attempts) == (
            NotificationStatus.SENT, failed_id, 1
        )
        assert (entry.recipient_email, entry.subject) == (failed.recipient_email, failed.subject)
        assert [message.to for message in gateway.sent] == [failed.recipient_email]
        (event,) = [
            e for e in store.committed.audit_events if e.action == NOTIFICATION_RESENT_ACTION
        ]
        assert (event.entity_id, event.actor_user_id) == (entry.id, ADMINISTRATOR.user_id)
        assert dict(event.after_state or {})["resend_of"] == str(failed_id)

    def test_a_resend_the_provider_refuses_is_failed_too_and_both_stay_in_the_log(self) -> None:
        desk, failed_id = failed_confirmation()
        entry = resend(desk, failed_id, gateway=FakeEmailGateway(failure_reason=FAILURE))
        assert (entry.status, entry.last_error) == (NotificationStatus.FAILED, FAILURE)
        log = StoredNotifications(desk.world.store).page(
            NotificationSearch(status=None, page=1, page_size=20)
        )
        assert log.total == 2

    def test_a_notification_that_was_sent_is_not_sent_again(self) -> None:
        desk, failed_id = failed_confirmation()
        sent = resend(desk, failed_id, gateway=FakeEmailGateway())
        with pytest.raises(StateTransitionError, match="already sent"):
            resend(desk, sent.id, gateway=FakeEmailGateway())

    def test_a_notification_that_does_not_exist_is_not_found(self) -> None:
        desk, _failed_id = failed_confirmation()
        with pytest.raises(NotFound, match="could not find that notification"):
            resend(desk, uuid4(), gateway=FakeEmailGateway())

    def test_a_resend_that_cannot_be_read_back_is_a_fault_in_the_data(self) -> None:
        desk, failed_id = failed_confirmation()
        with pytest.raises(LookupError, match="could not be read"):
            resend(desk, failed_id, gateway=FakeEmailGateway(), answers=False)


def test_the_notification_log_passes_the_status_and_the_page_on() -> None:
    log = StoredNotifications(build_memory_world().store)
    page = ReadNotificationLog(log).page(
        NotificationLogQueryRequest(
            actor=ADMINISTRATOR, status=NotificationStatus.FAILED, page=2, page_size=10
        )
    )
    (search,) = log.asked
    assert (search.status, search.page, search.page_size, search.offset) == (
        NotificationStatus.FAILED, 2, 10, 10
    )
    assert (page.total, page.items) == (0, ())
