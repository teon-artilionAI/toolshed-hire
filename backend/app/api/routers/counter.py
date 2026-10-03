"""The counter's dashboard and branch diary, which are FR-16, US-18 and US-19.

`GET /api/counter/dashboard` shows a branch what is due today, which is the
collections, the returns and the overdue hires, each list capped at fifty rows
with the true totals beside them. `GET /api/counter/diary` shows the
collections and the returns of a branch for one to seven days from any date.

Both are for counter staff and administrators. Counter staff read their own
branch and may leave `branchCode` out, and naming another branch is refused
with 403. An administrator names the branch, and leaving it out is a 422 that
names `branchCode`. Both run the lazy sweep before they answer, so a hold that
ran out is lapsed and a booking nobody collected is marked before it is shown.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Final

from fastapi import APIRouter, Query, status

from app.api.booking_deps import actor_of
from app.api.counter_deps import ReadCounterOverviewDependency
from app.api.counter_presenter import dashboard_response, diary_response
from app.api.counter_schemas import WRONG_BRANCH_RESPONSE, DashboardResponse, DiaryResponse
from app.api.deps import CounterUser
from app.api.hire_presenter import HIRE_TAG
from app.api.reservation_schemas import BRANCH_CODE_MAX_LENGTH, REFUSED_QUERY_RESPONSE
from app.application.hire.overview import (
    DEFAULT_DIARY_DAYS,
    MAXIMUM_DIARY_DAYS,
    MINIMUM_DIARY_DAYS,
    DashboardQuery,
    DiaryQuery,
)

COUNTER_PREFIX: Final[str] = "/counter"

router = APIRouter(prefix=COUNTER_PREFIX, tags=[HIRE_TAG])

BranchCode = Annotated[
    str | None,
    Query(
        alias="branchCode",
        max_length=BRANCH_CODE_MAX_LENGTH,
        description=(
            "The branch. Counter staff may leave it out and get their own. An administrator "
            "names one."
        ),
    ),
]
READ_RESPONSES: Final[dict[int | str, dict[str, object]]] = {
    status.HTTP_403_FORBIDDEN: WRONG_BRANCH_RESPONSE,
    status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_QUERY_RESPONSE,
}


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="Return what is due today at a branch",
    responses=READ_RESPONSES,
)
def read_dashboard(
    user: CounterUser, overview: ReadCounterOverviewDependency, branch_code: BranchCode = None
) -> DashboardResponse:
    """Return the collections, returns and overdue hires of today, after running the sweep.

    Raises:
        BranchScopeError: If counter staff name another branch. HTTP 403.
        ValidationFailure: If an administrator names no branch, or one that is
            not trading. HTTP 422, naming `branchCode`.

    """
    query = DashboardQuery(actor=actor_of(user), branch_code=branch_code)
    return dashboard_response(overview.dashboard(query))


@router.get(
    "/diary",
    response_model=DiaryResponse,
    summary="Return the collections and returns of a branch for one to seven days",
    responses=READ_RESPONSES,
)
def read_diary(
    user: CounterUser,
    overview: ReadCounterOverviewDependency,
    branch_code: BranchCode = None,
    first_day: Annotated[
        date | None, Query(alias="from", description="The first day. Today when left out.")
    ] = None,
    days: Annotated[
        int,
        Query(
            ge=MINIMUM_DIARY_DAYS,
            le=MAXIMUM_DIARY_DAYS,
            description="How many days to show, from one to seven.",
        ),
    ] = DEFAULT_DIARY_DAYS,
) -> DiaryResponse:
    """Return the diary of the branch, one entry for each day, after running the sweep.

    Raises:
        BranchScopeError: If counter staff name another branch. HTTP 403.
        ValidationFailure: If an administrator names no branch, or one that is
            not trading, or the run ends past the last date there is. HTTP 422,
            naming the parameter.

    """
    query = DiaryQuery(
        actor=actor_of(user), branch_code=branch_code, first_day=first_day, days=days
    )
    return diary_response(overview.diary(query))
