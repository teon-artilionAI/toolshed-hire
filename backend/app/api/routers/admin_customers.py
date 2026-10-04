"""The customer holds, kept by an administrator (BR-18, US-35).

`GET /api/admin/customers` answers one page of the customers by name, as the
`CustomerSummary` the counter reads, narrowed by `status`, which is the
`accountStatus` they hold, and searched by `q` the way the counter searches,
by part of a name, a phone number or the address of an account.

`POST /api/admin/customers/{id}/status` moves a customer between ACTIVE,
ON_HOLD and BLACKLISTED with a reason, which the audit event keeps, and
answers 200 with the `CustomerSummary`. A customer on hold or blacklisted is
refused a booking by the rule every booking already asks. Releasing a hold
keeps the count of bookings the customer did not collect. Asking for the
standing a customer already has changes nothing.

Every route is for an administrator alone, and the write reads the account
again under a row lock for the length of the change (`FreshAdminUser`).
Counter staff and customers are refused with 403.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status
from pydantic import StringConstraints

from app.api.admin_presenter import ADMIN_PREFIX
from app.api.admin_user_deps import ChangeCustomerStanding, ReadCustomerListDependency
from app.api.admin_user_presenter import (
    CUSTOMERS_PATH,
    IDENTITY_TAG,
    CustomerPathKey,
    standing_command,
)
from app.api.admin_user_schemas import CustomerStatusRequest
from app.api.booking_deps import actor_of
from app.api.customer_schemas import (
    UNKNOWN_CUSTOMER_RESPONSE,
    CustomerPageResponse,
    CustomerSummaryResponse,
)
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
from app.application.identity.customer_directory import (
    MAXIMUM_CUSTOMER_SEARCH_LENGTH,
    MINIMUM_CUSTOMER_SEARCH_LENGTH,
)
from app.application.identity.customer_listing import CustomerListRequest
from app.domain.enums import AccountStatus

router = APIRouter(prefix=f"{ADMIN_PREFIX}{CUSTOMERS_PATH}", tags=[IDENTITY_TAG])

# Surrounding spaces are removed before the length is checked, as the
# counter's search does.
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
    summary="Return one page of the customers by name, narrowed by their standing",
    responses={
        status.HTTP_403_FORBIDDEN: ADMIN_ONLY_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_QUERY_RESPONSE,
    },
)
def read_customers(
    user: AdminUser,
    reads: ReadCustomerListDependency,
    account_status: Annotated[
        AccountStatus | None,
        Query(alias="status", description="Only the customers in this standing."),
    ] = None,
    q: Annotated[
        CustomerSearchText | None,
        Query(description="Part of a name, a phone number or an email address."),
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
            description="How many customers a page holds.",
        ),
    ] = DEFAULT_PAGE_SIZE,
) -> CustomerPageResponse:
    """Return one page of the customers that match, by name."""
    found = reads.page(
        CustomerListRequest(
            actor=actor_of(user),
            status=account_status,
            text=q,
            page=page,
            page_size=page_size,
        )
    )
    return CustomerPageResponse(
        items=[CustomerSummaryResponse.model_validate(summary) for summary in found.items],
        page=found.page,
        page_size=found.page_size,
        total=found.total,
    )


@router.post(
    "/{id}/status",
    response_model=CustomerSummaryResponse,
    summary="Set the standing of a customer, with the reason",
    responses={
        status.HTTP_403_FORBIDDEN: ADMIN_ONLY_RESPONSE,
        status.HTTP_404_NOT_FOUND: UNKNOWN_CUSTOMER_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_BODY_RESPONSE,
    },
)
def post_customer_status(
    customer_id: CustomerPathKey,
    payload: CustomerStatusRequest,
    user: FreshAdminUser,
    use_case: ChangeCustomerStanding,
) -> CustomerSummaryResponse:
    """Set the standing and record it with the reason, in one transaction.

    Raises:
        NotFound: If there is no customer with this key. HTTP 404.
        ValidationFailure: If the reason is out of bounds. HTTP 422, naming `reason`.

    """
    summary = use_case.execute(standing_command(user, customer_id, payload))
    return CustomerSummaryResponse.model_validate(summary)
