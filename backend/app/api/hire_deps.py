"""The dependencies of the hire module, which are checkout, returns, settlement and the reads.

This is the hire part of the composition root. `app/api/deps.py` wires the
unit of work and the clock, `app/api/late_fee_deps.py` the late fee policy,
and `app/api/sweep_deps.py` the lazy sweep. This module puts them together
into the use cases and the reads the checkout and rental routes call. All of
them run on the unit of work of the request.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.api.deps import ClockDependency, UnitOfWorkDependency
from app.api.late_fee_deps import LateFeePolicyDependency
from app.api.sweep_deps import ExpiredHoldSweeper
from app.application.hire.balance_payment import RecordBalancePaymentUseCase
from app.application.hire.checkout import CheckoutRentalUseCase
from app.application.hire.list_rentals import ListRentals
from app.application.hire.loss import RecordLossUseCase
from app.application.hire.read_rental import ReadRentals
from app.application.hire.returns import ReturnRentalItemsUseCase


def get_checkout_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency, policy: LateFeePolicyDependency
) -> CheckoutRentalUseCase:
    """Return the use case that checks a reservation out."""
    return CheckoutRentalUseCase(uow, clock, policy)


def get_read_rentals(
    uow: UnitOfWorkDependency, clock: ClockDependency, policy: LateFeePolicyDependency
) -> ReadRentals:
    """Return the reads of one rental and of one checkout."""
    return ReadRentals(uow, clock, policy)


def get_list_rentals(
    uow: UnitOfWorkDependency,
    clock: ClockDependency,
    policy: LateFeePolicyDependency,
    sweep: ExpiredHoldSweeper,
) -> ListRentals:
    """Return the two lists of rentals, wired to the sweep the staff list runs first."""
    return ListRentals(uow, clock, policy, sweep)


def get_return_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency, policy: LateFeePolicyDependency
) -> ReturnRentalItemsUseCase:
    """Return the use case that takes units back."""
    return ReturnRentalItemsUseCase(uow, clock, policy)


def get_loss_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency, policy: LateFeePolicyDependency
) -> RecordLossUseCase:
    """Return the use case that records a unit as lost."""
    return RecordLossUseCase(uow, clock, policy)


def get_balance_payment_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency, policy: LateFeePolicyDependency
) -> RecordBalancePaymentUseCase:
    """Return the use case that records the payment of a balance."""
    return RecordBalancePaymentUseCase(uow, clock, policy)


CheckoutRental = Annotated[CheckoutRentalUseCase, Depends(get_checkout_use_case)]
ReadRentalsDependency = Annotated[ReadRentals, Depends(get_read_rentals)]
ListRentalsDependency = Annotated[ListRentals, Depends(get_list_rentals)]
ReturnItems = Annotated[ReturnRentalItemsUseCase, Depends(get_return_use_case)]
RecordLoss = Annotated[RecordLossUseCase, Depends(get_loss_use_case)]
RecordBalancePayment = Annotated[
    RecordBalancePaymentUseCase, Depends(get_balance_payment_use_case)
]
