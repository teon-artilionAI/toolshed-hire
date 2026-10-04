"""The use case by which an administrator sends a failed confirmation again (FR-27, US-36).

A notification that failed stays FAILED for ever, so the failure and the
re-send are both in the log. Sending it again writes a new notification row,
for the same booking and the same address, through the same outbox a
confirmation is queued in, with the audit event `notification.resent` in the
same transaction (BR-49). That event names the one that failed, which is
where the log reads `resend_of` from, because the table has no column for it.

The new row is sent after the commit, inside the request and with no
transaction open, by the same dispatcher a confirmation is sent by (BR-19).
So the email gateway decides as it always does, and the rule that a
demonstration environment sends to one allowed address only still applies.
The answer is the new notification as the log shows it once the dispatch has
recorded what became of it.

A notification that has not failed is refused with 409, and one that does not
exist with 404.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from app.application.audit import audit_event_for
from app.application.clock import Clock
from app.application.notification.dispatcher import NotificationDispatcher
from app.application.notification.log import (
    NOTIFICATION_ENTITY_TYPE,
    NOTIFICATION_RESENT_ACTION,
    RESEND_OF_KEY,
    NotificationEntry,
    NotificationLogQuery,
)
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.errors import NotFound
from app.domain.identity import Actor

logger = logging.getLogger(__name__)

NOTIFICATION_NOT_FOUND_MESSAGE: Final[str] = "We could not find that notification."


@dataclass(frozen=True, slots=True)
class ResendCommand:
    """A request to send one failed notification again.

    Attributes:
        actor: The administrator asking.
        notification_id: The notification that failed.

    """

    actor: Actor
    notification_id: UUID


class ResendNotificationUseCase(UseCase[ResendCommand, NotificationEntry]):
    """Queue a failed notification again as a new one, commit, and send it."""

    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        dispatcher: NotificationDispatcher,
        log: NotificationLogQuery,
    ) -> None:
        """Keep the collaborators the use case works with.

        Args:
            uow: The unit of work whose outbox the new notification is queued in.
            clock: Where the moment it is queued comes from.
            dispatcher: Sends what is queued once the transaction has committed.
            log: Reads the new notification back once it has been sent.

        """
        super().__init__(uow, clock)
        self._dispatcher = dispatcher
        self._log = log

    def execute(self, command: ResendCommand) -> NotificationEntry:
        """Queue the notification again, commit, send it and return the new one.

        Raises:
            NotFound: If there is no such notification.
            StateTransitionError: If it has not failed.

        """
        actor = command.actor
        logger.info(
            "notification.resend_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "notification_id": str(command.notification_id),
            },
        )
        now = self._clock.now()
        with self._uow as uow:
            failed = uow.notifications.find(command.notification_id)
            if failed is None:
                logger.info(
                    "notification.not_found",
                    extra={"notification_id": str(command.notification_id)},
                )
                raise NotFound(
                    NOTIFICATION_NOT_FOUND_MESSAGE,
                    {"notification": str(command.notification_id)},
                )
            again = failed.resent(queued_at=now)
            uow.notifications.enqueue(again)
            uow.audit.record(
                audit_event_for(
                    actor=actor,
                    entity_type=NOTIFICATION_ENTITY_TYPE,
                    entity_id=again.id,
                    action=NOTIFICATION_RESENT_ACTION,
                    occurred_at=now,
                    after_state={
                        RESEND_OF_KEY: str(failed.id),
                        "reservation_reference": again.reservation_reference,
                        "status": again.status.value,
                    },
                )
            )
            uow.commit()
        accepted_count = self._dispatcher.dispatch_due()
        entry = self._log.one(again.id)
        if entry is None:
            raise LookupError(
                f"Attempted to read back notification {again.id}, which was committed as the "
                f"re-send of {failed.id} and could not be read."
            )
        logger.info(
            "notification.resend_finished",
            extra={
                "notification_id": str(again.id),
                "resend_of": str(failed.id),
                "reservation_reference": again.reservation_reference,
                "status": entry.status.value,
                "notifications_accepted": accepted_count,
            },
        )
        return entry
