"""The damage report routes, which are FR-20, US-24 and US-38 (BR-35 to BR-40).

`POST /api/damage-reports` files a report for counter staff of the branch that
holds the unit, and for administrators at any branch (BR-43). It answers 201
with the report and its `Location`. The unit leaves availability, and a report
the customer is charged for raises a recovery on the hire, which settles the
deposit when it was the last thing the hire waited on.

`GET /api/damage-reports` lists reports at every branch, newest first, narrowed
by `assetTag`, `status` and `branchCode`. `GET /api/damage-reports/{id}` reads
one, by its key or its reference. Both are for staff.

`POST /api/damage-reports/{id}/repair` and `POST /api/damage-reports/{id}/resolution`
are for an administrator alone. Counter staff are refused with 403.
"""

from __future__ import annotations

from typing import Annotated, Final

from fastapi import APIRouter, Query, Request, Response, status

from app.api.booking_deps import actor_of
from app.api.damage_deps import (
    CloseDamageReport,
    FileDamageReport,
    ReadDamageReportsDependency,
    SendForRepair,
)
from app.api.damage_presenter import (
    DAMAGE_REPORTS_PREFIX,
    READ_DAMAGE_REPORT_ROUTE_NAME,
    ReportPathKey,
    amount_of,
    filing_of,
    report_page_response,
    report_response,
)
from app.api.damage_schemas import (
    ASSET_TAG_MAX_LENGTH,
    REPORT_MOVE_REFUSED_RESPONSE,
    REPORT_REFUSED_RESPONSE,
    UNKNOWN_REPORT_RESPONSE,
    DamageReportPageResponse,
    DamageReportRequest,
    DamageReportResponse,
    ResolutionRequest,
)
from app.api.deps import AdminUser, CounterUser
from app.api.hire_presenter import HIRE_TAG
from app.api.reservation_schemas import (
    NOT_PERMITTED_RESPONSE,
    REFUSED_BODY_RESPONSE,
    REFUSED_QUERY_RESPONSE,
)
from app.application.booking.read_models import (
    DEFAULT_PAGE_SIZE,
    MAXIMUM_PAGE_SIZE,
    MINIMUM_PAGE_SIZE,
)
from app.application.catalogue.read_models import FIRST_PAGE, MAXIMUM_PAGE
from app.application.hire.damage_closing import CloseReportCommand, RepairCommand
from app.application.hire.damage_models import DamageReportKey
from app.application.hire.damage_reads import ListDamageReportsQuery
from app.application.hire.file_damage_report import FileDamageReportCommand
from app.domain.enums import DamageStatus

router = APIRouter(prefix=DAMAGE_REPORTS_PREFIX, tags=[HIRE_TAG])

LOCATION_HEADER: Final[str] = "Location"


@router.post(
    "",
    response_model=DamageReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="File a damage report, quarantine the unit and charge the decided recovery",
    responses={
        status.HTTP_403_FORBIDDEN: NOT_PERMITTED_RESPONSE,
        status.HTTP_409_CONFLICT: REPORT_REFUSED_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_BODY_RESPONSE,
    },
)
def post_damage_report(
    payload: DamageReportRequest,
    user: CounterUser,
    use_case: FileDamageReport,
    request: Request,
    response: Response,
) -> DamageReportResponse:
    """File the report in one transaction.

    Raises:
        ValidationFailure: If the tag is unknown, the decision is missing, the
            amount to recover does not follow from it or is above the cap, or
            the rental item is not a hire of the unit. HTTP 422, naming the field.
        BranchScopeError: If counter staff file a report at another branch. HTTP 403.
        StateTransitionError: If the unit is out on hire or retired, waits for
            the report of another hire, or the deposit was already settled. HTTP 409.

    """
    detail = use_case.execute(
        FileDamageReportCommand(
            actor=actor_of(user), asset_tag=payload.asset_tag, filing=filing_of(payload)
        )
    )
    response.headers[LOCATION_HEADER] = str(
        request.app.url_path_for(READ_DAMAGE_REPORT_ROUTE_NAME, id=str(detail.id))
    )
    return report_response(detail)


