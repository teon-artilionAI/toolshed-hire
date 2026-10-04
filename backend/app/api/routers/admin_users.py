"""User and role management, kept by an administrator (FR-25, US-35, BR-41, BR-44, BR-51).

`GET /api/admin/users` answers one page of the staff accounts, counter staff
and administrators, by name, narrowed by `role` and `active` and searched by
`q` on part of the name or the address. A customer's account is never listed,
because a customer is kept through their profile.

`POST /api/admin/users` opens a staff account and answers 201 with the account
and `emailDeliverable`. Nobody sets or sees a password. The person is sent the
reset link every account uses and chooses their own. `PATCH
/api/admin/users/{id}` changes the name, the phone, the role and the branch it
names. Counter staff need a branch and an administrator has none, each a 422
naming `branchCode`, and an address another account holds is a 422 naming
`email`. A role change takes effect on the next request the person makes,
because every request reads the role from the account.

`POST /api/admin/users/{id}/deactivation` stops the account signing in at once
and revokes every refresh session it holds with the reason `ADMIN_REVOKE`.
`POST /api/admin/users/{id}/reactivation` lets it sign in again with the
password it had. The last active administrator can never be deactivated or
given another role, and an administrator cannot deactivate their own account,
each a 409. Nothing is deleted, so there is no DELETE route.

Every route is for an administrator alone. The writes depend on `AdminUser`
and not on `FreshAdminUser`, because each use case reads the administrator
again under the lock it takes on every active administrator, which is stronger
than the shared lock and is what keeps two administrators changing each other
from waiting on each other for ever. Counter staff and customers are refused
with 403.
"""

from __future__ import annotations

from typing import Annotated, Final

from fastapi import APIRouter, Query, status
from pydantic import StringConstraints

from app.api.admin_presenter import ADMIN_PREFIX
from app.api.admin_user_deps import (
    DeactivateStaffAccount,
    EditStaffAccount,
    OpenStaffAccount,
    ReactivateStaffAccount,
    ReadStaffDependency,
)
from app.api.admin_user_presenter import (
    IDENTITY_TAG,
    USERS_PATH,
    UserPathKey,
    admin_user_page_response,
    admin_user_response,
    deactivation_command,
    edit_command,
    open_command,
    opened_response,
    reactivation_command,
)
from app.api.admin_user_schemas import (
    NO_LONGER_ADMINISTRATOR_RESPONSE,
    STAFF_CHANGE_REFUSED_RESPONSE,
    UNKNOWN_STAFF_RESPONSE,
    AdminUserPageResponse,
    AdminUserResponse,
    DeactivationRequest,
    StaffCreatedResponse,
    StaffCreateRequest,
    StaffUpdateRequest,
)
from app.api.booking_deps import actor_of
from app.api.deps import AdminUser
from app.api.report_schemas import ADMIN_ONLY_RESPONSE
from app.api.reservation_schemas import REFUSED_BODY_RESPONSE, REFUSED_QUERY_RESPONSE
from app.application.admin_lists import (
    DEFAULT_PAGE_SIZE,
    FIRST_PAGE,
    MAXIMUM_PAGE,
    MAXIMUM_PAGE_SIZE,
    MINIMUM_PAGE_SIZE,
)
from app.application.identity.staff_read_models import (
    MAXIMUM_STAFF_SEARCH_LENGTH,
    MINIMUM_STAFF_SEARCH_LENGTH,
)
from app.application.identity.staff_reads import StaffListRequest
from app.domain.enums import UserRole

router = APIRouter(prefix=f"{ADMIN_PREFIX}{USERS_PATH}", tags=[IDENTITY_TAG])

# Surrounding spaces are removed before the length is checked, as every other
# search does, so a search for two spaces is refused like one too short.
StaffSearchText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=MINIMUM_STAFF_SEARCH_LENGTH,
        max_length=MAXIMUM_STAFF_SEARCH_LENGTH,
    ),
]

WRITE_RESPONSES: Final[dict[int | str, dict[str, object]]] = {
    status.HTTP_403_FORBIDDEN: NO_LONGER_ADMINISTRATOR_RESPONSE,
    status.HTTP_404_NOT_FOUND: UNKNOWN_STAFF_RESPONSE,
    status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_BODY_RESPONSE,
}


