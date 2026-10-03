"""The rental routes, which are the counter's view of a hire once it has gone out.

`GET /api/rentals` lists rentals at any branch for counter staff and
administrators, the overdue first, and runs the lazy sweep before it answers
(BR-52). `GET /api/rentals/{id}` returns one rental with its items and its
charges. `{id}` is the key of the rental or its reference. One that does not
exist is answered 404.

The three writes are for staff at the branch the hire went out from, and an
administrator at any branch (BR-43). `POST /api/rentals/{id}/returns` takes
units back and settles the deposit when the last one is back (FR-18, BR-32).
`POST /api/rentals/{id}/items/{itemId}/loss` records a unit more than fourteen
days late as lost (BR-31). `POST /api/rentals/{id}/balance-payment` records the
simulated payment of a balance the deposit could not cover (BR-33). Each
answers 200 with the rental as it now stands.
"""

from __future__ import annotations

from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Path, Query, status

from app.api.booking_deps import actor_of
from app.api.deps import CounterUser
from app.api.hire_deps import (
    ListRentalsDependency,
    ReadRentalsDependency,
    RecordBalancePayment,
    RecordLoss,
    ReturnItems,
)
from app.api.hire_presenter import (
    HIRE_TAG,
    READ_RENTAL_ROUTE_NAME,
    RENTALS_PREFIX,
    RentalPathKey,
    rental_page_response,
    rental_response,
)
from app.api.hire_schemas import UNKNOWN_RENTAL_RESPONSE, RentalResponse
from app.api.reservation_schemas import (
    NOT_PERMITTED_RESPONSE,
    REFUSED_BODY_RESPONSE,
    REFUSED_QUERY_RESPONSE,
)
from app.api.return_schemas import (
    LOSS_REFUSED_RESPONSE,
    NOTHING_DUE_RESPONSE,
    RETURN_REFUSED_RESPONSE,
    UNKNOWN_RENTAL_OR_ITEM_RESPONSE,
    BalancePaymentRequest,
    RentalPageResponse,
    ReturnRequest,
)
from app.application.booking.read_models import (
    DEFAULT_PAGE_SIZE,
    MAXIMUM_PAGE_SIZE,
    MINIMUM_PAGE_SIZE,
)
from app.application.catalogue.read_models import FIRST_PAGE, MAXIMUM_PAGE
from app.application.hire.balance_payment import BalancePaymentCommand
from app.application.hire.list_rentals import ListRentalsQuery
from app.application.hire.loss import LossCommand
from app.application.hire.read_models import RentalKey
from app.application.hire.read_rental import RentalCommand
from app.application.hire.returns import ReturnCommand
from app.domain.enums import RentalStatus
from app.domain.returns import ItemReturn

router = APIRouter(prefix=RENTALS_PREFIX, tags=[HIRE_TAG])

ItemPathKey = Annotated[UUID, Path(alias="itemId", description="The key of the rental item.")]
WRITE_REFUSALS: Final[dict[int | str, dict[str, object]]] = {
    status.HTTP_403_FORBIDDEN: NOT_PERMITTED_RESPONSE,
    status.HTTP_404_NOT_FOUND: UNKNOWN_RENTAL_RESPONSE,
}


@router.get(
    "",
    response_model=RentalPageResponse,
    summary="List rentals at any branch, the overdue first",
    responses={status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_QUERY_RESPONSE},
)
def list_rentals(
    user: CounterUser,
    reads: ListRentalsDependency,
    branch_code: Annotated[
        str | None,
        Query(alias="branchCode", description="A branch code. Only rentals that went out there."),
    ] = None,
    rental_status: Annotated[
        RentalStatus | None, Query(alias="status", description="Only rentals in this status.")
    ] = None,
    overdue_only: Annotated[
        bool,
        Query(alias="overdueOnly", description="Only rentals with a unit out past its due date."),
    ] = False,
    customer_profile_id: Annotated[
        UUID | None, Query(alias="customerProfileId", description="Only this customer's.")
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
            description="How many rentals a page holds.",
        ),
    ] = DEFAULT_PAGE_SIZE,
) -> RentalPageResponse:
    """Return one page of rentals, the most overdue first and then the newest.

    Raises:
        ValidationFailure: If the branch code is not the code of a trading
            branch. HTTP 422, naming `branchCode`.

    """
    found = reads.for_staff(
        ListRentalsQuery(
            actor=actor_of(user),
            branch_code=branch_code,
            status=rental_status,
            overdue_only=overdue_only,
            customer_profile_id=customer_profile_id,
            page=page,
            page_size=page_size,
        )
    )
    return rental_page_response(found)


