"""The dispatcher, which sends the queued notifications after the commit (BR-19).

A notification is queued inside the transaction of the booking it belongs to.
It is sent here, after that transaction has committed and with no transaction
open, so a slow or failing provider can never hold a database connection or
roll a booking back. The outcome of each send is then written in a short
transaction of its own.

Dispatch runs inside the request that queued the notification, after the commit
and before the response. Cloud Run only gives a container CPU while it is
serving a request, so work left for a background thread may never run. The
price is that a slow provider slows that one response by up to the gateway
timeout for each message it sends, which I accept for an email that is sent a
few dozen times a day.

Only `QUEUED` notifications are due. One that failed is not sent again by a
later dispatch, because sending it again is a decision for an administrator and
not something the next customer's request should pay for.

Two things about this design get worse with volume and are worth naming. A
dispatch sends whatever is queued, not only what its own request queued, so a
notification stranded by a crash is picked up by the next booking. Two requests
can therefore read the same queued row before either has recorded an outcome.
The message carries an idempotency key derived from the notification id, so the
provider delivers it once. The sends are also sequential, so a batch costs the
sum of its provider calls. At a few dozen bookings a day neither matters. At a
hundred times that, dispatch belongs in a scheduled job that claims a row
before it sends it.

Nothing in here raises. The booking is already committed when dispatch starts,
and answering that request with an error would tell the customer a booking
failed when it did not. A fault is logged with its traceback and the
notification is marked failed, or left queued when even that cannot be written.
"""

from __future__ import annotations

import logging
from typing import Final

from app.application.clock import Clock
from app.application.notification.ports import (
    DeliveryReceipt,
    NotificationGateway,
    NotificationOutbox,
)
from app.application.unit_of_work import UnitOfWork
from app.domain.notification import Notification

logger = logging.getLogger(__name__)

# How many queued notifications one dispatch will send. A booking queues one,
# so the rest of the batch is room for any that an earlier request left behind.
DEFAULT_DISPATCH_LIMIT: Final[int] = 5
UNEXPECTED_FAULT_REASON: Final[str] = "The email gateway failed unexpectedly. See the log."
MISSING_RECEIPT_REASON: Final[str] = "The email gateway gave no reason for the failure."
MISSING_MESSAGE_ID: Final[str] = "unknown"


class NotificationDispatcher:
    """Sends the outbox rows that are due and records what became of each."""

    def __init__(self, uow: UnitOfWork, gateway: NotificationGateway, clock: Clock) -> None:
        """Keep the collaborators the dispatcher works with.

        Args:
            uow: The unit of work whose outbox holds the queued notifications.
                It is entered once to read them and once more for each outcome.
            gateway: The email provider.
            clock: Where the moment of a successful send comes from.

        """
        self._uow = uow
        self._gateway = gateway
        self._clock = clock

    def dispatch_due(self, limit: int = DEFAULT_DISPATCH_LIMIT) -> int:
        """Send up to `limit` queued notifications.

        Args:
            limit: The most notifications to send in this call.

        Returns:
            How many the provider accepted.

        """
        due = self._read_due(limit)
        if not due:
            logger.debug("notification.dispatch_nothing_due", extra={"limit": limit})
            return 0
        logger.info("notification.dispatch_started", extra={"due_count": len(due), "limit": limit})
        accepted_count = sum(self._dispatch_one(notification) for notification in due)
        logger.info(
            "notification.dispatch_finished",
            extra={"due_count": len(due), "accepted_count": accepted_count},
        )
        return accepted_count

    def _read_due(self, limit: int) -> list[Notification]:
        """Return the queued notifications, or none when they cannot be read."""
        try:
            with self._uow as uow:
                return uow.notifications.due(limit)
        except Exception:
            # The booking that led here is committed. Failing the request now
            # would report a failure that did not happen, so the fault is
            # logged in full and the rows stay queued for the next dispatch.
            logger.exception(
                "notification.outbox_read_failed",
                extra={"attempted": "read the queued notifications", "limit": limit},
            )
            return []

    def _dispatch_one(self, notification: Notification) -> bool:
        """Send one notification and record the outcome. Return True when accepted."""
        receipt = self._send(notification)
        self._record_outcome(notification, receipt)
        return receipt.accepted

    def _send(self, notification: Notification) -> DeliveryReceipt:
        """Hand one message to the gateway, with no transaction open."""
        logger.info(
            "notification.send_started",
            extra={
                "notification_id": str(notification.id),
                "reservation_id": str(notification.reservation_id),
                "notification_type": notification.notification_type.value,
                "attempt": notification.attempts + 1,
            },
        )
        try:
            return self._gateway.send(notification.to_message())
        except Exception:
            # A gateway reports a failed delivery through its receipt. Reaching
            # here means it broke that contract, which is a defect, and the
            # booking must still stand. The traceback goes to the log.
            logger.exception(
                "notification.gateway_fault",
                extra={
                    "notification_id": str(notification.id),
                    "attempted": "send a queued notification through the gateway",
                },
            )
            return DeliveryReceipt.failed(UNEXPECTED_FAULT_REASON)

    def _record_outcome(self, notification: Notification, receipt: DeliveryReceipt) -> None:
        """Write what the gateway reported, in a transaction of its own."""
        try:
            with self._uow as uow:
                self._apply(uow.notifications, notification, receipt)
                uow.commit()
        except Exception:
            # The send has already happened or failed. If its outcome cannot be
            # written the row stays queued and is sent again later, and the
            # idempotency key stops the provider delivering it twice.
            logger.exception(
                "notification.outcome_not_recorded",
                extra={
                    "notification_id": str(notification.id),
                    "accepted": receipt.accepted,
                    "attempted": "record the outcome of a send",
                },
            )
            return
        log = logger.info if receipt.accepted else logger.warning
        log(
            "notification.send_finished",
            extra={
                "notification_id": str(notification.id),
                "reservation_id": str(notification.reservation_id),
                "status": notification.status.value,
                "provider_message_id": notification.provider_message_id,
                "failure_reason": notification.last_error,
                "attempts": notification.attempts,
            },
        )

    def _apply(
        self, outbox: NotificationOutbox, notification: Notification, receipt: DeliveryReceipt
    ) -> None:
        """Mark the notification sent or failed, in memory and in the outbox."""
        if receipt.accepted:
            message_id = receipt.provider_message_id or MISSING_MESSAGE_ID
            sent_at = self._clock.now()
            notification.mark_sent(message_id, sent_at)
            outbox.mark_sent(
                notification.id, notification.provider_message_id or message_id, sent_at
            )
            return
        reason = receipt.error or MISSING_RECEIPT_REASON
        notification.mark_failed(reason)
        outbox.mark_failed(notification.id, notification.last_error or reason)
