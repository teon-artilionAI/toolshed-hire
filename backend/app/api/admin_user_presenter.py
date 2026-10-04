"""What the routes of user and role management share, the path keys, the commands and the responses.

A request body becomes a command here and a read model becomes a response
here, once, so the routers stay about their routes. Nothing is worked out in
it but the one thing the boundary owns, which is that a branch code is read
in capitals, the way the branches are known.

An edit becomes a set of `Change`s, one for each field the request named, so
a field left out is told apart from a field sent as null.
"""

from __future__ import annotations

from typing import Annotated, Final
from uuid import UUID

from fastapi import Path

from app.api.admin_catalogue_presenter import cleared_or_sent, sent
from app.api.admin_user_schemas import (
    AdminUserPageResponse,
    AdminUserResponse,
    CustomerStatusRequest,
    DeactivationRequest,
    StaffCreatedResponse,
    StaffCreateRequest,
    StaffUpdateRequest,
)
from app.api.booking_deps import actor_of
from app.application.catalogue.admin_commands import Change
from app.application.identity.customer_standing import ChangeCustomerStandingCommand
from app.application.identity.staff_commands import (
    DeactivateStaffAccountCommand,
    EditStaffAccountCommand,
    OpenStaffAccountCommand,
    ReactivateStaffAccountCommand,
    StaffAccountOpened,
    StaffChanges,
)
from app.application.identity.staff_read_models import StaffMember, StaffPage
from app.domain.staff_account import BRANCH_CODE, ROLE, STAFF_FULL_NAME, STAFF_PHONE
from app.infrastructure.models import UserAccount

# The tag of the routers, which is the module the accounts belong to.
IDENTITY_TAG: Final[str] = "identity"
USERS_PATH: Final[str] = "/users"
CUSTOMERS_PATH: Final[str] = "/customers"

UserPathKey = Annotated[UUID, Path(alias="id", description="The key of the staff account.")]
CustomerPathKey = Annotated[UUID, Path(alias="id", description="The key of the customer.")]


def branch_code(code: str | None) -> str | None:
    """Return a branch code as it is stored, trimmed and in capitals, or None."""
    return code.strip().upper() if code is not None else None


def open_command(user: UserAccount, request: StaffCreateRequest) -> OpenStaffAccountCommand:
    """Return the command that opens the staff account a request describes."""
    return OpenStaffAccountCommand(
        actor=actor_of(user),
        email=request.email,
        full_name=request.full_name,
        phone=request.phone,
        role=request.role,
        branch_code=branch_code(request.branch_code),
    )


def edit_command(
    user: UserAccount, user_id: UUID, request: StaffUpdateRequest
) -> EditStaffAccountCommand:
    """Return the command that changes the fields an edit named."""
    named_branch = cleared_or_sent(request, BRANCH_CODE, request.branch_code)
    return EditStaffAccountCommand(
        actor=actor_of(user),
        user_id=user_id,
        changes=StaffChanges(
            full_name=sent(request, STAFF_FULL_NAME, request.full_name),
            phone=cleared_or_sent(request, STAFF_PHONE, request.phone),
            role=sent(request, ROLE, request.role),
            branch_code=(
                Change(branch_code(named_branch.value)) if named_branch is not None else None
            ),
        ),
    )


def deactivation_command(
    user: UserAccount, user_id: UUID, request: DeactivationRequest
) -> DeactivateStaffAccountCommand:
    """Return the command that stops an account signing in."""
    return DeactivateStaffAccountCommand(
        actor=actor_of(user), user_id=user_id, reason=request.reason
    )


def reactivation_command(user: UserAccount, user_id: UUID) -> ReactivateStaffAccountCommand:
    """Return the command that lets an account sign in again."""
    return ReactivateStaffAccountCommand(actor=actor_of(user), user_id=user_id)


def standing_command(
    user: UserAccount, customer_id: UUID, request: CustomerStatusRequest
) -> ChangeCustomerStandingCommand:
    """Return the command that sets the standing of a customer."""
    return ChangeCustomerStandingCommand(
        actor=actor_of(user),
        customer_profile_id=customer_id,
        account_status=request.account_status,
        reason=request.reason,
    )


def admin_user_response(member: StaffMember) -> AdminUserResponse:
    """Write one staff account in the shape the contract gives `AdminUser`."""
    return AdminUserResponse(
        id=member.id,
        email=member.email,
        full_name=member.full_name,
        phone=member.phone,
        role=member.role,
        branch_code=member.branch_code,
        is_active=member.is_active,
        email_verified=member.email_verified,
        last_login_at=member.last_login_at,
        locked_until=member.locked_until,
        created_at=member.created_at,
    )


def opened_response(opened: StaffAccountOpened) -> StaffCreatedResponse:
    """Write a new staff account with whether the email with its link was taken."""
    return StaffCreatedResponse(
        user=admin_user_response(opened.member), email_deliverable=opened.email_deliverable
    )


def admin_user_page_response(page: StaffPage) -> AdminUserPageResponse:
    """Write one page of the staff accounts in the shape the contract gives a list."""
    return AdminUserPageResponse(
        items=[admin_user_response(member) for member in page.items],
        page=page.page,
        page_size=page.page_size,
        total=page.total,
    )
