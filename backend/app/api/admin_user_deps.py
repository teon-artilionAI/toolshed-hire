"""The dependencies of user and role management and of the customer holds.

This is the part of the composition root behind the people screens of the
admin console. The reads go through `SqlStaffDirectory` and
`SqlCustomerListing` over the request scoped session. Each staff write runs on
the unit of work of the request and reads its answer back through the same
staff directory once it has committed, which is the session the unit of work
borrowed. Opening an account is also handed the password hasher and the mailer
of the account messages, which `app/api/account_deps.py` already builds.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.api.account_deps import AccountMailerDependency, PasswordHasherDependency
from app.api.deps import ClockDependency, SessionDependency, UnitOfWorkDependency
from app.application.identity.customer_listing import CustomerListing, ReadCustomerList
from app.application.identity.customer_standing import ChangeCustomerStandingUseCase
from app.application.identity.staff_access import (
    DeactivateStaffAccountUseCase,
    ReactivateStaffAccountUseCase,
)
from app.application.identity.staff_accounts import OpenStaffAccountUseCase
from app.application.identity.staff_edit import EditStaffAccountUseCase
from app.application.identity.staff_read_models import StaffDirectory
from app.application.identity.staff_reads import ReadStaff
from app.infrastructure.customer_listing import SqlCustomerListing
from app.infrastructure.staff_query import SqlStaffDirectory


def get_staff_directory(session: SessionDependency) -> StaffDirectory:
    """Return the SQL staff directory over the request scoped session."""
    return SqlStaffDirectory(session)


StaffDirectoryDependency = Annotated[StaffDirectory, Depends(get_staff_directory)]


def get_customer_listing(session: SessionDependency) -> CustomerListing:
    """Return the SQL list of customers by standing over the request scoped session."""
    return SqlCustomerListing(session)


def get_read_staff(directory: StaffDirectoryDependency) -> ReadStaff:
    """Return the read of the staff accounts."""
    return ReadStaff(directory)


def get_read_customer_list(
    listing: Annotated[CustomerListing, Depends(get_customer_listing)],
) -> ReadCustomerList:
    """Return the read of the customers by standing."""
    return ReadCustomerList(listing)


def get_open_staff_account_use_case(
    uow: UnitOfWorkDependency,
    clock: ClockDependency,
    directory: StaffDirectoryDependency,
    passwords: PasswordHasherDependency,
    mailer: AccountMailerDependency,
) -> OpenStaffAccountUseCase:
    """Return the use case that opens a staff account and sends its reset link."""
    return OpenStaffAccountUseCase(uow, clock, directory, passwords, mailer)


def get_edit_staff_account_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency, directory: StaffDirectoryDependency
) -> EditStaffAccountUseCase:
    """Return the use case that edits a staff account."""
    return EditStaffAccountUseCase(uow, clock, directory)


def get_deactivate_staff_account_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency, directory: StaffDirectoryDependency
) -> DeactivateStaffAccountUseCase:
    """Return the use case that deactivates a staff account."""
    return DeactivateStaffAccountUseCase(uow, clock, directory)


def get_reactivate_staff_account_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency, directory: StaffDirectoryDependency
) -> ReactivateStaffAccountUseCase:
    """Return the use case that reactivates a staff account."""
    return ReactivateStaffAccountUseCase(uow, clock, directory)


def get_change_customer_standing_use_case(
    uow: UnitOfWorkDependency, clock: ClockDependency
) -> ChangeCustomerStandingUseCase:
    """Return the use case that sets the standing of a customer."""
    return ChangeCustomerStandingUseCase(uow, clock)


ReadStaffDependency = Annotated[ReadStaff, Depends(get_read_staff)]
ReadCustomerListDependency = Annotated[ReadCustomerList, Depends(get_read_customer_list)]
OpenStaffAccount = Annotated[OpenStaffAccountUseCase, Depends(get_open_staff_account_use_case)]
EditStaffAccount = Annotated[EditStaffAccountUseCase, Depends(get_edit_staff_account_use_case)]
DeactivateStaffAccount = Annotated[
    DeactivateStaffAccountUseCase, Depends(get_deactivate_staff_account_use_case)
]
ReactivateStaffAccount = Annotated[
    ReactivateStaffAccountUseCase, Depends(get_reactivate_staff_account_use_case)
]
ChangeCustomerStanding = Annotated[
    ChangeCustomerStandingUseCase, Depends(get_change_customer_standing_use_case)
]