@router.get(
    "",
    response_model=DamageReportPageResponse,
    summary="List damage reports at every branch, newest first",
    responses={status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_QUERY_RESPONSE},
)
def list_damage_reports(
    user: CounterUser,
    reads: ReadDamageReportsDependency,
    asset_tag: Annotated[
        str | None,
        Query(
            alias="assetTag",
            max_length=ASSET_TAG_MAX_LENGTH,
            description="An asset tag. Only the reports of that unit.",
        ),
    ] = None,
    report_status: Annotated[
        DamageStatus | None, Query(alias="status", description="Only reports in this status.")
    ] = None,
    branch_code: Annotated[
        str | None,
        Query(alias="branchCode", description="A branch code. Only reports of units held there."),
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
            description="How many reports a page holds.",
        ),
    ] = DEFAULT_PAGE_SIZE,
) -> DamageReportPageResponse:
    """Return one page of damage reports, newest first.

    Raises:
        ValidationFailure: If the branch code is not the code of a trading
            branch. HTTP 422, naming `branchCode`.

    """
    found = reads.page(
        ListDamageReportsQuery(
            actor=actor_of(user),
            asset_tag=asset_tag.strip().upper() if asset_tag else None,
            status=report_status,
            branch_code=branch_code,
            page=page,
            page_size=page_size,
        )
    )
    return report_page_response(found)


@router.get(
    "/{id}",
    name=READ_DAMAGE_REPORT_ROUTE_NAME,
    response_model=DamageReportResponse,
    summary="Return one damage report, by its key or its reference",
    responses={status.HTTP_404_NOT_FOUND: UNKNOWN_REPORT_RESPONSE},
)
def read_damage_report(
    report_key: ReportPathKey, user: CounterUser, reads: ReadDamageReportsDependency
) -> DamageReportResponse:
    """Return the report, or 404 when it does not exist.

    Raises:
        NotFound: If there is no such report. HTTP 404.

    """
    return report_response(reads.one(actor_of(user), DamageReportKey.parse(report_key)))


@router.post(
    "/{id}/repair",
    response_model=DamageReportResponse,
    summary="Send an open damage report for repair, and its unit with it",
    responses={
        status.HTTP_403_FORBIDDEN: NOT_PERMITTED_RESPONSE,
        status.HTTP_404_NOT_FOUND: UNKNOWN_REPORT_RESPONSE,
        status.HTTP_409_CONFLICT: REPORT_MOVE_REFUSED_RESPONSE,
    },
)
def post_repair(
    report_key: ReportPathKey, user: AdminUser, use_case: SendForRepair
) -> DamageReportResponse:
    """Send the report for repair in one transaction.

    Raises:
        NotFound: If there is no such report. HTTP 404.
        StateTransitionError: If the report is not OPEN. HTTP 409.

    """
    detail = use_case.execute(
        RepairCommand(actor=actor_of(user), key=DamageReportKey.parse(report_key))
    )
    return report_response(detail)


@router.post(
    "/{id}/resolution",
    response_model=DamageReportResponse,
    summary="Close a damage report as resolved or written off",
    responses={
        status.HTTP_403_FORBIDDEN: NOT_PERMITTED_RESPONSE,
        status.HTTP_404_NOT_FOUND: UNKNOWN_REPORT_RESPONSE,
        status.HTTP_409_CONFLICT: REPORT_MOVE_REFUSED_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_BODY_RESPONSE,
    },
)
def post_resolution(
    report_key: ReportPathKey,
    payload: ResolutionRequest,
    user: AdminUser,
    use_case: CloseDamageReport,
) -> DamageReportResponse:
    """Close the report in one transaction.

    Raises:
        NotFound: If there is no such report. HTTP 404.
        ValidationFailure: If a report is resolved without its actual cost.
            HTTP 422, naming `actualRepairCost`.
        StateTransitionError: If the report is already closed, or a write off
            would retire a unit a booking still holds. HTTP 409.

    """
    detail = use_case.execute(
        CloseReportCommand(
            actor=actor_of(user),
            key=DamageReportKey.parse(report_key),
            outcome=DamageStatus(payload.outcome),
            actual_repair_cost=amount_of(payload.actual_repair_cost),
            resolution_notes=payload.resolution_notes,
        )
    )
    return report_response(detail)
