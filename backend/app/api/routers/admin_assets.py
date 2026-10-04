"""The asset register, kept by an administrator (FR-23, US-31, US-32, BR-34, BR-37, BR-38).

`GET /api/admin/assets` answers one page of every unit of the fleet, retired
or not, in tag order, narrowed by `branchCode`, `status` and `modelId` and
searched by `q` on part of the tag, the serial number or the model name.
`GET /api/admin/assets/{tag}` answers one unit with its history, built from
its allocations, its hires, its damage reports and its audit events, the
newest first and at most fifty entries.

`POST /api/admin/assets` registers a unit at INTAKE and answers 201. A tag
another unit carries is a 422 naming `assetTag`. `PATCH /api/admin/assets/{tag}`
changes the serial number, the grade, the meter reading and the notes it
names. The tag, the model and the branch never change (BR-34), so an edit
that sends one is a 422 naming it.

`POST /api/admin/assets/{tag}/transitions` moves a unit to the status it
names, through the asset state model. A move the model does not permit from
the unit's status is a 409 naming that status, and so is a retirement while a
booking still holds the unit, which names the booking (BR-37). ON_HIRE and
LOST are never set here, because only checkout and the loss route set them,
which is a 422 naming `to`. A move into quarantine, to repair or to
retirement needs a reason, a 422 naming `reason` without one. A retirement
stamps `retiredOn` and keeps the row (BR-38).

Every write answers the unit with its history, read once the change has
committed, so the screen shows the move it just made. Every route is for an
administrator alone, and every write reads the account again under a row
lock for the length of the change (`FreshAdminUser`). Counter staff and
customers are refused with 403.
"""

from __future__ import annotations

from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Query, status
from pydantic import StringConstraints

from app.api.admin_asset_deps import (
    EditUnit,
    MoveUnit,
    ReadAssetRegisterDependency,
    RegisterUnit,
)
from app.api.admin_asset_presenter import (
    ASSETS_PATH,
    CATALOGUE_TAG,
    AssetPathTag,
    asset_detail_response,
    asset_page_response,
    edit_command,
    move_command,
    path_tag,
    register_command,
)
from app.api.admin_asset_schemas import (
    MOVE_REFUSED_RESPONSE,
    UNKNOWN_UNIT_RESPONSE,
    AdminAssetDetailResponse,
    AdminAssetPageResponse,
    AssetCreateRequest,
    AssetTransitionRequest,
    AssetUpdateRequest,
)
from app.api.admin_presenter import ADMIN_PREFIX
from app.api.booking_deps import actor_of
from app.api.deps import AdminUser
from app.api.identity_deps import FreshAdminUser
from app.api.report_schemas import ADMIN_ONLY_RESPONSE
from app.api.reservation_schemas import REFUSED_BODY_RESPONSE, REFUSED_QUERY_RESPONSE
from app.application.admin_lists import (
    DEFAULT_PAGE_SIZE,
    FIRST_PAGE,
    MAXIMUM_PAGE,
    MAXIMUM_PAGE_SIZE,
    MINIMUM_PAGE_SIZE,
)
from app.application.catalogue.asset_reads import ListUnitsQuery
from app.application.catalogue.locator import (
    MAXIMUM_LOCATOR_SEARCH_LENGTH,
    MINIMUM_LOCATOR_SEARCH_LENGTH,
)
from app.domain.enums import AssetStatus

router = APIRouter(prefix=f"{ADMIN_PREFIX}{ASSETS_PATH}", tags=[CATALOGUE_TAG])

# Surrounding spaces are removed before the length is checked, as the
# locator does, so a search for two spaces is refused like one too short.
RegisterSearchText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=MINIMUM_LOCATOR_SEARCH_LENGTH,
        max_length=MAXIMUM_LOCATOR_SEARCH_LENGTH,
    ),
]

WRITE_RESPONSES: Final[dict[int | str, dict[str, object]]] = {
    status.HTTP_403_FORBIDDEN: ADMIN_ONLY_RESPONSE,
    status.HTTP_404_NOT_FOUND: UNKNOWN_UNIT_RESPONSE,
    status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_BODY_RESPONSE,
}


