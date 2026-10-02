"""The use case that puts a draft on hold, which is where units are taken (FR-06).

Holding gives every line of a reservation specific tagged units (BR-07) and
starts the thirty minutes the customer has to confirm (BR-12). It is all or
nothing (BR-09, US-12). Every line is allocated in one unit of work, and a
line that cannot be given all of its units fails the whole hold, so a
reservation never holds two of the three machines it asked for.

The units are found and locked by the existing allocation algorithm, through
the asset repository, which is the one place that locks candidate units. The
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
from collections.abc import Mapping, Sequence
from datetime import date
from uuid import UUID

from app.application.availability.allocation import AllocationCommand, allocate_assets
from app.application.availability.ports import AssetRepository
from app.application.booking.access import (
    RESERVATION_HELD_ACTION,
    ReservationCommand,
    customer_of,
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
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.availability import AssetAllocation
from app.domain.booking import Reservation, ReservationLine
from app.domain.catalogue import ProductModel
from app.domain.errors import AllocationConflictError

logger = logging.getLogger(__name__)


def date_in_words(day: date) -> str:
    """Return a date as a customer reads it, for example 9 March 2026."""
    return f"{day.day} {day:%B} {day.year}"


class _RepositoryAllocator:
    """Takes the units of one line through the allocation algorithm.

    This is the `UnitAllocator` the draft state asks for units through. It
    keeps the tags of what it held, for the audit event.
    """

    def __init__(
        self,
        assets: AssetRepository,
        clock: Clock,
        models: Mapping[UUID, ProductModel],
        branch_name: str,
    ) -> None:
        """Bind the allocator to the asset repository of the open unit of work."""
        self._assets = assets
        self._clock = clock
        self._models = models
        self._branch_name = branch_name
        self.asset_tags: list[str] = []

    def allocate(
        self, reservation: Reservation, line: ReservationLine
    ) -> Sequence[AssetAllocation]:
        """Hold the units of one line, or refuse in words a customer can act on.

        Raises:
            AllocationConflictError: If too few units are free, or the
                exclusion constraint refused one. The sentence names the model
                and the dates and carries no count.

        """
        model = self._models[line.product_model_id]
        period = reservation.period
        try:
            held = allocate_assets(
                self._assets,
                self._clock,
                AllocationCommand(
                    reservation_line_id=line.id,
                    product_model_id=line.product_model_id,
                    branch_id=reservation.branch_id,
                    period=period,
                    quantity=line.quantity,
                ),
            )
        except AllocationConflictError as conflict:
            logger.warning(
                "reservation.hold_refused",
                extra={
                    "reference": reservation.reference,
                    "sku": model.sku,
                    "period": period.as_postgres_daterange(),
                    "requested_quantity": line.quantity,
                    "available_quantity": conflict.detail.get("available_quantity"),
                    "constraint": conflict.detail.get("constraint_name"),
                    "outcome": "nothing was allocated",
                },
            )
            raise AllocationConflictError(
                f"{model.name} is not available at {self._branch_name} from "
                f"{date_in_words(period.start)} to {date_in_words(period.end)}. "
                "Choose other dates or another branch.",
                model_slug=model.slug,
                period=period.as_postgres_daterange(),
            ) from conflict
        self.asset_tags.extend(item.asset_tag for item in held)
        return [item.allocation for item in held]


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
            before = state_of(reservation)
            models = _models_of(uow, reservation)
            allocator = _RepositoryAllocator(
                uow.assets, self._clock, models, _branch_name_of(uow, reservation)
            )
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


def _models_of(uow: UnitOfWork, reservation: Reservation) -> dict[UUID, ProductModel]:
    """Return the product model of every line, by its key.

    Raises:
        LookupError: If a model cannot be read. A line carries a foreign key
            to its model and nothing is ever deleted, so this is a fault in
            the data and not something a caller can put right.

    """
    models: dict[UUID, ProductModel] = {}
    for line in reservation.lines:
        model = uow.product_models.get(line.product_model_id)
        if model is None:
            raise LookupError(
                f"Attempted to hold reservation {reservation.reference}, and product model "
                f"{line.product_model_id} of line {line.line_position} could not be read."
            )
        models[model.id] = model
    return models


def _branch_name_of(uow: UnitOfWork, reservation: Reservation) -> str:
    """Return the name of the collection branch, for the sentence of a conflict."""
    branch = uow.branches.get(reservation.branch_id)
    return branch.name if branch is not None else "this branch"
