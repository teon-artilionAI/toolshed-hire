"""The use case that cancels a reservation (FR-10, US-16).

A reservation can be cancelled while it is a draft, on hold or confirmed.
Cancelling releases every unit it holds, with the reason `CANCELLED`, in the
same unit of work as the change of status (BR-14), so there is never a
cancelled booking that still keeps a machine off the shelf. Once the equipment
has been collected nobody can cancel it (BR-15).

There is no charge, because no money is taken until checkout (BR-16). A
confirmed booking cancelled after 17:00 on the day before collection is a late
cancellation. The reservation state decides that, and this use case counts it
on the customer's profile.

Nothing is deleted (BR-51). A cancelled reservation stays readable, with when
it was cancelled and the reason that was given.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final

from app.application.booking.access import (
    RESERVATION_CANCELLED_ACTION,
    customer_of,
    is_staff,
    load_for_change,
    read_detail,
    record_change,
    state_of,
)
from app.application.booking.expire_holds import settle_overdue_hold
from app.application.booking.read_models import ReservationKey
from app.application.booking.views import ReservationView, view_for
from app.application.refusal import refused
from app.application.use_case import UseCase
from app.domain.identity import Actor

logger = logging.getLogger(__name__)

REASON_PARAMETER: Final[str] = "reason"
# The width of the column the reason is stored in.
REASON_MAX_LENGTH: Final[int] = 200
REASON_TOO_LONG_MESSAGE: Final[str] = f"Enter at most {REASON_MAX_LENGTH} characters."


@dataclass(frozen=True, slots=True)
class CancelReservationCommand:
    """A request to cancel one reservation.

    Attributes:
        actor: The account making the request and the role it holds.
        key: The reservation, by its key or its reference.
        reason: Why it is being cancelled, when the caller said.

    """

    actor: Actor
    key: ReservationKey
    reason: str | None = None


class CancelReservationUseCase(UseCase[CancelReservationCommand, ReservationView]):
    """Cancel a reservation and release its units, in one transaction."""

    def execute(self, command: CancelReservationCommand) -> ReservationView:
        """Cancel the reservation and return it as the caller sees it.

        Raises:
            ValidationFailure: If the reason is longer than the column that
                stores it. The failure names `reason`.
            NotFound: If there is no such reservation, or it is not the caller's.
            BranchScopeError: If counter staff act at another branch.
            StateTransitionError: If the reservation can no longer be cancelled.

        """
        actor = command.actor
        reason = _cleaned(command.reason)
        logger.info(
            "reservation.cancel_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "reservation": str(command.key),
                "reason_given": reason is not None,
            },
        )
        now = self._clock.now()
        with self._uow as uow:
            reservation = load_for_change(uow, actor, command.key)
            settle_overdue_hold(uow, reservation, now)
            customer = customer_of(uow, reservation)
            before = state_of(reservation)
            reservation.cancel(
                now=now,
                reason=reason,
                by_owner_or_staff=is_staff(actor) or customer.user_account_id == actor.user_id,
                # Checkout opens the rental in the same transaction that moves
                # the reservation to COLLECTED, and a collected reservation is
                # refused by its state before this is asked. So a reservation
                # that can still be cancelled never has one. The state still
                # asks, so the rule holds if that ever changes.
                has_rental=False,
            )
            uow.reservations.save(reservation)
            if reservation.is_late_cancellation:
                uow.customers.record_late_cancellation(customer.id)
            record_change(
                uow,
                actor=actor,
                reservation=reservation,
                action=RESERVATION_CANCELLED_ACTION,
                occurred_at=now,
                before=before,
                extra={
                    "late_cancellation": reservation.is_late_cancellation,
                    "cancellation_reason": reason,
                },
            )
            detail = read_detail(uow, actor, ReservationKey.of(reservation.id))
            uow.commit()
        logger.info(
            "reservation.cancel_finished",
            extra={
                "reference": reservation.reference,
                "reservation_id": str(reservation.id),
                "outcome": reservation.status.value,
                "released_count": before["active_allocation_count"],
                "late_cancellation": reservation.is_late_cancellation,
            },
        )
        return view_for(actor, detail, now)


def _cleaned(reason: str | None) -> str | None:
    """Return the reason without surrounding space, and None for one that is blank.

    Raises:
        ValidationFailure: Naming `reason` when it is too long to store.

    """
    if reason is None:
        return None
    cleaned = reason.strip()
    if len(cleaned) > REASON_MAX_LENGTH:
        raise refused(REASON_PARAMETER, REASON_TOO_LONG_MESSAGE, {"length": len(cleaned)})
    return cleaned or None
