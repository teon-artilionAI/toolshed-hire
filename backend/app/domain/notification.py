"""The notification entity and the message it turns into (BR-19).

A notification is the record of one outbound booking confirmation. It is
written `QUEUED` in the same transaction as the booking it belongs to and sent
only after that transaction commits, so an email is never sent for a booking
that was rolled back and never lost for one that was kept.

The row stores the recipient and the subject and not the body. The body is
rendered here from the booking reference when the message is sent, which means
the email provider only ever receives an address and a reference.

A notification that failed is sent again by a new one, which `resent` builds
for the same booking and address, and never by changing the one that failed,
so the log keeps both (US-36).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Final
from uuid import UUID, uuid4

from app.domain.enums import NotificationChannel, NotificationStatus, NotificationType
from app.domain.errors import StateTransitionError

# The longest failure reason a notification keeps. A reason is a short phrase
# for the person who decides whether to send again, never a provider response.
FAILURE_REASON_MAX_LENGTH: Final[int] = 300
# The longest provider message id a notification keeps.
PROVIDER_MESSAGE_ID_MAX_LENGTH: Final[int] = 80
IDEMPOTENCY_KEY_PREFIX: Final[str] = "notification-"
# An administrator sends a failed notification again (US-36).
RESEND_RULE: Final[str] = "US-36"
# Where a notification that has not failed stands, as an administrator reads it.
NOT_FAILED_IN_WORDS: Final[Mapping[NotificationStatus, str]] = MappingProxyType(
    {
        NotificationStatus.QUEUED: "still waiting to be sent",
        NotificationStatus.SENT: "already sent",
    }
)
CONFIRMATION_SUBJECT_TEMPLATE: Final[str] = "Your Toolshed Hire booking {reference}"
CONFIRMATION_BODY_TEMPLATE: Final[str] = (
    "Thank you for booking with Toolshed Hire.\n"
    "\n"
    "Your booking reference is {reference}. Please quote it when you collect "
    "at the branch.\n"
    "\n"
    "Toolshed Hire\n"
)


@dataclass(frozen=True, slots=True)
class EmailMessage:
    """One email, in the terms every email provider understands.

    Attributes:
        to: The single recipient address.
        subject: The subject line.
        text_body: The plain text body.
        idempotency_key: A value that is the same every time this message is
            sent, so a provider that sees it twice delivers it once. None for a
            message that has no stored record to derive one from.

    """

    to: str
    subject: str
    text_body: str
    idempotency_key: str | None = None


@dataclass(slots=True)
class Notification:
    """The record of one outbound booking confirmation.

    Attributes:
        reservation_id: The booking the message is about.
        reservation_reference: The reference the message quotes.
        recipient_email: The address the message goes to.
        subject: The subject line, fixed when the notification is queued.
        queued_at: When the notification was written.
        notification_type: What the message is about.
        channel: How the message travels.
        status: Whether it is waiting, delivered or failed.
        attempts: How many times a send has been tried.
        provider_message_id: The id the provider returned on success.
        last_error: Why the last attempt failed.
        sent_at: When the provider accepted it.
        id: The notification key, generated here so it is known before the insert.

    """

    reservation_id: UUID
    reservation_reference: str
    recipient_email: str
    subject: str
    queued_at: datetime
    notification_type: NotificationType = NotificationType.BOOKING_CONFIRMATION
    channel: NotificationChannel = NotificationChannel.EMAIL
    status: NotificationStatus = NotificationStatus.QUEUED
    attempts: int = 0
    provider_message_id: str | None = None
    last_error: str | None = None
    sent_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)

    @classmethod
    def booking_confirmation(
        cls,
        *,
        reservation_id: UUID,
        reservation_reference: str,
        recipient_email: str,
        queued_at: datetime,
    ) -> Notification:
        """Build the queued confirmation for a booking.

        Args:
            reservation_id: The booking the message is about.
            reservation_reference: The reference the customer will quote.
            recipient_email: The address of the customer's account.
            queued_at: The moment the booking was made, from the clock.

        Raises:
            ValueError: If the recipient address is blank.

        """
        recipient = recipient_email.strip()
        if not recipient:
            raise ValueError(
                "Attempted to queue a booking confirmation with no recipient address for "
                f"reservation {reservation_reference}."
            )
        return cls(
            reservation_id=reservation_id,
            reservation_reference=reservation_reference,
            recipient_email=recipient,
            subject=CONFIRMATION_SUBJECT_TEMPLATE.format(reference=reservation_reference),
            queued_at=queued_at,
        )

    def to_message(self) -> EmailMessage:
        """Return the email this notification stands for.

        The idempotency key is derived from the notification id, so the same
        notification always produces the same key however many times it is
        sent.
        """
        return EmailMessage(
            to=self.recipient_email,
            subject=self.subject,
            text_body=CONFIRMATION_BODY_TEMPLATE.format(reference=self.reservation_reference),
            idempotency_key=f"{IDEMPOTENCY_KEY_PREFIX}{self.id}",
        )

    def mark_sent(self, provider_message_id: str, sent_at: datetime) -> None:
        """Record that the provider accepted the message.

        Args:
            provider_message_id: The id the provider returned.
            sent_at: When it was accepted, from the clock.

        """
        self.status = NotificationStatus.SENT
        self.provider_message_id = provider_message_id[:PROVIDER_MESSAGE_ID_MAX_LENGTH]
        self.sent_at = sent_at
        self.last_error = None
        self.attempts += 1

    def resent(self, *, queued_at: datetime) -> Notification:
        """Return a new queued notification that sends this failed one again (US-36).

        The new one is for the same booking, to the same address, with the
        same subject. This one is left exactly as it is, so the failure and
        the re-send are both in the log.

        Args:
            queued_at: When the administrator asked for it to be sent again.

        Raises:
            StateTransitionError: If this notification has not failed.

        """
        if self.status is not NotificationStatus.FAILED:
            raise StateTransitionError(
                f"Only a notification that failed can be sent again. This one is "
                f"{NOT_FAILED_IN_WORDS[self.status]}.",
                from_status=self.status.value,
                to_status=NotificationStatus.QUEUED.value,
                rule=RESEND_RULE,
            )
        return Notification(
            reservation_id=self.reservation_id,
            reservation_reference=self.reservation_reference,
            recipient_email=self.recipient_email,
            subject=self.subject,
            queued_at=queued_at,
            notification_type=self.notification_type,
            channel=self.channel,
        )

    def mark_failed(self, reason: str) -> None:
        """Record that an attempt failed, and why.

        Args:
            reason: A short phrase saying what went wrong. Anything longer than
                `FAILURE_REASON_MAX_LENGTH` is cut to fit.

        """
        self.status = NotificationStatus.FAILED
        self.last_error = reason[:FAILURE_REASON_MAX_LENGTH]
        self.attempts += 1