@router.get(
    "/{id}",
    name=READ_RENTAL_ROUTE_NAME,
    response_model=RentalResponse,
    summary="Return one rental, by its key or its reference",
    responses={status.HTTP_404_NOT_FOUND: UNKNOWN_RENTAL_RESPONSE},
)
def read_rental(
    rental_key: RentalPathKey, user: CounterUser, reads: ReadRentalsDependency
) -> RentalResponse:
    """Return the rental, or 404 when it does not exist.

    Raises:
        NotFound: If there is no such rental. HTTP 404.

    """
    command = RentalCommand(actor=actor_of(user), key=RentalKey.parse(rental_key))
    return rental_response(reads.one(command))


@router.post(
    "/{id}/returns",
    response_model=RentalResponse,
    summary="Take units of a rental back, and settle the deposit when the last is back",
    responses={
        **WRITE_REFUSALS,
        status.HTTP_409_CONFLICT: RETURN_REFUSED_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_BODY_RESPONSE,
    },
)
def post_return(
    rental_key: RentalPathKey, payload: ReturnRequest, user: CounterUser, use_case: ReturnItems
) -> RentalResponse:
    """Record the return of the named units in one transaction.

    Raises:
        NotFound: If there is no such rental. HTTP 404.
        BranchScopeError: If counter staff take units back at another branch. HTTP 403.
        StateTransitionError: If a unit is already back. HTTP 409.
        ValidationFailure: If a unit is listed twice, is not on the rental or
            has a meter reading below the one it went out with. HTTP 422,
            naming the field.

    """
    view = use_case.execute(
        ReturnCommand(
            actor=actor_of(user),
            key=RentalKey.parse(rental_key),
            returns=tuple(
                ItemReturn(
                    rental_item_id=item.rental_item_id,
                    condition_in=item.condition_in,
                    hour_meter_in=item.hour_meter_in,
                    accessories_in=item.accessories_in,
                    notes=item.notes,
                    flagged_for_damage=item.flagged_for_damage,
                )
                for item in payload.items
            ),
        )
    )
    return rental_response(view)


@router.post(
    "/{id}/items/{itemId}/loss",
    response_model=RentalResponse,
    summary="Record a unit more than fourteen days late as lost",
    responses={
        **WRITE_REFUSALS,
        status.HTTP_404_NOT_FOUND: UNKNOWN_RENTAL_OR_ITEM_RESPONSE,
        status.HTTP_409_CONFLICT: LOSS_REFUSED_RESPONSE,
    },
)
def post_loss(
    rental_key: RentalPathKey, item_id: ItemPathKey, user: CounterUser, use_case: RecordLoss
) -> RentalResponse:
    """Record the loss of one unit in one transaction.

    Raises:
        NotFound: If there is no such rental, or the unit is not on it. HTTP 404.
        BranchScopeError: If counter staff record a loss at another branch. HTTP 403.
        StateTransitionError: If the unit is already back or not yet late
            enough. HTTP 409.

    """
    view = use_case.execute(
        LossCommand(actor=actor_of(user), key=RentalKey.parse(rental_key), rental_item_id=item_id)
    )
    return rental_response(view)


@router.post(
    "/{id}/balance-payment",
    response_model=RentalResponse,
    summary="Record the simulated payment of a rental's balance",
    responses={
        **WRITE_REFUSALS,
        status.HTTP_409_CONFLICT: NOTHING_DUE_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_BODY_RESPONSE,
    },
)
def post_balance_payment(
    rental_key: RentalPathKey,
    payload: BalancePaymentRequest,
    user: CounterUser,
    use_case: RecordBalancePayment,
) -> RentalResponse:
    """Record the payment and settle the rental in one transaction.

    Raises:
        NotFound: If there is no such rental. HTTP 404.
        BranchScopeError: If counter staff record a payment at another branch. HTTP 403.
        StateTransitionError: If nothing is owed. HTTP 409.

    """
    view = use_case.execute(
        BalancePaymentCommand(
            actor=actor_of(user),
            key=RentalKey.parse(rental_key),
            payment_reference=payload.payment_reference,
        )
    )
    return rental_response(view)
