"""Reading one reservation on behalf of somebody (BR-42).

A customer who asks for a reservation that is not theirs is told there is no
such reservation, in the words used for a key nobody ever issued. The scope of
the reader goes into the query, so this service never holds a record it then
has to decide not to return.

Nothing is written, so nothing is committed. The unit of work is used for the
session it carries and is left without a commit.
"""

from __future__ import annotations

import logging
from typing import Final
from uuid import UUID

from app.application.booking.read_models import ReservationSummary
from app.application.ownership import not_found, owner_scope_for
from app.application.unit_of_work import UnitOfWork
from app.domain.identity import Actor

logger = logging.getLogger(__name__)

RESERVATION_ENTITY: Final[str] = "reservation"


class ReadReservation:
    """Return one reservation to a reader who is allowed to see it."""

    def __init__(self, uow: UnitOfWork) -> None:
        """Keep the unit of work the read runs in."""
        self._uow = uow

    def execute(self, actor: Actor, reservation_id: UUID) -> ReservationSummary:
        """Return the reservation, or refuse as though it did not exist.

        Args:
            actor: Who is asking, with the role they hold.
            reservation_id: The reservation asked for.

        Raises:
            NotFound: If there is no such reservation, or if the actor is a
                customer and it belongs to somebody else. The two are not
                distinguished.

        """
        scope = owner_scope_for(actor)
        logger.info(
            "reservation.read_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "reservation_id": str(reservation_id),
                "restricted_to_owner": scope.is_restricted,
            },
        )
        with self._uow as uow:
            summary = uow.reservations.find_summary(reservation_id, scope)
        logger.info(
            "reservation.read_finished",
            extra={"reservation_id": str(reservation_id), "found": summary is not None},
        )
        if summary is None:
            raise not_found(RESERVATION_ENTITY, reservation_id)
        return summary
