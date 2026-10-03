"""The dependencies of the hire module, which are checkout and the rental read.

This is the hire part of the composition root. `app/api/deps.py` wires the
unit of work and the clock, and this module puts them together into the use
case and the reads the checkout and rental routes call. Both run on the unit
of work of the request.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.api.deps import ClockDependency, UnitOfWorkDependency
from app.application.hire.checkout import CheckoutRentalUseCase
from app.application.hire.read_rental import ReadRentals


def get_checkout_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency
) -> CheckoutRentalUseCase:
    """Return the use case that checks a reservation out."""
    return CheckoutRentalUseCase(uow, clock)


def get_read_rentals(uow: UnitOfWorkDependency, clock: ClockDependency) -> ReadRentals:
    """Return the reads of the hire module."""
    return ReadRentals(uow, clock)


CheckoutRental = Annotated[CheckoutRentalUseCase, Depends(get_checkout_use_case)]
ReadRentalsDependency = Annotated[ReadRentals, Depends(get_read_rentals)]
