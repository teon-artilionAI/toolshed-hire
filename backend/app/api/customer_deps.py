"""The dependencies of the counter's customer routes, which are the lookup and the walk-in.

This is the customer part of the composition root. `app/api/deps.py` wires the
unit of work and the clock, and this module puts them together into the lookup
and the use case the customer routes call. Both run on the unit of work of the
request.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.api.deps import ClockDependency, UnitOfWorkDependency
from app.application.identity.customer_lookup import LookUpCustomers
from app.application.identity.walk_in import RegisterWalkInUseCase


def get_customer_lookup(uow: UnitOfWorkDependency) -> LookUpCustomers:
    """Return the counter's customer lookup."""
    return LookUpCustomers(uow)


def get_register_walk_in_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency
) -> RegisterWalkInUseCase:
    """Return the use case that registers a walk-in."""
    return RegisterWalkInUseCase(uow, clock)


CustomerLookup = Annotated[LookUpCustomers, Depends(get_customer_lookup)]
RegisterWalkIn = Annotated[RegisterWalkInUseCase, Depends(get_register_walk_in_use_case)]
