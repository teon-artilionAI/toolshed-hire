"""The two checkout routes, which are FR-17 and US-22.

`GET /api/reservations/{id}/checkout` answers what the counter needs to hand
the equipment of a reservation over, and whether the caller may do it now.
`POST /api/reservations/{id}/checkout` does it. Both are for counter staff and
administrators, and the post is for counter staff of the collection branch
only (BR-26, BR-43).

The post answers 201 with the new rental and a `Location` header. Asked again
for a reservation that was already checked out, it answers 200 with the rental
the first checkout opened and writes nothing, so a second click or a retry
over a dropped connection is harmless.

`{id}` is the key of the reservation or its reference.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.api.booking_deps import actor_of
from app.api.deps import CounterUser
from app.api.hire_deps import CheckoutRental, ReadRentalsDependency
from app.api.hire_presenter import (
    HIRE_TAG,
    READ_RENTAL_ROUTE_NAME,
    checkout_response,
    rental_response,
)
from app.api.hire_schemas import (
    ALREADY_CHECKED_OUT_RESPONSE,
    CHECKOUT_REFUSED_RESPONSE,
    CheckoutPreviewResponse,
    CheckoutRequest,
    RentalResponse,
)
from app.api.reservation_presenter import RESERVATIONS_PREFIX, ReservationPathKey
from app.api.reservation_schemas import (
    NOT_PERMITTED_RESPONSE,
    REFUSED_BODY_RESPONSE,
    UNKNOWN_RESERVATION_RESPONSE,
)
from app.application.booking.access import ReservationCommand
from app.application.booking.read_models import ReservationKey
from app.application.hire.checkout import CheckoutCommand
from app.domain.checkout import HandOver

LOCATION_HEADER = "Location"

router = APIRouter(prefix=RESERVATIONS_PREFIX, tags=[HIRE_TAG])


@router.get(
    "/{id}/checkout",
    response_model=CheckoutPreviewResponse,
    summary="Return what the counter needs to check a reservation out",
    responses={status.HTTP_404_NOT_FOUND: UNKNOWN_RESERVATION_RESPONSE},
)
def read_checkout(
    reservation_key: ReservationPathKey, user: CounterUser, reads: ReadRentalsDependency
) -> CheckoutPreviewResponse:
    """Return the reservation, its units and whether the caller may check it out now.

    Raises:
        NotFound: If there is no such reservation. HTTP 404.

    """
    command = ReservationCommand(actor=actor_of(user), key=ReservationKey.parse(reservation_key))
    return checkout_response(reads.checkout(command))


@router.post(
    "/{id}/checkout",
    response_model=RentalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Check a confirmed reservation out, opening its rental",
    responses={
        status.HTTP_200_OK: ALREADY_CHECKED_OUT_RESPONSE,
        status.HTTP_403_FORBIDDEN: NOT_PERMITTED_RESPONSE,
        status.HTTP_404_NOT_FOUND: UNKNOWN_RESERVATION_RESPONSE,
        status.HTTP_409_CONFLICT: CHECKOUT_REFUSED_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_BODY_RESPONSE,
    },
)
def post_checkout(
    reservation_key: ReservationPathKey,
    payload: CheckoutRequest,
    user: CounterUser,
    use_case: CheckoutRental,
    request: Request,
    response: Response,
) -> RentalResponse:
    """Hand the equipment over in one transaction, or answer with the rental already opened.

    Raises:
        NotFound: If there is no such reservation. HTTP 404.
        BranchScopeError: If counter staff check out at another branch. HTTP 403.
        StateTransitionError: If the reservation is not confirmed or its hire
            has not started. HTTP 409.
        ValidationFailure: If the list of units is wrong or the agreement is
            not signed. HTTP 422, naming the field.

    """
    outcome = use_case.execute(
        CheckoutCommand(
            actor=actor_of(user),
            key=ReservationKey.parse(reservation_key),
            hand_overs=tuple(
                HandOver(
                    allocation_id=item.allocation_id,
                    condition_out=item.condition_out,
                    accessories_out=item.accessories_out,
                    hour_meter_out=item.hour_meter_out,
                )
                for item in payload.items
            ),
            agreement_signed=payload.agreement_signed,
        )
    )
    if outcome.created:
        response.headers[LOCATION_HEADER] = str(
            request.app.url_path_for(READ_RENTAL_ROUTE_NAME, id=str(outcome.rental.detail.id))
        )
    else:
        response.status_code = status.HTTP_200_OK
    return rental_response(outcome.rental)
