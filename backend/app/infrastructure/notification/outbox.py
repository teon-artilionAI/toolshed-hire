"""The SQL notification outbox (BR-19).

The `notification` table is a transactional outbox. A row is written `QUEUED`
through the session of the unit of work that holds the booking, so the two
commit together. The dispatcher reads the queued rows back after that commit
and records the outcome of each send through a later transaction.

The table has no column for the body of the message. The body is rendered from
the booking reference when the message is sent, so `due` reads the reference
of each reservation in the same statement.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Final
from uuid import UUID

from sqlmodel import Session, col, select

from app.domain import notification as domain
from app.domain.enums import NotificationStatus
from app.infrastructure.models import Notification, Reservation

logger = logging.getLogger(__name__)

# What the `provider` column records. The outbox and the adapter are the only
# two places that know which provider carries the mail.
EMAIL_PROVIDER_NAME: Final[str] = "resend"
ATTEMPT_INCREMENT: Final[int] = 1


class SqlNotificationOutbox:
    """Queues notifications and records their outcomes through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the outbox to the session of its unit of work."""
        self._session = session

    def enqueue(self, notification: domain.Notification) -> None:
        """Write a queued notification inside the current transaction."""
        row = Notification(
            id=notification.id,
            reservation_id=notification.reservation_id,
            notification_type=notification.notification_type,
            channel=notification.channel,
            recipient_email=notification.recipient_email,
            subject=notification.subject,
            status=notification.status,
            provider=EMAIL_PROVIDER_NAME,
            provider_message_id=notification.provider_message_id,
            attempts=notification.attempts,
            last_error=notification.last_error,
            queued_at=notification.queued_at,
            sent_at=notification.sent_at,
        )
        self._session.add(row)
        self._session.flush()
        logger.debug(
            "notification.enqueued",
            extra={
                "notification_id": str(notification.id),
                "reservation_id": str(notification.reservation_id),
                "notification_type": notification.notification_type.value,
            },
        )

    def due(self, limit: int) -> list[domain.Notification]:
        """Return up to `limit` queued notifications, oldest first."""
        statement = (
            select(Notification, col(Reservation.reference))
            .join(Reservation, col(Reservation.id) == col(Notification.reservation_id))
            .where(col(Notification.status) == NotificationStatus.QUEUED)
            .order_by(col(Notification.queued_at), col(Notification.id))
            .limit(limit)
        )
        logger.debug("notification.due_query_started", extra={"limit": limit})
        found = self._session.exec(statement).all()
        logger.debug("notification.due_query_finished", extra={"due_count": len(found)})
        return [_notification_of(row, reference) for row, reference in found]

    def mark_sent(
        self, notification_id: UUID, provider_message_id: str, sent_at: datetime
    ) -> None:
        """Record that the provider accepted the notification and count the attempt."""
        row = self._row(notification_id)
        row.status = NotificationStatus.SENT
        row.provider_message_id = provider_message_id
        row.sent_at = sent_at
        row.last_error = None
        row.attempts += ATTEMPT_INCREMENT
        self._session.add(row)
        self._session.flush()
        logger.debug(
            "notification.marked_sent",
            extra={"notification_id": str(notification_id), "attempts": row.attempts},
        )

    def mark_failed(self, notification_id: UUID, reason: str) -> None:
        """Record that an attempt failed and count the attempt."""
        row = self._row(notification_id)
        row.status = NotificationStatus.FAILED
        row.last_error = reason
        row.attempts += ATTEMPT_INCREMENT
        self._session.add(row)
        self._session.flush()
        logger.debug(
            "notification.marked_failed",
            extra={"notification_id": str(notification_id), "attempts": row.attempts},
        )

    def _row(self, notification_id: UUID) -> Notification:
        """Return the stored notification.

        Raises:
            LookupError: If no row has this key. An outcome can only be
                recorded for a notification that was queued, so this means the
                caller holds an id that never reached the table.

        """
        row = self._session.get(Notification, notification_id)
        if row is None:
            raise LookupError(
                f"Attempted to record the outcome of notification {notification_id}, "
                "which is not in the outbox."
            )
        return row


def _notification_of(row: Notification, reservation_reference: str) -> domain.Notification:
    """Return the domain entity for a notification row and its booking reference."""
    return domain.Notification(
        id=row.id,
        reservation_id=row.reservation_id,
        reservation_reference=reservation_reference,
        recipient_email=row.recipient_email,
        subject=row.subject,
        queued_at=row.queued_at,
        notification_type=row.notification_type,
        channel=row.channel,
        status=row.status,
        attempts=row.attempts,
        provider_message_id=row.provider_message_id,
        last_error=row.last_error,
        sent_at=row.sent_at,
    )
