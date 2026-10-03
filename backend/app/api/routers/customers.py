"""The counter's customer routes, which are US-20 and US-21.

Counter staff and administrators look a customer up by part of a name, a
phone number or an email address, open one by its key, and register a walk-in
who has no login. Nobody else may call any of the three.

A walk-in is registered at the assistant's own branch. An administrator
belongs to no branch and names one. Counter staff who name another branch are
refused with 403, because registering a customer is a write (BR-43).

The text of a search is two to eighty characters, and a page holds one to
fifty customers, best match first.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request, Response, status
from pydantic import StringConstraints

from app.api.booking_deps import actor_of
from app.api.customer_deps import CustomerLookup, RegisterWalkIn
from app.api.customer_schemas import (
    UNKNOWN_CUSTOMER_RESPONSE,
    WRONG_BRANCH_RESPONSE,
    CustomerPageResponse,
    CustomerSummaryResponse,
    WalkInRequest,
)
from app.api.deps import CounterUser
from app.api.reservation_schemas import REFUSED_BODY_RESPONSE, REFUSED_QUERY_RESPONSE
from app.application.booking.read_models import (
    DEFAULT_PAGE_SIZE,
    MAXIMUM_PAGE_SIZE,
    MINIMUM_PAGE_SIZE,
)
from app.application.catalogue.read_models import FIRST_PAGE, MAXIMUM_PAGE
from app.application.identity.customer_directory import (
    MAXIMUM_CUSTOMER_SEARCH_LENGTH,
    MINIMUM_CUSTOMER_SEARCH_LENGTH,
    CustomerSearch,
)
from app.application.identity.walk_in import RegisterWalkInCommand

LOCATION_HEADER = "Location"
READ_CUSTOMER_ROUTE_NAME = "read_customer"
IDENTITY_TAG = "identity"

router = APIRouter(prefix="/customers", tags=[IDENTITY_TAG])

# Surrounding spaces are removed before the length is checked, so a search for
# two spaces is refused like any other search that is too short.
CustomerSearchText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=MINIMUM_CUSTOMER_SEARCH_LENGTH,
        max_length=MAXIMUM_CUSTOMER_SEARCH_LENGTH,
    ),
]


@router.get(
    "",
    response_model=CustomerPageResponse,
    summary="Find customers by name, phone or email, best match first",
    responses={
        status.HTTP_403_FORBIDDEN: WRONG_BRANCH_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_QUERY_RESPONSE,
    },
)
def search_customers(
    user: CounterUser,
    lookup: CustomerLookup,
    q: Annotated[
        CustomerSearchText,
        Query(description="Part of a name, a phone number or an email address."),
    ],
    page: Annotated[
        int, Query(ge=FIRST_PAGE, le=MAXIMUM_PAGE, description="The page, counted from 1.")
    ] = FIRST_PAGE,
    page_size: Annotated[
        int,
        Query(
            alias="pageSize",
            ge=MINIMUM_PAGE_SIZE,
            le=MAXIMUM_PAGE_SIZE,
            description="How many customers a page holds.",
        ),
    ] = DEFAULT_PAGE_SIZE,
) -> CustomerPageResponse:
    """Return one page of the customers the text matches."""
    found = lookup.search(
        actor_of(user), CustomerSearch(text=q, page=page, page_size=page_size)
    )
    return CustomerPageResponse(
        items=[CustomerSummaryResponse.model_validate(summary) for summary in found.items],
        page=found.page,
        page_size=found.page_size,
        total=found.total,
    )


@router.post(
    "",
    response_model=CustomerSummaryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a walk-in customer who has no login",
    responses={
        status.HTTP_403_FORBIDDEN: WRONG_BRANCH_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_BODY_RESPONSE,
    },
)
def post_walk_in(
    payload: WalkInRequest,
    user: CounterUser,
    use_case: RegisterWalkIn,
    request: Request,
    response: Response,
) -> CustomerSummaryResponse:
    """Register the walk-in and answer with the customer and a `Location` header.

    Raises:
        ValidationFailure: If a field is refused, or an administrator names no
            branch. HTTP 422, naming the field.
        BranchScopeError: If counter staff name another branch. HTTP 403.

    """
    summary = use_case.execute(
        RegisterWalkInCommand(
            actor=actor_of(user),
            display_name=payload.display_name,
            phone=payload.phone,
            id_document_type=payload.id_document_type,
            id_document_last4=payload.id_document_last4,
            billing_address_line1=payload.billing_address_line1,
            billing_suburb=payload.billing_suburb,
            billing_city=payload.billing_city,
            billing_postal_code=payload.billing_postal_code,
            customer_type=payload.customer_type,
            company_name=payload.company_name,
            vat_number=payload.vat_number,
            branch_code=payload.branch_code,
        )
    )
    response.headers[LOCATION_HEADER] = str(
        request.app.url_path_for(READ_CUSTOMER_ROUTE_NAME, id=str(summary.id))
    )
    return CustomerSummaryResponse.model_validate(summary)


@router.get(
    "/{id}",
    name=READ_CUSTOMER_ROUTE_NAME,
    response_model=CustomerSummaryResponse,
    summary="Return one customer",
    responses={status.HTTP_404_NOT_FOUND: UNKNOWN_CUSTOMER_RESPONSE},
)
def read_customer(
    customer_id: Annotated[UUID, Path(alias="id", description="The key of the customer.")],
    user: CounterUser,
    lookup: CustomerLookup,
) -> CustomerSummaryResponse:
    """Return the customer, or 404 when there is none with this key.

    Raises:
        NotFound: If there is no customer profile with this key. HTTP 404.

    """
    return CustomerSummaryResponse.model_validate(lookup.one(actor_of(user), customer_id))
