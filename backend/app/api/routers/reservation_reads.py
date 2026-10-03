"""The two reads of the booking module, which are FR-09.

A signed in caller reads one reservation, or a page of them. A customer is
shown their own and nobody else's, and one that is not theirs is answered 404
in the words used for one that never existed (BR-42). Counter staff and
administrators read any customer's reservation at any branch, and may narrow
a list to one customer with `customerProfileId` or one branch with
`branchCode`. The branch filter was first called `branch`, and that name is
still accepted so a client built against it keeps working. `branchCode` wins
when both are sent.

A list is newest first. Every reservation in it carries what the caller may do
to it next, so a screen draws its buttons from the answer.

Both reads run the sweep that lapses expired holds before they answer
(BR-13), so nothing is shown as held when its hold has already run out.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.booking_deps import ReadReservationsDependency, actor_of
from app.api.deps import AnyRoleUser
from app.api.reservation_presenter import (
    BOOKING_TAG,
    READ_RESERVATION_ROUTE_NAME,
    RESERVATIONS_PREFIX,
    ReservationPathKey,
    reservation_page_response,
    reservation_response,
)
from app.api.reservation_schemas import (
    NOT_PERMITTED_RESPONSE,
    REFUSED_QUERY_RESPONSE,
    UNKNOWN_RESERVATION_RESPONSE,
    ReservationPageResponse,
    ReservationResponse,
)
from app.application.availability.search import BRANCH_PARAMETER
from app.application.booking.access import ReservationCommand
from app.application.booking.read_models import (
    DEFAULT_PAGE_SIZE,
    MAXIMUM_PAGE_SIZE,
    MINIMUM_PAGE_SIZE,
    ReservationKey,
)
from app.application.booking.read_reservation import ListReservationsQuery
from app.application.catalogue.read_models import FIRST_PAGE, MAXIMUM_PAGE
from app.domain.enums import ReservationStatus

# The name the contract gives the branch filter. `branch` is its earlier name.
BRANCH_CODE_PARAMETER = "branchCode"

router = APIRouter(prefix=RESERVATIONS_PREFIX, tags=[BOOKING_TAG])


@router.get(
    "",
    response_model=ReservationPageResponse,
    summary="List reservations, newest first",
    responses={
        status.HTTP_403_FORBIDDEN: NOT_PERMITTED_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_QUERY_RESPONSE,
    },
)
def list_reservations(
    user: AnyRoleUser,
    reads: ReadReservationsDependency,
    reservation_status: Annotated[
        ReservationStatus | None,
        Query(alias="status", description="Only reservations in this status."),
    ] = None,
    customer_profile_id: Annotated[
        UUID | None,
        Query(alias="customerProfileId", description="Only this customer's. Staff only."),
    ] = None,
    branch_code: Annotated[
        str | None,
        Query(
            alias="branchCode",
            description="A branch code. Only reservations collected there. Staff only.",
        ),
    ] = None,
    branch: Annotated[
        str | None,
        Query(
            description="The earlier name of `branchCode`, still accepted. Staff only.",
            deprecated=True,
        ),
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
            description="How many reservations a page holds.",
        ),
    ] = DEFAULT_PAGE_SIZE,
) -> ReservationPageResponse:
    """Return one page of the reservations the caller may see.

    Raises:
        AuthorisationFailure: If a customer narrows the list to another
            customer or to a branch. Mapped to HTTP 403.
        ValidationFailure: If the branch code is not the code of a trading
            branch. Mapped to HTTP 422, naming the parameter it was sent in.

    """
    branch_parameter = BRANCH_CODE_PARAMETER if branch_code is not None else BRANCH_PARAMETER
    found = reads.page(
        ListReservationsQuery(
            actor=actor_of(user),
            status=reservation_status,
            customer_profile_id=customer_profile_id,
            branch_code=branch_code if branch_code is not None else branch,
            page=page,
            page_size=page_size,
            branch_parameter=branch_parameter,
        )
    )
    return reservation_page_response(found)


@router.get(
    "/{id}",
    name=READ_RESERVATION_ROUTE_NAME,
    response_model=ReservationResponse,
    summary="Return one reservation, by its key or its reference",
    responses={status.HTTP_404_NOT_FOUND: UNKNOWN_RESERVATION_RESPONSE},
)
def read_reservation(
    reservation_key: ReservationPathKey, user: AnyRoleUser, reads: ReadReservationsDependency
) -> ReservationResponse:
    """Return the reservation, or 404 when it does not exist or is not the caller's.

    Raises:
        NotFound: If there is no such reservation for this caller. Mapped to
            HTTP 404.

    """
    command = ReservationCommand(actor=actor_of(user), key=ReservationKey.parse(reservation_key))
    return reservation_response(reads.one(command))
