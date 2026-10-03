"""The use case by which staff mark a booking as not collected (FR-12, US-37, BR-17, BR-18).

The sweep marks a confirmed booking as a no show once its branch has closed on
the first day of the hire. A member of staff at the counter can do it sooner,
from the start of that day, because they can see that nobody came. They give a
reason, which the audit event keeps. There is no column for it on the
reservation, and a no show is not a cancellation, so it is not written where a
cancellation keeps its reason.

It is the same move as the sweep's. `mark_as_no_show` makes it through the
reservation's state, releases every unit with the reason `NO_SHOW`, counts the
strike and puts the customer on hold at the third, all in one unit of work. The
difference is the actor on the audit event, and that staff may act from the
start of the first day.

Counter staff mark bookings at their own branch only (BR-43), and an
administrator at any. A booking that is not confirmed, or whose hire has not
started, is refused with 409 and a sentence that says which.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final

from app.application.booking.access import load_for_change, read_detail
from app.application.booking.expire_holds import settle_overdue_hold
from app.application.booking.no_show import mark_as_no_show
from app.application.booking.read_models import ReservationKey
from app.application.booking.views import ReservationView, view_for
from app.application.refusal import refused
from app.application.use_case import UseCase
from app.domain.identity import Actor

logger = logging.getLogger(__name__)

REASON_PARAMETER: Final[str] = "reason"
# The contract allows two hundred characters, the width a cancellation reason has.
NO_SHOW_REASON_MAX_LENGTH: Final[int] = 200
REASON_REQUIRED_MESSAGE: Final[str] = "Say why the booking was not collected."
REASON_TOO_LONG_MESSAGE: Final[str] = f"Enter at most {NO_SHOW_REASON_MAX_LENGTH} characters."


@dataclass(frozen=True, slots=True)
class MarkNoShowCommand:
    """A request by a member of staff to mark one reservation as not collected.

    Attributes:
        actor: The member of staff at the counter.
        key: The reservation, by its key or its reference.
        reason: Why it is being marked. Required.

    """

    actor: Actor
    key: ReservationKey
    reason: str


class MarkNoShowUseCase(UseCase[MarkNoShowCommand, ReservationView]):
    """Mark a confirmed reservation as a no show and count the strike, in one transaction."""

    def execute(self, command: MarkNoShowCommand) -> ReservationView:
        """Mark the reservation and return it as the caller sees it.

        Raises:
            ValidationFailure: If the reason is blank or too long. The failure
                names `reason`.
            NotFound: If there is no such reservation.
            BranchScopeError: If counter staff act at another branch.
            StateTransitionError: If the reservation is not confirmed or its
                hire has not started.

        """
        actor = command.actor
        reason = _checked_reason(command.reason)
        logger.info(
            "reservation.no_show_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "reservation": str(command.key),
            },
        )
        now = self._clock.now()
        today = self._clock.today()
        with self._uow as uow:
            reservation = load_for_change(uow, actor, command.key)
            settle_overdue_hold(uow, reservation, now)
            outcome = mark_as_no_show(
                uow,
                reservation,
                actor=actor,
                now=now,
                today=today,
                branch_closed_at=None,
                reason=reason,
            )
            detail = read_detail(uow, actor, ReservationKey.of(reservation.id))
            uow.commit()
        logger.info(
            "reservation.no_show_finished",
            extra={
                "reference": outcome.reference,
                "reservation_id": str(reservation.id),
                "released_count": outcome.released_count,
                "strikes_in_window": outcome.strikes_in_window,
                "put_on_hold": outcome.put_on_hold,
            },
        )
        return view_for(actor, detail, now)


def _checked_reason(reason: str) -> str:
    """Return the reason without surrounding space.

    Raises:
        ValidationFailure: Naming `reason` when it is blank or too long.

    """
    cleaned = reason.strip()
    if not cleaned:
        raise refused(REASON_PARAMETER, REASON_REQUIRED_MESSAGE)
    if len(cleaned) > NO_SHOW_REASON_MAX_LENGTH:
        raise refused(REASON_PARAMETER, REASON_TOO_LONG_MESSAGE, {"length": len(cleaned)})
    return cleaned
