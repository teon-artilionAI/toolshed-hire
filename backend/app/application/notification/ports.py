"""The notification ports, which are the outbox and the gateway (BR-19).

The outbox is the `notification` table seen from the application layer. A use
case queues a notification through it inside its own transaction, and the
dispatcher reads the queued ones back and records what became of each.

The gateway is the email provider seen from the application layer. Nothing on
this side of it knows which provider is in use, so changing supplier changes
one adapter and nothing else. A gateway never raises for a delivery that did
not happen. It returns a receipt that says so, because a failed email is an
outcome to record and not a reason to fail the booking it belongs to.

A gateway can also say whether it would deliver to an address at all. An
environment may be set up to send mail to one address only, and a screen that
has just promised somebody a message needs to know when none is coming. The
answer depends on how the gateway is configured and on the address, and on
nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.notification import EmailMessage, Notification


@dataclass(frozen=True, slots=True)
class DeliveryReceipt:
    """What the gateway reports about one attempt to send one message.

    Attributes:
        accepted: True when the provider took the message for delivery.
        provider_message_id: The id the provider gave it, when it was accepted.
        error: A short reason, when it was not. Never a secret and never the
            raw provider response.

    """

    accepted: bool
    provider_message_id: str | None = None
    error: str | None = None

    @classmethod
    def delivered(cls, provider_message_id: str) -> DeliveryReceipt:
        """Return the receipt for a message the provider accepted."""
        return cls(accepted=True, provider_message_id=provider_message_id)

    @classmethod
    def failed(cls, reason: str) -> DeliveryReceipt:
        """Return the receipt for a message that was not sent, with the reason."""
        return cls(accepted=False, error=reason)


@runtime_checkable
class NotificationGateway(Protocol):
    """The email provider, as the application sees it."""

    def send(self, message: EmailMessage) -> DeliveryReceipt:
        """Try to send one message and report what happened.

        A provider error, a timeout and a refused recipient all come back as a
        failed receipt. The method does not raise for any of them.
        """
        ...

    def delivers_to(self, address: str) -> bool:
        """Return True when a message for this address would be handed to the provider."""
        ...


class NotificationOutbox(Protocol):
    """The queue of notifications waiting to be sent."""

    def enqueue(self, notification: Notification) -> None:
        """Write a queued notification inside the current transaction."""
        ...

    def due(self, limit: int) -> list[Notification]:
        """Return up to `limit` queued notifications, oldest first."""
        ...

    def mark_sent(
        self, notification_id: UUID, provider_message_id: str, sent_at: datetime
    ) -> None:
        """Record that the provider accepted the notification and count the attempt.

        Args:
            notification_id: The notification that was sent.
            provider_message_id: The id the provider returned.
            sent_at: When it was accepted.

        """
        ...

    def mark_failed(self, notification_id: UUID, reason: str) -> None:
        """Record that an attempt failed and count the attempt.

        Args:
            notification_id: The notification that was not sent.
            reason: A short phrase saying why.

        """
        ...
