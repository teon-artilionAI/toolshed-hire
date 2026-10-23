"""Sending a booking confirmation again (FR-27, US-36, B13.2).

A customer may ask for their own booking's confirmation again, and counter
staff may ask for any booking at their branch. The message goes through the
same outbox and dispatcher as the original, so restricted mode applies exactly
as it did then and the notification log keeps both sends.

Three re-sends are allowed per booking in one hour, counted in the shared
throttle table under the reservation key. The fourth is refused with the wait
until the window ends. The count and the new notification commit together, so
a request that fails after counting does not spend one of the three.

The booking must already have been confirmed. A held, draft, cancelled, no
show or expired booking is refused with 409, because a confirmation for one of
those would tell the customer something untrue.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Final

from app.application.audit import audit_event_for
from app.application.booking.access import RESERVATION_ENTITY_TYPE, customer_of, load_for_change
from app.application.booking.read_models import ReservationKey
from app.application.clock import Clock
from app.application.notification.dispatcher import NotificationDispatcher
from app.application.notification.ports import NotificationGateway
from app.application.throttle import Throttle, ThrottleRule
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.booking import Reservation
from app.domain.enums import ReservationStatus
from app.domain.errors import StateTransitionError, TooManyAttempts
from app.domain.identity import Actor
from app.domain.notification import Notification

logger = logging.getLogger(__name__)

RESEND_RULE: Final[ThrottleRule] = ThrottleRule(
    name="booking-confirmation-resend", limit=3, window=timedelta(hours=1)
)
RESENDABLE_STATUSES: Final[frozenset[ReservationStatus]] = frozenset(
    {ReservationStatus.CONFIRMED, ReservationStatus.COLLECTED}
)
CONFIRMATION_RESENT_ACTION: Final[str] = "notification.booking_confirmation_resent"
NO_EMAIL_MESSAGE: Final[str] = (
    "This customer has no email address on the booking, so there is nowhere to send it."
)
NOT_CONFIRMED_MESSAGE: Final[str] = (
    "Only a confirmed booking can have its confirmation sent again."
)
TOO_MANY_MESSAGE: Final[str] = (
    "This booking has had its confirmation sent again three times in the last hour. "
    "Try again later."
)


@dataclass(frozen=True, slots=True)
class ResendBookingConfirmationCommand:
    """A request to send a booking's confirmation again.

    Attributes:
        actor: The customer or member of staff asking.
        key: The booking, by its key or its reference.

    """

    actor: Actor
    key: ReservationKey


@dataclass(frozen=True, slots=True)
class ResendOutcome:
    """What happened to a re-send."""

    email_deliverable: bool


class ResendBookingConfirmation(
    UseCase[ResendBookingConfirmationCommand, ResendOutcome]
):
    """Queue the confirmation again, send it, and say whether email can reach the address."""

    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        throttle: Throttle,
        dispatcher: NotificationDispatcher,
        gateway: NotificationGateway,
    ) -> None:
        """Keep the collaborators the re-send works with."""
        super().__init__(uow, clock)
        self._throttle = throttle
        self._dispatcher = dispatcher
        self._gateway = gateway

    def execute(self, command: ResendBookingConfirmationCommand) -> ResendOutcome:
        """Queue and send the confirmation again.

        Raises:
            NotFound: If the booking is absent or not the caller's.
            BranchScopeError: If counter staff name another branch.
            StateTransitionError: If the booking is not confirmed, or the
                customer has no address.
            TooManyAttempts: If the booking has had three re-sends this hour.

        """
        actor = command.actor
        now = self._clock.now()
        logger.info(
            "notification.confirmation_resend_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "reservation": str(command.key),
            },
        )
        with self._uow as uow:
            reservation = load_for_change(uow, actor, command.key)
            self._ensure_resendable(reservation)
            customer = customer_of(uow, reservation)
            if customer.email is None:
                raise StateTransitionError(
                    NO_EMAIL_MESSAGE,
                    from_status=reservation.status.value,
                    to_status=reservation.status.value,
                )
            verdict = self._throttle.check(
                uow.rate_limits, RESEND_RULE, f"reservation:{reservation.id}", now
            )
            if not verdict.allowed:
                raise TooManyAttempts(
                    TOO_MANY_MESSAGE, retry_after_seconds=verdict.retry_after_seconds
                )
            notification = Notification.booking_confirmation(
                reservation_id=reservation.id,
                reservation_reference=reservation.reference,
                recipient_email=customer.email,
                queued_at=now,
            )
            uow.notifications.enqueue(notification)
            uow.audit.record(
                audit_event_for(
                    actor=actor,
                    entity_type=RESERVATION_ENTITY_TYPE,
                    entity_id=reservation.id,
                    action=CONFIRMATION_RESENT_ACTION,
                    occurred_at=now,
                    after_state={
                        "notification_id": str(notification.id),
                        "reservation_reference": reservation.reference,
                    },
                )
            )
            uow.commit()
        self._dispatcher.dispatch_due()
        deliverable = self._gateway.delivers_to(customer.email)
        logger.info(
            "notification.confirmation_resent",
            extra={
                "reservation_reference": reservation.reference,
                "notification_id": str(notification.id),
                "email_deliverable": deliverable,
            },
        )
        return ResendOutcome(email_deliverable=deliverable)

    def _ensure_resendable(self, reservation: Reservation) -> None:
        """Refuse a booking whose confirmation would be untrue."""
        if reservation.status not in RESENDABLE_STATUSES:
            raise StateTransitionError(
                NOT_CONFIRMED_MESSAGE,
                from_status=reservation.status.value,
                to_status=ReservationStatus.CONFIRMED.value,
            )


__all__ = [
    "CONFIRMATION_RESENT_ACTION",
    "ResendBookingConfirmation",
    "ResendBookingConfirmationCommand",
    "ResendOutcome",
]