@router.get(
    "",
    response_model=AdminAssetPageResponse,
    summary="Return one page of the units of the fleet, retired or not, in tag order",
    responses={
        status.HTTP_403_FORBIDDEN: ADMIN_ONLY_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_QUERY_RESPONSE,
    },
)
def read_assets(
    user: AdminUser,
    reads: ReadAssetRegisterDependency,
    q: Annotated[
        RegisterSearchText | None,
        Query(description="Part of the tag, the serial number or the model name."),
    ] = None,
    branch_code: Annotated[
        str | None,
        Query(alias="branchCode", description="A branch code. Only the units it holds."),
    ] = None,
    unit_status: Annotated[
        AssetStatus | None, Query(alias="status", description="Only the units in this status.")
    ] = None,
    model_id: Annotated[
        UUID | None, Query(alias="modelId", description="Only the units of this product model.")
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
            description="How many units a page holds.",
        ),
    ] = DEFAULT_PAGE_SIZE,
) -> AdminAssetPageResponse:
    """Return one page of the units that match, in tag order.

    Raises:
        ValidationFailure: If no branch has the code. HTTP 422, naming `branchCode`.

    """
    query = ListUnitsQuery(
        text=q,
        branch_code=branch_code.strip().upper() if branch_code else None,
        status=unit_status,
        model_id=model_id,
        page=page,
        page_size=page_size,
    )
    return asset_page_response(reads.page(actor_of(user), query))


@router.get(
    "/{tag}",
    response_model=AdminAssetDetailResponse,
    summary="Return one unit with its history, the newest first",
    responses={
        status.HTTP_403_FORBIDDEN: ADMIN_ONLY_RESPONSE,
        status.HTTP_404_NOT_FOUND: UNKNOWN_UNIT_RESPONSE,
    },
)
def read_asset(
    tag: AssetPathTag, user: AdminUser, reads: ReadAssetRegisterDependency
) -> AdminAssetDetailResponse:
    """Return the unit with its history.

    Raises:
        NotFound: If no unit carries the tag. HTTP 404.

    """
    return asset_detail_response(reads.unit(actor_of(user), path_tag(tag)))


@router.post(
    "",
    response_model=AdminAssetDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a unit, at INTAKE",
    responses={
        status.HTTP_403_FORBIDDEN: ADMIN_ONLY_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_BODY_RESPONSE,
    },
)
def post_asset(
    payload: AssetCreateRequest, user: FreshAdminUser, use_case: RegisterUnit
) -> AdminAssetDetailResponse:
    """Register the unit and record it, in one transaction.

    Raises:
        ValidationFailure: If a field breaks a rule, the model or the branch
            is unknown, or another unit carries the tag. HTTP 422, naming the
            field.

    """
    return asset_detail_response(use_case.execute(register_command(user, payload)))


@router.patch(
    "/{tag}",
    response_model=AdminAssetDetailResponse,
    summary="Change the paperwork of a unit, never its tag, model or branch",
    responses=WRITE_RESPONSES,
)
def patch_asset(
    tag: AssetPathTag, payload: AssetUpdateRequest, user: FreshAdminUser, use_case: EditUnit
) -> AdminAssetDetailResponse:
    """Change the fields that were sent and record them before and after.

    Raises:
        NotFound: If no unit carries the tag. HTTP 404.
        ValidationFailure: If a field breaks a rule, or the tag, the model or
            the branch is sent. HTTP 422, naming the field.

    """
    return asset_detail_response(use_case.execute(edit_command(user, tag, payload)))


@router.post(
    "/{tag}/transitions",
    response_model=AdminAssetDetailResponse,
    summary="Move a unit through its lifecycle by hand",
    responses={**WRITE_RESPONSES, status.HTTP_409_CONFLICT: MOVE_REFUSED_RESPONSE},
)
def post_transition(
    tag: AssetPathTag, payload: AssetTransitionRequest, user: FreshAdminUser, use_case: MoveUnit
) -> AdminAssetDetailResponse:
    """Move the unit and record the move, in one transaction.

    Raises:
        NotFound: If no unit carries the tag. HTTP 404.
        ValidationFailure: For ON_HIRE or LOST, naming `to`, or a move out of
            service with no reason, naming `reason`. HTTP 422.
        StateTransitionError: If the move is not permitted from the unit's
            status, or a booking or an open damage report holds the unit.
            HTTP 409.

    """
    return asset_detail_response(use_case.execute(move_command(user, tag, payload)))
