"""The customer's own rentals, which is US-26 and US-29.

`GET /api/me/rentals` lists the rentals of the signed in customer, newest
first, with every money line on each so the customer can see what was charged
and what came back of the deposit. It is for customers only. The scope goes
into the query, so nobody else's rental is ever read (BR-42), and `assetTag`
is null on every item, because a customer never learns which unit they were
given (US-07).
"""

from __future__ import annotations

from typing import Annotated, Final

from fastapi import APIRouter, Query

from app.api.booking_deps import actor_of
from app.api.deps import CustomerUser
from app.api.hire_deps import ListRentalsDependency
from app.api.hire_presenter import HIRE_TAG, rental_page_response
from app.api.return_schemas import RentalPageResponse
from app.application.booking.read_models import (
    DEFAULT_PAGE_SIZE,
    MAXIMUM_PAGE_SIZE,
    MINIMUM_PAGE_SIZE,
)
from app.application.catalogue.read_models import FIRST_PAGE, MAXIMUM_PAGE
from app.application.hire.list_rentals import MyRentalsQuery

MY_RENTALS_PATH: Final[str] = "/me/rentals"

router = APIRouter(tags=[HIRE_TAG])


@router.get(
    MY_RENTALS_PATH,
    response_model=RentalPageResponse,
    summary="List the signed in customer's own rentals, newest first",
)
def list_my_rentals(
    user: CustomerUser,
    reads: ListRentalsDependency,
    page: Annotated[
        int, Query(ge=FIRST_PAGE, le=MAXIMUM_PAGE, description="The page, counted from 1.")
    ] = FIRST_PAGE,
    page_size: Annotated[
        int,
        Query(
            alias="pageSize",
            ge=MINIMUM_PAGE_SIZE,
            le=MAXIMUM_PAGE_SIZE,
            description="How many rentals a page holds.",
        ),
    ] = DEFAULT_PAGE_SIZE,
) -> RentalPageResponse:
    """Return one page of the caller's own rentals, with no asset tag on any item."""
    found = reads.for_customer(
        MyRentalsQuery(actor=actor_of(user), page=page, page_size=page_size)
    )
    return rental_page_response(found)
