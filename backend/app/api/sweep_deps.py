"""The dependency that lapses expired holds before a question is answered (BR-13).

A hold that has run out still occupies its units until something lapses it,
and nothing does that on a timer. The sweep is run instead by whatever is
about to decide or report something an expired hold could spoil. The booking
use cases are handed the sweep itself. The availability search only needs it
run, so it is handed a call that runs it once.

The sweep is wired in a module of its own because both the booking
dependencies and the catalogue dependencies need it, and neither may import
the other.

It runs on the unit of work of the request and commits what it lapsed before
it returns. On a route with no credential it still writes, because the visitor
who searches availability is as entitled to a true answer as anybody else. Its
audit events carry no actor.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends

from app.api.deps import ClockDependency, UnitOfWorkDependency
from app.application.booking.expire_holds import ExpireHoldsAndNoShowsUseCase, SweepCommand


def get_hold_sweep(
    uow: UnitOfWorkDependency, clock: ClockDependency
) -> ExpireHoldsAndNoShowsUseCase:
    """Return the sweep that lapses expired holds, on the unit of work of the request."""
    return ExpireHoldsAndNoShowsUseCase(uow, clock)


HoldSweepDependency = Annotated[ExpireHoldsAndNoShowsUseCase, Depends(get_hold_sweep)]


def get_expired_hold_sweeper(sweep: HoldSweepDependency) -> Callable[[], object]:
    """Return a call that runs the sweep once, for a read that only needs it run."""
    return lambda: sweep.execute(SweepCommand())


ExpiredHoldSweeper = Annotated[Callable[[], object], Depends(get_expired_hold_sweeper)]
