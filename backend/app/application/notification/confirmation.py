"""Queueing the booking confirmation (BR-19).

The booking module decides that a booking was confirmed. The notification
module decides what is sent about it and to whom. The use case that confirms a
reservation calls `queue_booking_confirmation` inside its own unit of work, so
the notification is written in the same transaction as the confirmation and
commits or rolls back with it. Nothing is sent here. The dispatcher sends what was queued once that
transaction has committed.
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.application.notification.ports import NotificationOutbox
from app.domain.booking import Reservation
from app.domain.identity import CustomerProfile
from app.domain.notification import Notification

logger = logging.getLogger(__name__)


def queue_booking_confirmation(
    outbox: NotificationOutbox,
    *,
    reservation: Reservation,
    customer: CustomerProfile,
    queued_at: datetime,
) -> Notification | None:
    """Queue the confirmation of a booking in the outbox of the open unit of work.

    Args:
        outbox: The outbox of the unit of work that holds the booking.
        reservation: The booking to confirm.
        customer: The customer the booking belongs to.
        queued_at: The moment the booking was confirmed, from the clock.

    Returns:
        The queued notification, or None when the customer has no email
        address. That is a walk-in with no login, and there is nowhere to send
        a confirmation to.

    """
    if customer.email is None:
        logger.info(
            "notification.confirmation_not_queued",
            extra={
                "reference": reservation.reference,
                "customer_profile_id": str(customer.id),
                "reason": "the customer has no email address",
            },
        )
        return None
    notification = Notification.booking_confirmation(
        reservation_id=reservation.id,
        reservation_reference=reservation.reference,
        recipient_email=customer.email,
        queued_at=queued_at,
    )
    outbox.enqueue(notification)
    logger.info(
        "notification.confirmation_queued",
        extra={"reference": reservation.reference, "notification_id": str(notification.id)},
    )
    return notification
