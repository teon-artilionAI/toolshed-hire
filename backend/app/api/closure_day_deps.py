"""The dependencies of the owner's closure days (B9.5).

This is the part of the composition root behind the trading calendar of the
admin console. The two reads go through `SqlClosureDayQuery` over the request
scoped session, with the branches read through `SqlBranchRepository` on the
same session, because a read writes nothing and needs no unit of work. Adding
and cancelling a closure run on the unit of work of the request.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.api.deps import ClockDependency, SessionDependency, UnitOfWorkDependency
from app.application.trading.closure_days import AddClosureDayUseCase, CancelClosureDayUseCase
from app.application.trading.closure_reads import ReadClosureDays
from app.infrastructure.branch_repository import SqlBranchRepository
from app.infrastructure.closure_day_query import SqlClosureDayQuery


def get_read_closure_days(session: SessionDependency, clock: ClockDependency) -> ReadClosureDays:
    """Return the read of the closed days and of the bookings a closure strands."""
    return ReadClosureDays(SqlClosureDayQuery(session), SqlBranchRepository(session), clock)


def get_add_closure_day_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency
) -> AddClosureDayUseCase:
    """Return the use case that closes a branch, or every branch, on a day."""
    return AddClosureDayUseCase(uow, clock)


def get_cancel_closure_day_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency
) -> CancelClosureDayUseCase:
    """Return the use case that opens a closed day again."""
    return CancelClosureDayUseCase(uow, clock)


ReadClosureDaysDependency = Annotated[ReadClosureDays, Depends(get_read_closure_days)]
AddClosureDay = Annotated[AddClosureDayUseCase, Depends(get_add_closure_day_use_case)]
CancelClosureDay = Annotated[CancelClosureDayUseCase, Depends(get_cancel_closure_day_use_case)]
