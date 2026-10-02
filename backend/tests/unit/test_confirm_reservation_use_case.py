"""The use case that confirms a held reservation, run against ports and nothing else.

Confirmation happens inside the hold, needs every unit held (BR-08) and needs
a verified email address unless staff confirm at the counter (BR-47). It is
also the moment the customer is told, so the booking confirmation is queued
here, in the same transaction, and sent after the commit (BR-19). Holding
sends nothing. That moved in this change, and the first class below pins it.

A hold that has run out is lapsed and its units released, and that lapse is
kept even though the confirmation is refused (BR-13).

The unit of work is the in memory double from tests/support, and the clock
stands still on the second of March 2026 until a test moves it.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final
from uuid import uuid4

import pytest

from app.application.booking.access import RESERVATION_CONFIRMED_ACTION
from app.application.notification.ports import DeliveryReceipt
from app.domain.enums import (
    AccountStatus,
    NotificationStatus,
    ReleaseReason,
    ReservationStatus,
    UserRole,
)
from app.domain.errors import EmailNotVerifiedError, StateTransitionError
from app.domain.identity import Actor, CustomerProfile
from app.domain.notification import EmailMessage
from app.domain.states import HOLD_DURATION
from app.infrastructure.notification import FakeEmailGateway
from tests.support.clock import DEFAULT_INSTANT
from tests.support.memory import COMMIT, MemoryStore, StoreFault
from tests.support.memory_world import CUSTOMER_EMAIL, build_memory_world, open_desk

SEND: Final[str] = "send"
PROVIDER_FAILURE: Final[str] = "Resend answered 500 (Internal Server Error)."
JUST_PAST_THE_HOLD: Final[timedelta] = HOLD_DURATION + timedelta(seconds=1)


class JournallingGateway:
    """A gateway that writes each send into the store's journal of commits."""

    def __init__(self, store: MemoryStore) -> None:
        """Bind the gateway to the journal it writes into."""
        self._store = store

    def send(self, message: EmailMessage) -> DeliveryReceipt:
        """Note the send beside the commits, and accept the message."""
        self._store.journal.append(SEND)
        return DeliveryReceipt.delivered("journalled-message")


class TestTheConfirmationIsQueuedAtConfirmationAndNotBefore:
    """Holding writes no notification row. Confirming writes exactly one."""

    def test_a_held_reservation_has_no_notification(self) -> None:
        world = build_memory_world()
        open_desk(world).held()
        assert world.store.committed.notifications == {}

    def test_a_confirmed_reservation_has_exactly_one(self) -> None:
        world = build_memory_world()
        confirmed = open_desk(world).confirmed()
        (notification,) = world.store.committed.notifications.values()
        assert notification.reservation_id == confirmed.detail.id
        assert notification.reservation_reference == confirmed.detail.reference
        assert notification.recipient_email == CUSTOMER_EMAIL

    def test_the_confirmation_is_sent_only_after_the_confirmation_is_committed(self) -> None:
        world = build_memory_world()
        desk = open_desk(world, gateway=JournallingGateway(world.store))
        held = desk.held()
        commits_before = len(world.store.journal)
        desk.confirm.execute(desk.command_for(held))
        assert world.store.journal[commits_before:] == [COMMIT, SEND, COMMIT]

    def test_the_sent_notification_is_marked_sent(self) -> None:
        world = build_memory_world()
        gateway = FakeEmailGateway()
        open_desk(world, gateway=gateway).confirmed()
        (notification,) = world.store.committed.notifications.values()
        assert notification.status is NotificationStatus.SENT
        assert [message.to for message in gateway.sent] == [CUSTOMER_EMAIL]

    def test_a_provider_failure_leaves_the_booking_confirmed(self) -> None:
        world = build_memory_world()
        confirmed = open_desk(world, gateway=FakeEmailGateway(PROVIDER_FAILURE)).confirmed()
        assert confirmed.detail.status is ReservationStatus.CONFIRMED
        (notification,) = world.store.committed.notifications.values()
        assert notification.status is NotificationStatus.FAILED
        assert notification.last_error == PROVIDER_FAILURE
        assert world.stored(confirmed.detail.id).status is ReservationStatus.CONFIRMED

    def test_a_refused_confirmation_queues_nothing(self) -> None:
        world = build_memory_world(email_verified=False)
        desk = open_desk(world)
        held = desk.held()
        with pytest.raises(EmailNotVerifiedError):
            desk.confirm.execute(desk.command_for(held))
        assert world.store.committed.notifications == {}