@router.get(
    "",
    response_model=AdminUserPageResponse,
    summary="Return one page of the staff accounts, by name",
    responses={
        status.HTTP_403_FORBIDDEN: ADMIN_ONLY_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_QUERY_RESPONSE,
    },
)
def read_users(
    user: AdminUser,
    reads: ReadStaffDependency,
    q: Annotated[
        StaffSearchText | None, Query(description="Part of the name or the email address.")
    ] = None,
    role: Annotated[
        UserRole | None, Query(description="COUNTER_STAFF or ADMIN. Both when left out.")
    ] = None,
    active: Annotated[
        bool | None,
        Query(description="True for active accounts, false for deactivated ones."),
    ] = None,
    page: Annotated[
        int, Query(ge=FIRST_PAGE, le=MAXIMUM_PAGE, description="The page, counted from 1.")
    ] = FIRST_PAGE,
    page_size: Annotated[
        int,
        Query(
            alias="pageSize",
            ge=MINIMUM_PAGE_SIZE,
            le=MAXIMUM_PAGE_SIZE,
            description="How many accounts a page holds.",
        ),
    ] = DEFAULT_PAGE_SIZE,
) -> AdminUserPageResponse:
    """Return one page of the staff accounts that match, by name.

    Raises:
        ValidationFailure: If `role` is CUSTOMER. HTTP 422, naming `role`.

    """
    request = StaffListRequest(
        actor=actor_of(user), text=q, role=role, active=active, page=page, page_size=page_size
    )
    return admin_user_page_response(reads.page(request))


@router.post(
    "",
    response_model=StaffCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Open a staff account and send the person a link to choose their password",
    responses={
        status.HTTP_403_FORBIDDEN: NO_LONGER_ADMINISTRATOR_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_BODY_RESPONSE,
    },
)
def post_user(
    payload: StaffCreateRequest, user: AdminUser, use_case: OpenStaffAccount
) -> StaffCreatedResponse:
    """Open the account and record it, in one transaction, then send the link.

    Raises:
        ValidationFailure: If a field breaks a rule, the branch is unknown, or
            another account holds the address. HTTP 422, naming the field.
        AuthorisationFailure: If the caller stopped being an active
            administrator. HTTP 403.

    """
    return opened_response(use_case.execute(open_command(user, payload)))


@router.patch(
    "/{id}",
    response_model=AdminUserResponse,
    summary="Change the name, the phone, the role or the branch of a staff account",
    responses={**WRITE_RESPONSES, status.HTTP_409_CONFLICT: STAFF_CHANGE_REFUSED_RESPONSE},
)
def patch_user(
    user_id: UserPathKey, payload: StaffUpdateRequest, user: AdminUser, use_case: EditStaffAccount
) -> AdminUserResponse:
    """Change the fields that were sent and record the change.

    Raises:
        NotFound: If no staff account has the key. HTTP 404.
        ValidationFailure: If a field breaks a rule. HTTP 422, naming the field.
        StateTransitionError: If the account is the last active administrator
            and the edit gives it another role. HTTP 409.

    """
    return admin_user_response(use_case.execute(edit_command(user, user_id, payload)))


@router.post(
    "/{id}/deactivation",
    response_model=AdminUserResponse,
    summary="Stop a staff account signing in and revoke every session it holds",
    responses={**WRITE_RESPONSES, status.HTTP_409_CONFLICT: STAFF_CHANGE_REFUSED_RESPONSE},
)
def post_deactivation(
    user_id: UserPathKey,
    payload: DeactivationRequest,
    user: AdminUser,
    use_case: DeactivateStaffAccount,
) -> AdminUserResponse:
    """Deactivate the account, revoke its sessions and record why, in one transaction.

    Raises:
        NotFound: If no staff account has the key. HTTP 404.
        ValidationFailure: If the reason is out of bounds. HTTP 422, naming `reason`.
        StateTransitionError: If it is the caller's own account or the last
            active administrator. HTTP 409.

    """
    return admin_user_response(use_case.execute(deactivation_command(user, user_id, payload)))


@router.post(
    "/{id}/reactivation",
    response_model=AdminUserResponse,
    summary="Let a deactivated staff account sign in again with its own password",
    responses={
        status.HTTP_403_FORBIDDEN: NO_LONGER_ADMINISTRATOR_RESPONSE,
        status.HTTP_404_NOT_FOUND: UNKNOWN_STAFF_RESPONSE,
    },
)
def post_reactivation(
    user_id: UserPathKey, user: AdminUser, use_case: ReactivateStaffAccount
) -> AdminUserResponse:
    """Reactivate the account and record it.

    Raises:
        NotFound: If no staff account has the key. HTTP 404.

    """
    return admin_user_response(use_case.execute(reactivation_command(user, user_id)))
