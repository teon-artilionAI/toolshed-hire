"""The dependencies of the booking module, which are its use cases and its sweep.

This is the booking half of the composition root. `app/api/deps.py` wires the
unit of work, the clock and the dispatcher, and `app/api/pricing_deps.py`
chooses the pricing policy. This module puts those together into the use cases
a reservation route calls.

Every use case that could be misled by an expired hold is handed the sweep
that lapses them (BR-13), which is wired in `app/api/sweep_deps.py`. It runs
on the unit of work of the request, in a transaction of its own, so a sweep is
committed before the question that follows it is asked.

`actor_of` turns the account the request authenticated as into the actor a use
case is handed. A router calls it before the use case runs, because a commit
expires the loaded account, and the role an audit event records is the one
held at this moment.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.api.deps import ClockDependency, NotificationDispatcherDependency, UnitOfWorkDependency
from app.api.pricing_deps import PricingPolicyDependency
from app.api.sweep_deps import HoldSweepDependency
from app.application.booking.cancel_reservation import CancelReservationUseCase
from app.application.booking.confirm_reservation import ConfirmReservationUseCase
from app.application.booking.create_reservation import CreateReservationUseCase
from app.application.booking.hold_reservation import HoldReservationUseCase
from app.application.booking.mark_no_show import MarkNoShowUseCase
from app.application.booking.read_reservation import ReadReservations
from app.domain.identity import Actor
from app.infrastructure.models import UserAccount


def actor_of(user: UserAccount) -> Actor:
    """Return the signed in account as the actor of an operation."""
    return Actor(user_id=user.id, role=user.role, branch_id=user.branch_id)


def get_create_reservation_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency, pricing: PricingPolicyDependency
) -> CreateReservationUseCase:
    """Return the use case that creates a draft, wired to the pricing policy."""
    return CreateReservationUseCase(uow, clock, pricing)


def get_hold_reservation_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency, sweep: HoldSweepDependency
) -> HoldReservationUseCase:
    """Return the use case that puts a draft on hold, wired to the sweep."""
    return HoldReservationUseCase(uow, clock, sweep)


def get_confirm_reservation_use_case(
    uow: UnitOfWorkDependency,
    clock: ClockDependency,
    sweep: HoldSweepDependency,
    dispatcher: NotificationDispatcherDependency,
) -> ConfirmReservationUseCase:
    """Return the use case that confirms a hold, wired to the sweep and the dispatcher."""
    return ConfirmReservationUseCase(uow, clock, sweep, dispatcher)


def get_cancel_reservation_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency
) -> CancelReservationUseCase:
    """Return the use case that cancels a reservation."""
    return CancelReservationUseCase(uow, clock)


def get_mark_no_show_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency
) -> MarkNoShowUseCase:
    """Return the use case by which staff mark a reservation as not collected."""
    return MarkNoShowUseCase(uow, clock)


def get_read_reservations(
    uow: UnitOfWorkDependency, clock: ClockDependency, sweep: HoldSweepDependency
) -> ReadReservations:
    """Return the reads of the booking module, wired to the sweep."""
    return ReadReservations(uow, clock, sweep)


CreateReservation = Annotated[CreateReservationUseCase, Depends(get_create_reservation_use_case)]
HoldReservation = Annotated[HoldReservationUseCase, Depends(get_hold_reservation_use_case)]
ConfirmReservation = Annotated[
    ConfirmReservationUseCase, Depends(get_confirm_reservation_use_case)
]
CancelReservation = Annotated[CancelReservationUseCase, Depends(get_cancel_reservation_use_case)]
MarkNoShow = Annotated[MarkNoShowUseCase, Depends(get_mark_no_show_use_case)]
ReadReservationsDependency = Annotated[ReadReservations, Depends(get_read_reservations)]