class TestConfirmingInsideTheHold:
    """The status, the dates of the move and the audit event."""

    def test_a_confirmed_reservation_keeps_its_units_and_loses_its_expiry(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        held = desk.held()
        desk.clock.advance(timedelta(minutes=10))
        confirmed = desk.confirm.execute(desk.command_for(held))
        assert confirmed.detail.status is ReservationStatus.CONFIRMED
        assert confirmed.detail.hold_expires_at is None
        assert confirmed.detail.confirmed_at == DEFAULT_INSTANT + timedelta(minutes=10)
        assert confirmed.detail.lines[0].allocated_count == 1

    def test_a_hold_can_be_confirmed_at_the_very_instant_it_expires(self) -> None:
        desk = open_desk(build_memory_world())
        held = desk.held()
        desk.clock.advance(HOLD_DURATION)
        assert desk.confirm.execute(desk.command_for(held)).detail.status is (
            ReservationStatus.CONFIRMED
        )

    def test_the_confirmation_writes_one_audit_event(self) -> None:
        world = build_memory_world()
        confirmed = open_desk(world).confirmed()
        event = world.store.committed.audit_events[-1]
        assert event.action == RESERVATION_CONFIRMED_ACTION
        assert event.entity_id == confirmed.detail.id
        assert event.before_state is not None
        assert event.before_state["status"] == "HELD"
        assert event.after_state is not None
        assert event.after_state["status"] == "CONFIRMED"
        assert event.after_state["confirmed_on_behalf"] is False

    def test_a_confirmation_whose_audit_event_cannot_be_written_does_not_happen(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        held = desk.held()
        world.store.fail_audit = True
        with pytest.raises(StoreFault):
            desk.confirm.execute(desk.command_for(held))
        assert world.stored(held.detail.id).status is ReservationStatus.HELD
        assert world.store.committed.notifications == {}

    def test_a_draft_cannot_be_confirmed(self) -> None:
        desk = open_desk(build_memory_world())
        draft = desk.drafted()
        with pytest.raises(StateTransitionError) as refusal:
            desk.confirm.execute(desk.command_for(draft))
        assert refusal.value.detail == {"from_status": "DRAFT", "to_status": "CONFIRMED"}

    def test_a_confirmed_reservation_cannot_be_confirmed_again(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        confirmed = desk.confirmed()
        with pytest.raises(StateTransitionError):
            desk.confirm.execute(desk.command_for(confirmed))
        assert len(world.store.committed.notifications) == 1


class TestTheVerifiedEmailRule:
    """A customer needs a verified address. Staff at the counter satisfy the rule."""

    def test_an_unverified_customer_cannot_confirm_and_stays_on_hold(self) -> None:
        world = build_memory_world(email_verified=False)
        desk = open_desk(world)
        held = desk.held()
        with pytest.raises(EmailNotVerifiedError) as refusal:
            desk.confirm.execute(desk.command_for(held))
        assert refusal.value.rule == "BR-47"
        assert refusal.value.message.startswith("Please verify your email address")
        stored = world.stored(held.detail.id)
        assert stored.status is ReservationStatus.HELD
        assert stored.is_fully_allocated()

    @pytest.mark.parametrize("role", [UserRole.COUNTER_STAFF, UserRole.ADMIN])
    def test_staff_confirm_for_an_unverified_customer(self, role: UserRole) -> None:
        world = build_memory_world(email_verified=False)
        desk = open_desk(world)
        held = desk.held()
        branch_id = world.branch.id if role is UserRole.COUNTER_STAFF else None
        member_of_staff = Actor(user_id=uuid4(), role=role, branch_id=branch_id)
        confirmed = desk.confirm.execute(desk.command_for(held, actor=member_of_staff))
        assert confirmed.detail.status is ReservationStatus.CONFIRMED
        event = world.store.committed.audit_events[-1]
        assert event.after_state is not None
        assert event.after_state["confirmed_on_behalf"] is True

    def test_a_walk_in_confirmed_at_the_counter_is_sent_nothing(self) -> None:
        world = build_memory_world()
        walk_in = CustomerProfile(
            id=uuid4(),
            user_account_id=None,
            display_name="Thabo Mokoena",
            account_status=AccountStatus.ACTIVE,
            email=None,
        )
        world.store.walk_ins.append(walk_in)
        assistant = world.assistant()
        desk = open_desk(world)
        draft = desk.drafted(
            world.draft_command(actor=assistant, customer_profile_id=walk_in.id)
        )
        held = desk.hold.execute(desk.command_for(draft, actor=assistant))
        confirmed = desk.confirm.execute(desk.command_for(held, actor=assistant))
        assert confirmed.detail.status is ReservationStatus.CONFIRMED
        assert world.store.committed.notifications == {}


class TestAHoldThatHasRunOut:
    """It cannot be confirmed, and its units are free again whatever happens next."""

    def test_confirming_after_the_hold_has_run_out_is_refused(self) -> None:
        desk = open_desk(build_memory_world())
        held = desk.held()
        desk.clock.advance(JUST_PAST_THE_HOLD)
        with pytest.raises(StateTransitionError) as refusal:
            desk.confirm.execute(desk.command_for(held))
        assert refusal.value.detail == {"from_status": "EXPIRED", "to_status": "CONFIRMED"}
        assert refusal.value.message == "This reservation has expired, so it cannot be confirmed."

    def test_the_refused_confirmation_still_leaves_the_reservation_expired(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        held = desk.held()
        desk.clock.advance(JUST_PAST_THE_HOLD)
        with pytest.raises(StateTransitionError):
            desk.confirm.execute(desk.command_for(held))
        stored = world.stored(held.detail.id)
        assert stored.status is ReservationStatus.EXPIRED
        assert stored.hold_expires_at is None
        (allocation,) = stored.lines[0].allocations
        assert allocation.release_reason is ReleaseReason.EXPIRED
        assert world.store.committed.notifications == {}

    def test_the_units_of_the_expired_hold_can_be_held_by_somebody_else(self) -> None:
        world = build_memory_world()
        desk = open_desk(world)
        held = desk.held()
        desk.clock.advance(JUST_PAST_THE_HOLD)
        with pytest.raises(StateTransitionError):
            desk.confirm.execute(desk.command_for(held))
        assert desk.held().detail.status is ReservationStatus.HELD
