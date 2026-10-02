"""The reservation endpoints, which are FR-05 to FR-11.

A signed in caller builds a draft, puts it on hold, confirms it, reads it and
cancels it. Each of those is one route and one use case. The router does no
work of its own beyond the HTTP boundary. It reads the request, says who is
asking and hands a command to a use case, which arrives already wired.

Every move goes through the reservation states, so an illegal one is answered
with 409 and the problem type `state-transition`. Losing the race for a unit
is 409 as well, with the type `asset-unavailable`, and its sentence names the
model and the dates and never how many units are left.

A reservation is named in a path by its key or by its reference. A customer
who names one that is not theirs gets 404, in the words used for one that
never existed (BR-42). Counter staff who act on a reservation at another
branch get 403 (BR-43).

There is no route that deletes anything (BR-51). A reservation is cancelled
by posting a cancellation, and it stays readable afterwards.

The two reads are in `app/api/routers/reservation_reads.py`.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response, status

from app.api.booking_deps import (
    CancelReservation,
    ConfirmReservation,
    CreateReservation,
    HoldReservation,
    actor_of,
)
from app.api.deps import AnyRoleUser
from app.api.reservation_presenter import (
    BOOKING_TAG,
    READ_RESERVATION_ROUTE_NAME,
    RESERVATIONS_PREFIX,
    ReservationPathKey,
    reservation_response,
)
from app.api.reservation_schemas import (
    CONFLICT_RESPONSE,
    NOT_PERMITTED_RESPONSE,
    REFUSED_BODY_RESPONSE,
    REFUSED_DATES_RESPONSE,
    UNKNOWN_RESERVATION_RESPONSE,
    CancellationRequest,
    CreateReservationRequest,
    ReservationResponse,
)
from app.application.booking.access import ReservationCommand
from app.application.booking.cancel_reservation import CancelReservationCommand
from app.application.booking.read_models import ReservationKey
from app.application.booking.reservation_request import (
    CreateReservationCommand,
    RequestedLine,
)

logger = logging.getLogger(__name__)

LOCATION_HEADER = "Location"

router = APIRouter(prefix=RESERVATIONS_PREFIX, tags=[BOOKING_TAG])

MOVE_RESPONSES: dict[int | str, dict[str, object]] = {
    status.HTTP_403_FORBIDDEN: NOT_PERMITTED_RESPONSE,
    status.HTTP_404_NOT_FOUND: UNKNOWN_RESERVATION_RESPONSE,
    status.HTTP_409_CONFLICT: CONFLICT_RESPONSE,
}


@router.post(
    "",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft reservation",
    responses={
        status.HTTP_403_FORBIDDEN: NOT_PERMITTED_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_BODY_RESPONSE,
    },
)
def post_reservation(
    payload: CreateReservationRequest,
    user: AnyRoleUser,
    use_case: CreateReservation,
    request: Request,
    response: Response,
) -> ReservationResponse:
    """Create a priced draft. Nothing is held until it is put on hold.

    Raises:
        AuthorisationFailure: If a customer names a customer profile. HTTP 403.
        BranchScopeError: If counter staff book at another branch. HTTP 403.
        AccountOnHoldError: If the customer's account is on hold. HTTP 403.
        ValidationFailure: If a field is refused. HTTP 422, naming the field.

    """
    actor = actor_of(user)
    view = use_case.execute(
        CreateReservationCommand(
            actor=actor,
            branch_code=payload.branch_code,
            start=payload.from_date,
            end=payload.to_date,
            lines=tuple(
                RequestedLine(model_slug=line.model_slug, quantity=line.quantity)
                for line in payload.lines
            ),
            customer_profile_id=payload.customer_profile_id,
            notes=payload.notes,
        )
    )
    # A path and not a full address. The browser reaches this service through
    # a rewrite, so the host this process sees is not the one the caller used.
    response.headers[LOCATION_HEADER] = str(
        request.app.url_path_for(READ_RESERVATION_ROUTE_NAME, id=str(view.detail.id))
    )
    return reservation_response(view)


@router.post(
    "/{id}/hold",
    response_model=ReservationResponse,
    summary="Put a draft on hold, taking named units for thirty minutes",
    responses={
        **MOVE_RESPONSES,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_DATES_RESPONSE,
    },
)
def post_hold(
    reservation_key: ReservationPathKey, user: AnyRoleUser, use_case: HoldReservation
) -> ReservationResponse:
    """Hold every unit the reservation asks for, or none of them (BR-09).

    Raises:
        NotFound: If there is no such reservation for this caller. HTTP 404.
        AllocationConflictError: If a line cannot be fully allocated. HTTP 409.
        StateTransitionError: If the reservation is not a draft. HTTP 409.

    """
    actor = actor_of(user)
    command = ReservationCommand(actor=actor, key=ReservationKey.parse(reservation_key))
    return reservation_response(use_case.execute(command))


@router.post(
    "/{id}/confirm",
    response_model=ReservationResponse,
    summary="Confirm a held reservation",
    responses=MOVE_RESPONSES,
)
def post_confirmation(
    reservation_key: ReservationPathKey, user: AnyRoleUser, use_case: ConfirmReservation
) -> ReservationResponse:
    """Confirm inside the hold, and send the booking confirmation (BR-19).

    Raises:
        NotFound: If there is no such reservation for this caller. HTTP 404.
        StateTransitionError: If the hold has run out or the move is not
            permitted. HTTP 409.
        EmailNotVerifiedError: If the customer's address is not verified.
            HTTP 403.

    """
    actor = actor_of(user)
    command = ReservationCommand(actor=actor, key=ReservationKey.parse(reservation_key))
    return reservation_response(use_case.execute(command))


@router.post(
    "/{id}/cancellation",
    response_model=ReservationResponse,
    summary="Cancel a reservation and release its units",
    responses={
        **MOVE_RESPONSES,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_BODY_RESPONSE,
    },
)
def post_cancellation(
    reservation_key: ReservationPathKey,
    user: AnyRoleUser,
    use_case: CancelReservation,
    payload: CancellationRequest | None = None,
) -> ReservationResponse:
    """Cancel the reservation. Nothing is deleted and nothing is charged.

    Raises:
        NotFound: If there is no such reservation for this caller. HTTP 404.
        StateTransitionError: If it can no longer be cancelled. HTTP 409.

    """
    actor = actor_of(user)
    command = CancelReservationCommand(
        actor=actor,
        key=ReservationKey.parse(reservation_key),
        reason=payload.reason if payload is not None else None,
    )
    return reservation_response(use_case.execute(command))
