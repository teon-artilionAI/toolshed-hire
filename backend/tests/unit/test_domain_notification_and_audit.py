"""The notification and the audit event, with no database anywhere.

A notification is the record of one booking confirmation. These tests pin what
it turns into when it is sent and how it records an outcome. The audit event is
pinned beside it, because both are evidence. Each has to say enough to be
useful and must refuse to be built half filled in.
"""

from __future__ import annotations

from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Final
from uuid import uuid4

import pytest

from app.domain.audit import AuditEvent
from app.domain.enums import (
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    UserRole,
)
from app.domain.errors import (
    AccountOnHoldError,
    AllocationConflictError,
    BranchScopeError,
    DomainError,
    StateTransitionError,
)
from app.domain.notification import (
    FAILURE_REASON_MAX_LENGTH,
    PROVIDER_MESSAGE_ID_MAX_LENGTH,
    Notification,
)

REFERENCE: Final[str] = "TSH-R-26-000124"
RECIPIENT: Final[str] = "nomsa.dlamini@example.co.za"
QUEUED_AT: Final[datetime] = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
SENT_AT: Final[datetime] = datetime(2026, 3, 2, 8, 0, 3, tzinfo=UTC)
PROVIDER_MESSAGE_ID: Final[str] = "made-up-provider-message-id"


def a_queued_confirmation() -> Notification:
    """Return the confirmation queued for the worked example booking."""
    return Notification.booking_confirmation(
        reservation_id=uuid4(),
        reservation_reference=REFERENCE,
        recipient_email=RECIPIENT,
        queued_at=QUEUED_AT,
    )


class TestAQueuedConfirmation:
    """What a booking writes into the outbox."""

    def test_it_is_a_queued_email_about_a_booking_confirmation(self) -> None:
        notification = a_queued_confirmation()
        assert notification.status is NotificationStatus.QUEUED
        assert notification.notification_type is NotificationType.BOOKING_CONFIRMATION
        assert notification.channel is NotificationChannel.EMAIL
        assert notification.attempts == 0
        assert notification.queued_at == QUEUED_AT

    def test_the_subject_quotes_the_booking_reference(self) -> None:
        assert REFERENCE in a_queued_confirmation().subject

    def test_a_blank_recipient_is_refused(self) -> None:
        with pytest.raises(ValueError, match="no recipient address"):
            Notification.booking_confirmation(
                reservation_id=uuid4(),
                reservation_reference=REFERENCE,
                recipient_email="   ",
                queued_at=QUEUED_AT,
            )


class TestTheMessageANotificationTurnsInto:
    """The provider is given an address and a reference, and nothing else."""

    def test_the_message_goes_to_the_recipient_with_the_stored_subject(self) -> None:
        notification = a_queued_confirmation()
        message = notification.to_message()
        assert message.to == RECIPIENT
        assert message.subject == notification.subject

    def test_the_body_quotes_the_booking_reference(self) -> None:
        assert REFERENCE in a_queued_confirmation().to_message().text_body

    def test_the_idempotency_key_is_derived_from_the_notification_id(self) -> None:
        notification = a_queued_confirmation()
        assert notification.to_message().idempotency_key == f"notification-{notification.id}"

    def test_the_same_notification_always_produces_the_same_key(self) -> None:
        notification = a_queued_confirmation()
        first = notification.to_message().idempotency_key
        notification.mark_failed("Resend answered 500 (Internal Server Error).")
        assert notification.to_message().idempotency_key == first

    def test_two_notifications_never_share_a_key(self) -> None:
        first = a_queued_confirmation().to_message().idempotency_key
        second = a_queued_confirmation().to_message().idempotency_key
        assert first != second


class TestRecordingAnOutcome:
    """A send either worked or it did not, and the notification says which."""

    def test_a_successful_send_records_the_provider_id_and_the_time(self) -> None:
        notification = a_queued_confirmation()
        notification.mark_sent(PROVIDER_MESSAGE_ID, SENT_AT)
        assert notification.status is NotificationStatus.SENT
        assert notification.provider_message_id == PROVIDER_MESSAGE_ID
        assert notification.sent_at == SENT_AT
        assert notification.attempts == 1

    def test_a_failed_send_records_the_reason(self) -> None:
        notification = a_queued_confirmation()
        notification.mark_failed("Resend answered 429 (Too Many Requests).")
        assert notification.status is NotificationStatus.FAILED
        assert notification.last_error == "Resend answered 429 (Too Many Requests)."
        assert notification.sent_at is None
        assert notification.attempts == 1

    def test_a_send_that_works_after_a_failure_clears_the_old_reason(self) -> None:
        notification = a_queued_confirmation()
        notification.mark_failed("Resend did not answer within 5 seconds.")
        notification.mark_sent(PROVIDER_MESSAGE_ID, SENT_AT)
        assert notification.status is NotificationStatus.SENT
        assert notification.last_error is None
        assert notification.attempts == 2

    def test_a_reason_longer_than_the_notification_keeps_is_cut_to_fit(self) -> None:
        notification = a_queued_confirmation()
        notification.mark_failed("x" * (FAILURE_REASON_MAX_LENGTH + 50))
        assert notification.last_error is not None
        assert len(notification.last_error) == FAILURE_REASON_MAX_LENGTH

    def test_a_provider_id_longer_than_the_notification_keeps_is_cut_to_fit(self) -> None:
        notification = a_queued_confirmation()
        notification.mark_sent("i" * (PROVIDER_MESSAGE_ID_MAX_LENGTH + 20), SENT_AT)
        assert notification.provider_message_id is not None
        assert len(notification.provider_message_id) == PROVIDER_MESSAGE_ID_MAX_LENGTH


