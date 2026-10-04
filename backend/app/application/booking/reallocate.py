"""The use case that gives a short booking replacement units (US-32, BR-08, BR-09).

A booking that lost a unit to a force release holds fewer units than it asks
for, and it cannot be collected until it holds them all again. Staff at the
collection branch, or an administrator, ask for replacements, and every short
line is topped up through the allocator a hold uses, so the units are found by
the one locking query, the exclusion constraint has the last word, and a
conflict is the same clean 409 naming the model and the dates (BR-07). A line
that cannot be given all it is short of fails the whole reallocation, and
nothing is allocated. Units come only from the collection branch (BR-06).

Before anything is decided the sweep runs, and a hold that has run out is
lapsed, so a booking that is no longer waiting for its units is refused with
409. A booking short of nothing is answered as it stands and nothing is
written.
"""

from __future__ import annotations

import logging
from typing import Final

from app.application.booking.access import (
    ReservationCommand,
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
from app.application.booking.unit_allocator import (
    REALLOCATION_REFUSED_EVENT,
    allocator_for,
    line_models_of,
)
from app.application.booking.views import ReservationView, view_for
from app.application.clock import Clock
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.reallocation import give_replacement_units

logger = logging.getLogger(__name__)

RESERVATION_REALLOCATED_ACTION: Final[str] = "reservation.reallocated"


class ReallocateUseCase(UseCase[ReservationCommand, ReservationView]):
    """Top up every short line of a booking, all or nothing, in one transaction."""

    def __init__(
        self, uow: UnitOfWork, clock: Clock, sweep: ExpireHoldsAndNoShowsUseCase
    ) -> None:
        """Keep the collaborators the use case works with.

        Args:
            uow: The unit of work that owns the transaction.
            clock: Where the current instant comes from.
            sweep: Lapses the holds and marks the no shows that are due first.

        """
        super().__init__(uow, clock)
        self._sweep = sweep

    def execute(self, command: ReservationCommand) -> ReservationView:
        """Give the booking replacement units and return it as the caller sees it.

        Raises:
            NotFound: If there is no such reservation.
            BranchScopeError: If counter staff act at another branch.
            StateTransitionError: If the booking is neither on hold nor confirmed.
            AllocationConflictError: If a line could not be given every unit
                it is short of. Nothing is allocated.

        """
        actor = command.actor
        logger.info(
            "reservation.reallocation_requested",
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
            before = state_of(reservation)
            allocator = allocator_for(
                uow,
                self._clock,
                reservation,
                line_models_of(uow, reservation),
                REALLOCATION_REFUSED_EVENT,
            )
            taken = give_replacement_units(reservation, allocator)
            if taken:
                record_change(
                    uow,
                    actor=actor,
                    reservation=reservation,
                    action=RESERVATION_REALLOCATED_ACTION,
                    occurred_at=now,
                    before=before,
                    extra={"asset_tags": sorted(allocator.asset_tags)},
                )
            detail = read_detail(uow, actor, ReservationKey.of(reservation.id))
            uow.commit()
        logger.info(
            "reservation.reallocation_finished",
            extra={
                "reference": reservation.reference,
                "reservation_id": str(reservation.id),
                "allocated_count": len(taken),
                "asset_tags": sorted(allocator.asset_tags),
            },
        )
        return view_for(actor, detail, now)
