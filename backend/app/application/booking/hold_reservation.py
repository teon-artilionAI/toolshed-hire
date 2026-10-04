"""The use case that puts a draft on hold, which is where units are taken (FR-06).

Holding gives every line of a reservation specific tagged units (BR-07) and
starts the thirty minutes the customer has to confirm (BR-12). It is all or
nothing (BR-09, US-12). Every line is allocated in one unit of work, and a
line that cannot be given all of its units fails the whole hold, so a
reservation never holds two of the three machines it asked for.

The units are found and locked by the existing allocation algorithm, through
the asset repository, which is the one place that locks candidate units, by
the allocator in `app.application.booking.unit_allocator`. The
exclusion constraint still has the last word. When it refuses an insert the
answer is the same clean conflict as when too few units were free.

The reservation state decides whether the hold may happen at all, and it is
the state that asks for the units, once every date guard has passed. This use
case supplies the allocator the state takes them through.

The conflict a customer is shown names the model and the dates. It never says
how many units are left (US-07). The counts go to the log.

Before anything is decided the sweep lapses the holds that have run out, so a
unit somebody stopped wanting half an hour ago is free to be held here.
"""

from __future__ import annotations

import logging

from app.application.booking.access import (
    RESERVATION_HELD_ACTION,
    ReservationCommand,
    customer_of,
    ensure_collection_branch_open,
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
from app.application.booking.unit_allocator import allocator_for, line_models_of
from app.application.booking.views import ReservationView, view_for
from app.application.clock import Clock
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.states.base import HOLD_MOVE

logger = logging.getLogger(__name__)


class HoldReservationUseCase(UseCase[ReservationCommand, ReservationView]):
    """Put a draft on hold, with every line allocated, in one transaction."""

    def __init__(
        self, uow: UnitOfWork, clock: Clock, sweep: ExpireHoldsAndNoShowsUseCase
    ) -> None:
        """Keep the collaborators the use case works with.

        Args:
            uow: The unit of work that owns the transaction.
            clock: Where the current instant and business day come from.
            sweep: Lapses the holds that have run out, before units are looked for.

        """
        super().__init__(uow, clock)
        self._sweep = sweep

    def execute(self, command: ReservationCommand) -> ReservationView:
        """Hold the reservation and return it as the caller sees it.

        Raises:
            NotFound: If there is no such reservation, or it is not the caller's.
            BranchScopeError: If counter staff act at another branch.
            AccountOnHoldError: If the customer's account is on hold (BR-18).
            StateTransitionError: If the reservation is not a draft.
            ValidationFailure: If the dates can no longer be booked.
            AllocationConflictError: If a line could not be given every unit.
                Nothing is allocated.

        """
        actor = command.actor
        logger.info(
            "reservation.hold_requested",
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
            customer_of(uow, reservation).ensure_may_book()
            if reservation.state.permits(HOLD_MOVE):
                ensure_collection_branch_open(uow, reservation, now)
            before = state_of(reservation)
            models = line_models_of(uow, reservation)
            allocator = allocator_for(uow, self._clock, reservation, models)
            reservation.hold(
                now=now, today=self._clock.today(), models=models, allocator=allocator
            )
            uow.reservations.save(reservation)
            record_change(
                uow,
                actor=actor,
                reservation=reservation,
                action=RESERVATION_HELD_ACTION,
                occurred_at=now,
                before=before,
                extra={"asset_tags": sorted(allocator.asset_tags)},
            )
            detail = read_detail(uow, actor, ReservationKey.of(reservation.id))
            uow.commit()
        logger.info(
            "reservation.hold_finished",
            extra={
                "reference": reservation.reference,
                "reservation_id": str(reservation.id),
                "outcome": reservation.status.value,
                "allocated_count": len(allocator.asset_tags),
            },
        )
        return view_for(actor, detail, now)
