"""The utilisation and gross contribution report and the admin dashboard (FR-24, US-33, US-34).

`GET /api/admin/reports/utilisation` answers one page of the report for any
period of up to 366 days, grouped by asset, model, category or branch,
narrowed by `branchCode` and `categorySlug`, highest gross contribution first,
with the totals over every line and the two definitions.

`GET /api/admin/reports/utilisation.csv` answers every line of the same report
as a CSV file, streamed a line at a time, its first line saying the figures
are gross contribution and not profit (C-32).

`GET /api/admin/dashboard` answers the business across every branch today.

All three are for an administrator alone. Counter staff and customers are
refused with 403. Each runs the lazy sweep before it counts anything.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Final

from fastapi import APIRouter, Query, status
from fastapi.responses import StreamingResponse

from app.api.booking_deps import actor_of
from app.api.deps import AdminUser
from app.api.report_csv import report_csv_lines, report_filename
from app.api.report_deps import ReadAdminDashboardDependency, ReadUtilisationReportDependency
from app.api.report_presenter import dashboard_response, report_page_response
from app.api.report_schemas import (
    ADMIN_ONLY_RESPONSE,
    CSV_RESPONSE,
    AdminDashboardResponse,
    UtilisationReportResponse,
)
from app.api.reservation_schemas import BRANCH_CODE_MAX_LENGTH, REFUSED_QUERY_RESPONSE
from app.application.catalogue.read_models import FIRST_PAGE, MAXIMUM_PAGE
from app.application.reporting.read_report import (
    DEFAULT_PAGE_SIZE,
    MAXIMUM_PAGE_SIZE,
    MINIMUM_PAGE_SIZE,
    ReportQuery,
)
from app.application.reporting.report_models import GroupBy

ADMIN_PREFIX: Final[str] = "/admin"
REPORTING_TAG: Final[str] = "reporting"
CSV_MEDIA_TYPE: Final[str] = "text/csv; charset=utf-8"
CONTENT_DISPOSITION_HEADER: Final[str] = "Content-Disposition"
CATEGORY_SLUG_MAX_LENGTH: Final[int] = 80

router = APIRouter(prefix=ADMIN_PREFIX, tags=[REPORTING_TAG])

From = Annotated[date, Query(alias="from", description="The first day of the period.")]
To = Annotated[
    date,
    Query(alias="to", description="The day after the last day, so the period is [from, to)."),
]
GroupedBy = Annotated[
    GroupBy, Query(alias="groupBy", description="What each line stands for.")
]
BranchCode = Annotated[
    str | None,
    Query(
        alias="branchCode",
        max_length=BRANCH_CODE_MAX_LENGTH,
        description="Only the units held at this branch.",
    ),
]
CategorySlug = Annotated[
    str | None,
    Query(
        alias="categorySlug",
        max_length=CATEGORY_SLUG_MAX_LENGTH,
        description="Only the units of models in this category and its children.",
    ),
]
READ_RESPONSES: Final[dict[int | str, dict[str, object]]] = {
    status.HTTP_403_FORBIDDEN: ADMIN_ONLY_RESPONSE,
    status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_QUERY_RESPONSE,
}


@router.get(
    "/reports/utilisation",
    response_model=UtilisationReportResponse,
    summary="Return one page of the utilisation and gross contribution report",
    responses=READ_RESPONSES,
)
def read_utilisation_report(
    user: AdminUser,
    reads: ReadUtilisationReportDependency,
    from_date: From,
    to_date: To,
    group_by: GroupedBy = GroupBy.ASSET,
    branch_code: BranchCode = None,
    category_slug: CategorySlug = None,
    page: Annotated[
        int, Query(ge=FIRST_PAGE, le=MAXIMUM_PAGE, description="The page, counted from 1.")
    ] = FIRST_PAGE,
    page_size: Annotated[
        int,
        Query(
            alias="pageSize",
            ge=MINIMUM_PAGE_SIZE,
            le=MAXIMUM_PAGE_SIZE,
            description="How many lines a page holds.",
        ),
    ] = DEFAULT_PAGE_SIZE,
) -> UtilisationReportResponse:
    """Return one page of the report, after running the sweep.

    Raises:
        ValidationFailure: If the period ends before it starts or is longer
            than 366 days, or the branch or the category is unknown. HTTP
            422, naming the parameter.

    """
    query = ReportQuery(
        actor=actor_of(user),
        starts_on=from_date,
        ends_on=to_date,
        group_by=group_by,
        branch_code=branch_code,
        category_slug=category_slug,
        page=page,
        page_size=page_size,
    )
    return report_page_response(reads.page(query))


@router.get(
    "/reports/utilisation.csv",
    response_class=StreamingResponse,
    summary="Return every line of the report as a CSV file",
    responses={status.HTTP_200_OK: CSV_RESPONSE, **READ_RESPONSES},
)
def export_utilisation_report(
    user: AdminUser,
    reads: ReadUtilisationReportDependency,
    from_date: From,
    to_date: To,
    group_by: GroupedBy = GroupBy.ASSET,
    branch_code: BranchCode = None,
    category_slug: CategorySlug = None,
) -> StreamingResponse:
    """Return every line of the report as CSV, worked out first and then streamed a line at a time.

    Raises:
        ValidationFailure: As for the report. HTTP 422, naming the parameter.

    """
    report = reads.everything(
        ReportQuery(
            actor=actor_of(user),
            starts_on=from_date,
            ends_on=to_date,
            group_by=group_by,
            branch_code=branch_code,
            category_slug=category_slug,
        )
    )
    return StreamingResponse(
        report_csv_lines(report),
        media_type=CSV_MEDIA_TYPE,
        headers={
            CONTENT_DISPOSITION_HEADER: f'attachment; filename="{report_filename(report)}"'
        },
    )


@router.get(
    "/dashboard",
    response_model=AdminDashboardResponse,
    summary="Return the business across every branch today",
    responses={status.HTTP_403_FORBIDDEN: ADMIN_ONLY_RESPONSE},
)
def read_admin_dashboard(
    user: AdminUser, dashboard: ReadAdminDashboardDependency
) -> AdminDashboardResponse:
    """Return each branch, the totals, the month so far and what waits, after running the sweep."""
    return dashboard_response(dashboard.read(actor_of(user)))
