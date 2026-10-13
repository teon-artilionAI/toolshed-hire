"""The owner's closure days, the days a branch does not trade beyond its week.

`GET /api/admin/closure-days` answers every day in a span on which a branch is
closed for a reason other than its week, from today for a year unless `from`
and `to` say otherwise, and never more than a year at once. A public holiday is
listed once, for every branch, and a closure day names its branch, or none for
every branch, with the key it is cancelled by.

`GET /api/admin/closure-days/impact` answers the held and confirmed bookings
that start or end on a day at a branch, or at any branch when `branchCode` is
left out, and the hires still out whose equipment is due back that day, so the
owner can ring each customer before closing it. Nothing is cancelled.

`POST /api/admin/closure-days` closes a branch, or every branch, on a day with a
reason, and answers 201 with the closure. A day already closed at that branch or
at every branch is a 409. `POST /api/admin/closure-days/{id}/cancel` opens the
day again and answers 200 with the closure. A closure is never deleted (BR-51),
and one cancelled already is a 409.

Every route is for an administrator alone, and the two writes read the account
again under a row lock for the length of the change (`FreshAdminUser`). Counter
staff and customers are refused with 403.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.admin_presenter import ADMIN_PREFIX
from app.api.admin_user_presenter import branch_code
from app.api.booking_deps import actor_of
from app.api.closure_day_deps import AddClosureDay, CancelClosureDay, ReadClosureDaysDependency
from app.api.closure_day_presenter import (
    BRANCHES_TAG,
    CLOSURE_DAYS_PATH,
    ClosurePathKey,
    add_command,
    cancel_command,
    closed_days_response,
    closure_response,
    stranded_response,
)
from app.api.closure_day_schemas import (
    CANCEL_REFUSED_RESPONSE,
    CLOSURE_REFUSED_RESPONSE,
    UNKNOWN_CLOSURE_RESPONSE,
    ClosedDayListResponse,
    ClosureDayRequest,
    ClosureDayResponse,
    StrandedBookingListResponse,
)
from app.api.deps import AdminUser
from app.api.identity_deps import FreshAdminUser
from app.api.report_schemas import ADMIN_ONLY_RESPONSE
from app.api.reservation_schemas import (
    BRANCH_CODE_MAX_LENGTH,
    REFUSED_BODY_RESPONSE,
    REFUSED_QUERY_RESPONSE,
)
from app.application.trading.closure_reads import ClosedDaysRequest, ClosureImpactRequest

router = APIRouter(prefix=f"{ADMIN_PREFIX}{CLOSURE_DAYS_PATH}", tags=[BRANCHES_TAG])


@router.get(
    "",
    response_model=ClosedDayListResponse,
    summary="Return the public holidays and closure days in a span, by day",
    responses={
        status.HTTP_403_FORBIDDEN: ADMIN_ONLY_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_QUERY_RESPONSE,
    },
)
def read_closure_days(
    user: AdminUser,
    reads: ReadClosureDaysDependency,
    from_day: Annotated[
        date | None, Query(alias="from", description="The first day. Today when left out.")
    ] = None,
    to_day: Annotated[
        date | None,
        Query(
            alias="to",
            description="The last day, which is included. A year from the first when left out.",
        ),
    ] = None,
) -> ClosedDayListResponse:
    """Return every public holiday and live closure day in the span, by day.

    Raises:
        ValidationFailure: If `to` is before `from` or the span is longer than
            a year. HTTP 422, naming `to`.

    """
    request = ClosedDaysRequest(actor=actor_of(user), from_day=from_day, to_day=to_day)
    return closed_days_response(reads.closed_days(request))


@router.get(
    "/impact",
    response_model=StrandedBookingListResponse,
    summary="Return the bookings and hires out that fall on a day a closure would close",
    responses={
        status.HTTP_403_FORBIDDEN: ADMIN_ONLY_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_QUERY_RESPONSE,
    },
)
def read_closure_impact(
    user: AdminUser,
    reads: ReadClosureDaysDependency,
    day: Annotated[date, Query(description="The day the owner is thinking of closing.")],
    branch: Annotated[
        str | None,
        Query(
            alias="branchCode",
            max_length=BRANCH_CODE_MAX_LENGTH,
            description="The branch. Every branch when left out.",
        ),
    ] = None,
) -> StrandedBookingListResponse:
    """Return the bookings that start or end on the day, and the hires due back.

    Raises:
        ValidationFailure: If no trading branch has the code. HTTP 422, naming
            `branchCode`.

    """
    request = ClosureImpactRequest(actor=actor_of(user), branch_code=branch_code(branch), day=day)
    return stranded_response(reads.impact(request))


@router.post(
    "",
    response_model=ClosureDayResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Close a branch, or every branch, on a day, with the reason",
    responses={
        status.HTTP_403_FORBIDDEN: ADMIN_ONLY_RESPONSE,
        status.HTTP_409_CONFLICT: CLOSURE_REFUSED_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_BODY_RESPONSE,
    },
)
def post_closure_day(
    payload: ClosureDayRequest, user: FreshAdminUser, use_case: AddClosureDay
) -> ClosureDayResponse:
    """Add the closure and record it, in one transaction.

    Raises:
        ValidationFailure: For a reason out of bounds, a day that has passed or
            is more than a year ahead, or a branch that is not trading. HTTP
            422, naming the field.
        StateTransitionError: If the day is closed already. HTTP 409.

    """
    return closure_response(use_case.execute(add_command(user, payload)))


@router.post(
    "/{id}/cancel",
    response_model=ClosureDayResponse,
    summary="Cancel a closure day, which opens the day again",
    responses={
        status.HTTP_403_FORBIDDEN: ADMIN_ONLY_RESPONSE,
        status.HTTP_404_NOT_FOUND: UNKNOWN_CLOSURE_RESPONSE,
        status.HTTP_409_CONFLICT: CANCEL_REFUSED_RESPONSE,
    },
)
def post_closure_cancel(
    closure_id: ClosurePathKey, user: FreshAdminUser, use_case: CancelClosureDay
) -> ClosureDayResponse:
    """Cancel the closure and record it, in one transaction.

    Raises:
        NotFound: If there is no such closure. HTTP 404.
        StateTransitionError: If it was cancelled already. HTTP 409.

    """
    return closure_response(use_case.execute(cancel_command(user, closure_id)))
