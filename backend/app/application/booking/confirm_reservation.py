"""The use case that confirms a held reservation (FR-08, US-13).

A reservation is confirmed inside its hold, when every line holds the units it
asks for (BR-08) and the customer has proved their email address (BR-47). A
counter assistant or an administrator confirming for a customer who is
standing at the counter satisfies that rule by being there.

The confirmation is the moment the customer is told about, so this is where
the booking confirmation is queued (BR-19). The notification row is written in
the same unit of work as the change of status and commits or rolls back with
it. It is sent only after the commit, with no transaction open, and still
inside the request. A provider failure marks the notification failed and
leaves the booking exactly as it was committed. Holding a reservation queues
nothing, because a hold that is never confirmed is nothing to write home
about.

A hold that has run out is lapsed before anything else is decided, and that
lapse is committed, so the units are free again even though the confirmation
is then refused.
"""

from __future__ import annotations

import logging

from app.application.booking.access import (
    RESERVATION_CONFIRMED_ACTION,
    ReservationCommand,
    customer_of,
    ensure_collection_branch_open,
    is_staff,
    load_for_change,
    read_detail,
    record_change,
    state_of,
)
from app.application.booking.expire_holds import (
    ExpireHoldsAndNoShowsUseCase,
    SweepCommand,
    settle_overdue_hold,
)
from app.application.booking.read_models import ReservationKey
from app.application.booking.views import ReservationView, view_for
from app.application.clock import Clock
from app.application.notification.confirmation import queue_booking_confirmation
from app.application.notification.dispatcher import NotificationDispatcher
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.states.base import CONFIRM_MOVE

logger = logging.getLogger(__name__)


class ConfirmReservationUseCase(UseCase[ReservationCommand, ReservationView]):
    """Confirm a held reservation and queue its confirmation, in one transaction."""

    def __init__(
        self,
        uow: UnitOfWork,
        clock: Clock,
        sweep: ExpireHoldsAndNoShowsUseCase,
        dispatcher: NotificationDispatcher,
    ) -> None:
        """Keep the collaborators the use case works with.

        Args:
            uow: The unit of work that owns the transaction.
            clock: Where the current instant comes from.
            sweep: Lapses the holds that have run out, before anything is decided.
            dispatcher: Sends the queued confirmation once the booking is committed.

        """
        super().__init__(uow, clock)
        self._sweep = sweep
        self._dispatcher = dispatcher

    def execute(self, command: ReservationCommand) -> ReservationView:
        """Confirm the reservation, commit it and then send its confirmation.

        Raises:
            NotFound: If there is no such reservation, or it is not the caller's.
            BranchScopeError: If counter staff act at another branch.
            StateTransitionError: If the reservation is not on hold, or its
                hold has run out.
            EmailNotVerifiedError: If a customer who has not proved their
                address is confirming for themselves.

        """
        actor = command.actor
        logger.info(
            "reservation.confirm_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "reservation": str(command.key),
            },
        )
        self._sweep.execute(SweepCommand())
        now = self._clock.now()
        with self._uow as uow:
            reservation = load_for_change(uow, actor, command.key)
            settle_overdue_hold(uow, reservation, now)
            customer = customer_of(uow, reservation)
            if reservation.state.permits(CONFIRM_MOVE):
                ensure_collection_branch_open(uow, reservation, now)
            before = state_of(reservation)
            reservation.confirm(
                now=now, email_verified=is_staff(actor) or customer.email_verified
            )
            uow.reservations.save(reservation)
            record_change(
                uow,
                actor=actor,
                reservation=reservation,
                action=RESERVATION_CONFIRMED_ACTION,
                occurred_at=now,
                before=before,
                extra={"confirmed_on_behalf": is_staff(actor)},
            )
            queue_booking_confirmation(
                uow.notifications, reservation=reservation, customer=customer, queued_at=now
            )
            detail = read_detail(uow, actor, ReservationKey.of(reservation.id))
            uow.commit()
        logger.info(
            "reservation.confirm_committed",
            extra={
                "reference": reservation.reference,
                "reservation_id": str(reservation.id),
                "outcome": reservation.status.value,
            },
        )

        # After the commit and outside the transaction. The dispatcher never
        # raises, so nothing that happens here can undo or misreport a booking.
        accepted_count = self._dispatcher.dispatch_due()
        logger.info(
            "reservation.confirm_finished",
            extra={
                "reference": reservation.reference,
                "reservation_id": str(reservation.id),
                "notifications_accepted": accepted_count,
            },
        )
        return view_for(actor, detail, now)