class TestAnAuditEvent:
    """BR-49. Who did what to which record, or it is not an audit event."""

    def test_an_event_carries_the_actor_the_entity_and_the_action(self) -> None:
        actor_id, entity_id, request_id = uuid4(), uuid4(), uuid4()
        event = AuditEvent(
            entity_type="reservation",
            entity_id=entity_id,
            action="reservation.held",
            occurred_at=QUEUED_AT,
            actor_user_id=actor_id,
            actor_role=UserRole.COUNTER_STAFF,
            after_state={"status": "HELD", "asset_tags": ["TSH-DR-0042"]},
            request_id=request_id,
            ip_address=ip_address("203.0.113.9"),
        )
        assert event.actor_user_id == actor_id
        assert event.actor_role is UserRole.COUNTER_STAFF
        assert event.entity_id == entity_id
        assert event.before_state is None
        assert event.request_id == request_id

    def test_an_event_with_no_human_actor_is_allowed(self) -> None:
        """The sweep that expires holds has nobody to name."""
        event = AuditEvent(
            entity_type="reservation",
            entity_id=uuid4(),
            action="reservation.expired",
            occurred_at=QUEUED_AT,
        )
        assert event.actor_user_id is None
        assert event.actor_role is None

    def test_an_actor_without_a_role_is_refused(self) -> None:
        with pytest.raises(ValueError, match="half an actor"):
            AuditEvent(
                entity_type="reservation",
                entity_id=uuid4(),
                action="reservation.held",
                occurred_at=QUEUED_AT,
                actor_user_id=uuid4(),
            )

    def test_a_role_without_an_actor_is_refused(self) -> None:
        with pytest.raises(ValueError, match="half an actor"):
            AuditEvent(
                entity_type="reservation",
                entity_id=uuid4(),
                action="reservation.held",
                occurred_at=QUEUED_AT,
                actor_role=UserRole.ADMIN,
            )

    @pytest.mark.parametrize(("entity_type", "action"), [("", "reservation.held"), ("x", " ")])
    def test_a_blank_entity_type_or_action_is_refused(
        self, entity_type: str, action: str
    ) -> None:
        with pytest.raises(ValueError, match="blank entity type or action"):
            AuditEvent(
                entity_type=entity_type, entity_id=uuid4(), action=action, occurred_at=QUEUED_AT
            )


class TestTheErrorsTheDesignDocumentNames:
    """Each is a domain error with a stable slug and structured detail."""

    def test_every_one_of_them_is_a_domain_error(self) -> None:
        for error in (
            AllocationConflictError("no unit"),
            StateTransitionError("no", from_status="HELD", to_status="COLLECTED"),
            BranchScopeError("wrong branch"),
            AccountOnHoldError("on hold"),
        ):
            assert isinstance(error, DomainError)

    def test_a_state_transition_error_names_both_statuses(self) -> None:
        error = StateTransitionError(
            "A held reservation cannot be collected.", from_status="HELD", to_status="COLLECTED"
        )
        assert error.from_status == "HELD"
        assert error.to_status == "COLLECTED"
        assert error.detail == {"from_status": "HELD", "to_status": "COLLECTED"}

    def test_an_allocation_conflict_leaves_out_what_it_was_not_told(self) -> None:
        error = AllocationConflictError(
            "no unit", period="[2026-03-09,2026-03-12)", available_quantity=0
        )
        assert error.detail == {"period": "[2026-03-09,2026-03-12)", "available_quantity": 0}

    def test_the_slugs_are_distinct(self) -> None:
        slugs = {
            AllocationConflictError.code,
            StateTransitionError.code,
            BranchScopeError.code,
            AccountOnHoldError.code,
        }
        assert len(slugs) == 4
