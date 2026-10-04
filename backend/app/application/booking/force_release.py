"""The use case by which an administrator releases one unit of a booking by hand (US-32).

This is the escape hatch of the office, for a unit the record says is held for
a booking when it cannot be handed over. In one unit of work the allocation is
found through the asset repository, which is the allocation repository of the
system, the reservation that holds it is locked, the domain releases it with
the reason REALLOCATED, the repository writes the release, and the audit event
names the administrator, the unit and the reason they gave (BR-25, BR-49).

The order of the locks is the reservation's first, as a checkout and a hold
take it, so a release and a checkout of the same booking take turns. An
allocation already released, or a unit out on hire on the booking, is refused
with 409 and nothing changes. The booking then holds fewer units than it asks
for, so it cannot be checked out until it is given a replacement.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from app.application.booking.access import load_for_change, read_detail, record_change, state_of
from app.application.booking.read_models import ReservationKey
from app.application.booking.views import ReservationView, view_for
from app.application.identity.account_rules import refused_field
from app.application.use_case import UseCase
from app.domain.enums import ReleaseReason
from app.domain.errors import NotFound, ValidationFailure
from app.domain.identity import Actor
from app.domain.override_reason import written_reason
from app.domain.reallocation import force_release, units_short_of

logger = logging.getLogger(__name__)

RESERVATION_UNIT_RELEASED_ACTION: Final[str] = "reservation.unit_released"
ALLOCATION_NOT_FOUND_MESSAGE: Final[str] = "We could not find that allocation."


@dataclass(frozen=True, slots=True)
class ForceReleaseCommand:
    """A request to release one allocation by hand.

    Attributes:
        actor: The administrator releasing it.
        allocation_id: The allocation, as the checkout read lists it.
        reason: Why, which goes into the audit event.

    """

    actor: Actor
    allocation_id: UUID
    reason: str


class ForceReleaseUseCase(UseCase[ForceReleaseCommand, ReservationView]):
    """Release one active allocation with the reason REALLOCATED, in one transaction."""

    def execute(self, command: ForceReleaseCommand) -> ReservationView:
        """Release the allocation and return the reservation that held it.

        Raises:
            ValidationFailure: If the reason is too short or too long.
            NotFound: If there is no such allocation.
            StateTransitionError: If it was already released, or its unit is
                out on hire on the booking.

        """
        actor = command.actor
        logger.info(
            "allocation.force_release_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "allocation_id": str(command.allocation_id),
            },
        )
        try:
            reason = written_reason(command.reason)
        except ValidationFailure as failure:
            raise refused_field(failure) from failure
        now = self._clock.now()
        with self._uow as uow:
            held = uow.assets.find_allocation(command.allocation_id)
            if held is None:
                logger.info(
                    "allocation.not_found", extra={"allocation_id": str(command.allocation_id)}
                )
                raise NotFound(
                    ALLOCATION_NOT_FOUND_MESSAGE, {"allocation": str(command.allocation_id)}
                )
            reservation = load_for_change(uow, actor, ReservationKey.of(held.reservation_id))
            before = state_of(reservation)
            released = force_release(reservation, command.allocation_id, now)
            uow.assets.release_allocation(released)
            short = units_short_of(reservation)
            record_change(
                uow,
                actor=actor,
                reservation=reservation,
                action=RESERVATION_UNIT_RELEASED_ACTION,
                occurred_at=now,
                before=before,
                extra={
                    "allocation_id": str(released.id),
                    "asset_tag": held.asset_tag,
                    "release_reason": ReleaseReason.REALLOCATED.value,
                    "reason": reason,
                    "units_short": short,
                },
            )
            detail = read_detail(uow, actor, ReservationKey.of(reservation.id))
            uow.commit()
        logger.info(
            "allocation.force_released",
            extra={
                "reference": reservation.reference,
                "allocation_id": str(released.id),
                "asset_tag": held.asset_tag,
                "units_short": short,
            },
        )
        return view_for(actor, detail, now)
