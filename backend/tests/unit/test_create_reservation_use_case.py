"""The reservation use case, run against ports and nothing else.

There is no database here and no HTTP. The use case is handed an in memory unit
of work, a clock that stands still and a fake email gateway, which is only
possible because it depends on ports. What these tests pin is the order of
things. The booking, its audit event and its queued confirmation are committed
together or not at all, and the confirmation is sent only after that commit.

What the use case refuses is in test_create_reservation_refusals.py. The same
behaviour is proved against real transactions in
tests/component/test_booking_unit_of_work.py and, on PostgreSQL, in
tests/integration/test_booking_transaction.py.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from ipaddress import ip_address
from typing import Final
from uuid import UUID, uuid4

import pytest

from app.application.booking.create_reservation import RESERVATION_HELD_ACTION
from app.application.notification.ports import DeliveryReceipt
from app.domain.enums import NotificationStatus, ReservationStatus, UserRole
from app.domain.identity import Actor
from app.domain.notification import EmailMessage
from app.domain.period import BookingPeriod
from app.infrastructure.notification import FakeEmailGateway
from app.request_context import RequestContext, bind_request_context, release_request_context
from tests.support.clock import FixedClock
from tests.support.memory import COMMIT, MemoryStore, StoreFault
from tests.support.memory_world import CUSTOMER_EMAIL, build_memory_world, wire_use_case

FIRST_HIRE: Final[BookingPeriod] = BookingPeriod(date(2026, 3, 9), date(2026, 3, 12))
REQUEST_ID: Final[str] = "6f1c2b9e-3d4a-4c5b-8e7f-0a1b2c3d4e5f"
CLIENT_ADDRESS: Final[str] = "203.0.113.9"
PROVIDER_FAILURE: Final[str] = "Resend answered 500 (Internal Server Error)."
SEND: Final[str] = "send"


class JournallingGateway:
    """A gateway that notes when it was called and what the store held at that moment."""

    def __init__(self, store: MemoryStore) -> None:
        """Watch the store the booking commits into."""
        self._store = store
        self.reservations_committed_at_send: int | None = None
        self.statuses_at_send: list[NotificationStatus] = []

    def send(self, message: EmailMessage) -> DeliveryReceipt:
        """Record the committed state at the moment of the send, then accept."""
        self._store.journal.append(SEND)
        self.reservations_committed_at_send = len(self._store.committed.reservations)
        self.statuses_at_send = [
            notification.status for notification in self._store.committed.notifications.values()
        ]
        return DeliveryReceipt.delivered("made-up-provider-message-id")


class TestABookingIsCommittedWhole:
    """One reservation, its line, its allocations, its audit event and its notification."""

    def test_the_view_names_the_reference_the_line_and_the_unit_held(self) -> None:
        world = build_memory_world()
        use_case = wire_use_case(world)
        view = use_case.execute(world.command(FIRST_HIRE))
        assert view.reference == "TSH-R-26-000124"
        assert view.status is ReservationStatus.HELD
        assert [item.asset_tag for item in view.allocated] == ["TSH-DR-0001"]

    def test_the_reservation_is_stored_held_against_the_customers_profile(self) -> None:
        world = build_memory_world()
        use_case = wire_use_case(world)
        view = use_case.execute(world.command(FIRST_HIRE))
        (reservation,) = world.store.committed.reservations
        assert reservation.id == view.reservation_id
        assert reservation.customer_profile_id == world.profile.id
        assert reservation.created_by_user_id == world.customer_account_id
        assert reservation.period == FIRST_HIRE

    def test_the_aggregate_holds_the_allocations_it_was_given(self) -> None:
        world = build_memory_world(asset_count=3)
        use_case = wire_use_case(world)
        use_case.execute(world.command(FIRST_HIRE, quantity=2))
        (reservation,) = world.store.committed.reservations
        assert reservation.is_fully_allocated()
        assert len(world.store.committed.allocations) == 2

    def test_units_are_held_in_asset_tag_order(self) -> None:
        world = build_memory_world(asset_count=3)
        use_case = wire_use_case(world)
        view = use_case.execute(world.command(FIRST_HIRE, quantity=2))
        assert [item.asset_tag for item in view.allocated] == ["TSH-DR-0001", "TSH-DR-0002"]

    def test_the_hold_is_stamped_with_the_clock_and_not_the_wall_clock(self) -> None:
        world = build_memory_world()
        clock = FixedClock(datetime(2026, 3, 4, 14, 15, tzinfo=UTC))
        use_case = wire_use_case(world, clock=clock)
        use_case.execute(world.command(FIRST_HIRE))
        (allocation,) = world.store.committed.allocations
        assert allocation.allocated_at == clock.instant

    def test_everything_is_kept_by_one_commit(self) -> None:
        world = build_memory_world()
        use_case = wire_use_case(world, gateway=JournallingGateway(world.store))
        use_case.execute(world.command(FIRST_HIRE))
        # One commit for the booking. The second is the outcome of the send.
        assert world.store.journal == [COMMIT, SEND, COMMIT]


class TestTheAuditEvent:
    """BR-49. A state change leaves exactly one event, in the same transaction."""

    def test_a_booking_leaves_exactly_one_event_for_the_reservation(self) -> None:
        world = build_memory_world()
        use_case = wire_use_case(world)
        view = use_case.execute(world.command(FIRST_HIRE))
        (event,) = world.store.committed.audit_events
        assert event.action == RESERVATION_HELD_ACTION == "reservation.held"
        assert event.entity_type == "reservation"
        assert event.entity_id == view.reservation_id

    def test_the_event_names_the_actor_and_the_role_held_at_the_time(self) -> None:
        world = build_memory_world()
        assistant = Actor(user_id=uuid4(), role=UserRole.COUNTER_STAFF)
        use_case = wire_use_case(world)
        use_case.execute(world.command(FIRST_HIRE, actor=assistant))
        (event,) = world.store.committed.audit_events
        assert event.actor_user_id == assistant.user_id
        assert event.actor_role is UserRole.COUNTER_STAFF

    def test_the_booking_names_the_actor_as_its_creator(self) -> None:
        world = build_memory_world()
        assistant = Actor(user_id=uuid4(), role=UserRole.COUNTER_STAFF)
        use_case = wire_use_case(world)
        use_case.execute(world.command(FIRST_HIRE, actor=assistant))
        (reservation,) = world.store.committed.reservations
        assert reservation.created_by_user_id == assistant.user_id

    def test_a_creation_has_no_before_state_and_records_what_was_set(self) -> None:
        world = build_memory_world()
        use_case = wire_use_case(world)
        view = use_case.execute(world.command(FIRST_HIRE))
        (event,) = world.store.committed.audit_events
        assert event.before_state is None
        assert event.after_state == {
            "status": "HELD",
            "reference": view.reference,
            "customer_profile_id": str(world.profile.id),
            "branch_id": str(world.branch.id),
            "start_date": "2026-03-09",
            "end_date": "2026-03-12",
            "product_model_id": str(world.product_model.id),
            "quantity": 1,
            "asset_tags": ["TSH-DR-0001"],
        }

    def test_the_event_carries_the_request_id_and_the_client_address(self) -> None:
        world = build_memory_world()
        use_case = wire_use_case(world)
        token = bind_request_context(
            RequestContext(request_id=REQUEST_ID, client_address=ip_address(CLIENT_ADDRESS))
        )
        try:
            use_case.execute(world.command(FIRST_HIRE))
        finally:
            release_request_context(token)
        (event,) = world.store.committed.audit_events
        assert event.request_id == UUID(REQUEST_ID)
        assert str(event.ip_address) == CLIENT_ADDRESS

    def test_outside_a_request_the_event_carries_neither(self) -> None:
        world = build_memory_world()
        use_case = wire_use_case(world)
        use_case.execute(world.command(FIRST_HIRE))
        (event,) = world.store.committed.audit_events
        assert event.request_id is None
        assert event.ip_address is None


class TestAnOperationThatCannotBeAuditedDoesNotHappen:
    """If the audit write fails, the booking fails and nothing is committed."""

    def test_the_fault_reaches_the_caller(self) -> None:
        world = build_memory_world()
        world.store.fail_audit = True
        use_case = wire_use_case(world)
        with pytest.raises(StoreFault):
            use_case.execute(world.command(FIRST_HIRE))

    def test_no_reservation_no_allocation_and_no_notification_are_kept(self) -> None:
        world = build_memory_world()
        world.store.fail_audit = True
        use_case = wire_use_case(world)
        with pytest.raises(StoreFault):
            use_case.execute(world.command(FIRST_HIRE))
        committed = world.store.committed
        assert committed.reservations == []
        assert committed.allocations == []
        assert committed.notifications == {}
        assert world.store.journal == []

    def test_nothing_is_sent(self) -> None:
        world = build_memory_world()
        world.store.fail_audit = True
        gateway = FakeEmailGateway()
        use_case = wire_use_case(world, gateway=gateway)
        with pytest.raises(StoreFault):
            use_case.execute(world.command(FIRST_HIRE))
        assert gateway.sent == []

    def test_the_unit_is_still_free_for_the_next_booking(self) -> None:
        world = build_memory_world()
        world.store.fail_audit = True
        use_case = wire_use_case(world)
        with pytest.raises(StoreFault):
            use_case.execute(world.command(FIRST_HIRE))
        world.store.fail_audit = False
        view = use_case.execute(world.command(FIRST_HIRE))
        assert [item.asset_tag for item in view.allocated] == ["TSH-DR-0001"]


class TestTheConfirmationIsQueuedWithTheBookingAndSentAfterIt:
    """BR-19. The outbox row commits with the booking, and dispatch follows the commit."""

    def test_the_send_happens_after_the_booking_is_committed(self) -> None:
        world = build_memory_world()
        gateway = JournallingGateway(world.store)
        use_case = wire_use_case(world, gateway=gateway)
        use_case.execute(world.command(FIRST_HIRE))
        assert world.store.journal.index(COMMIT) < world.store.journal.index(SEND)
        assert gateway.reservations_committed_at_send == 1

    def test_the_notification_was_committed_queued_before_it_was_sent(self) -> None:
        world = build_memory_world()
        gateway = JournallingGateway(world.store)
        use_case = wire_use_case(world, gateway=gateway)
        use_case.execute(world.command(FIRST_HIRE))
        assert gateway.statuses_at_send == [NotificationStatus.QUEUED]

    def test_the_message_goes_to_the_customers_account_address(self) -> None:
        world = build_memory_world()
        gateway = FakeEmailGateway()
        use_case = wire_use_case(world, gateway=gateway)
        view = use_case.execute(world.command(FIRST_HIRE))
        (message,) = gateway.sent_to(CUSTOMER_EMAIL)
        assert view.reference in message.subject
        assert view.reference in message.text_body

    def test_a_delivered_confirmation_is_marked_sent_with_the_provider_id(self) -> None:
        world = build_memory_world()
        use_case = wire_use_case(world)
        view = use_case.execute(world.command(FIRST_HIRE))
        (notification,) = world.store.committed.notifications.values()
        assert notification.reservation_id == view.reservation_id
        assert notification.status is NotificationStatus.SENT
        assert notification.provider_message_id == "fake-message-1"
        assert notification.sent_at is not None
        assert notification.attempts == 1

    def test_a_provider_failure_marks_it_failed_with_the_reason(self) -> None:
        world = build_memory_world()
        use_case = wire_use_case(world, gateway=FakeEmailGateway(PROVIDER_FAILURE))
        use_case.execute(world.command(FIRST_HIRE))
        (notification,) = world.store.committed.notifications.values()
        assert notification.status is NotificationStatus.FAILED
        assert notification.last_error == PROVIDER_FAILURE
        assert notification.sent_at is None

    def test_a_provider_failure_leaves_the_booking_exactly_as_committed(self) -> None:
        world = build_memory_world()
        use_case = wire_use_case(world, gateway=FakeEmailGateway(PROVIDER_FAILURE))
        view = use_case.execute(world.command(FIRST_HIRE))
        committed = world.store.committed
        assert [reservation.id for reservation in committed.reservations] == [view.reservation_id]
        assert len(committed.allocations) == 1
        assert len(committed.audit_events) == 1

    def test_a_customer_with_no_address_gets_no_notification(self) -> None:
        world = build_memory_world(customer_email=None)
        gateway = FakeEmailGateway()
        use_case = wire_use_case(world, gateway=gateway)
        use_case.execute(world.command(FIRST_HIRE))
        assert world.store.committed.notifications == {}
        assert gateway.sent == []
        assert len(world.store.committed.reservations) == 1
