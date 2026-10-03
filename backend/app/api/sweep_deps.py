"""The dependency that runs the lazy sweep before a question is answered (BR-13, BR-17).

A hold that has run out still occupies its units until something lapses it,
and a confirmed booking nobody collected still holds its units until something
marks it as a no show. Nothing does either on a timer. The sweep is run instead
by whatever is about to decide or report something they could spoil. The
booking use cases are handed the sweep itself. The availability search and the
counter's dashboard and diary only need it run, so they are handed a call that
runs it once.

The sweep is wired in a module of its own because the booking, catalogue and
counter dependencies all need it, and none of them may import another.

It runs on the unit of work of the request and commits what it changed before
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
    """Return the sweep of holds and no shows, on the unit of work of the request."""
    return ExpireHoldsAndNoShowsUseCase(uow, clock)


HoldSweepDependency = Annotated[ExpireHoldsAndNoShowsUseCase, Depends(get_hold_sweep)]


def get_expired_hold_sweeper(sweep: HoldSweepDependency) -> Callable[[], object]:
    """Return a call that runs the sweep once, for a read that only needs it run."""
    return lambda: sweep.execute(SweepCommand())


ExpiredHoldSweeper = Annotated[Callable[[], object], Depends(get_expired_hold_sweeper)]
