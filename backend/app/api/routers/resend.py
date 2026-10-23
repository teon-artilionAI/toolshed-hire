"""Sending a booking confirmation again, for a customer or at the counter (B13.2).

A customer may ask for their own booking's confirmation again. Counter staff
may ask for a booking at their branch. The route is the same use case, and the
scope is applied in it, so a customer naming somebody else's booking is a 404
and staff naming another branch are a 403.

The answer is 202 with whether email can reach the customer's address in this
environment. The notification log records what the provider did with it.
"""

from __future__ import annotations

from typing import Final

from fastapi import APIRouter, status

from app.api.booking_deps import ResendConfirmation, actor_of
from app.api.deps import CounterUser, CustomerUser
from app.api.reservation_presenter import BOOKING_TAG, ReservationPathKey
from app.api.reservation_schemas import (
    NOT_PERMITTED_RESPONSE,
    UNKNOWN_RESERVATION_RESPONSE,
    ConfirmationResendResponse,
)
from app.application.booking.read_models import ReservationKey
from app.application.notification.booking_resend import ResendBookingConfirmationCommand

MY_RESEND_PATH: Final[str] = "/me/reservations/{id}/confirmation/resend"
COUNTER_RESEND_PATH: Final[str] = "/counter/reservations/{id}/confirmation/resend"

router = APIRouter(tags=[BOOKING_TAG])

RESPONSES: Final[dict[int | str, dict[str, object]]] = {
    status.HTTP_403_FORBIDDEN: NOT_PERMITTED_RESPONSE,
    status.HTTP_404_NOT_FOUND: UNKNOWN_RESERVATION_RESPONSE,
    status.HTTP_409_CONFLICT: {
        "description": "The booking is not confirmed, or the customer has no email address."
    },
    status.HTTP_429_TOO_MANY_REQUESTS: {
        "description": "Three re-sends in the last hour. `Retry-After` carries the wait."
    },
}


@router.post(
    MY_RESEND_PATH,
    response_model=ConfirmationResendResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Send the signed in customer's own booking confirmation again",
    responses=RESPONSES,
)
def post_my_confirmation_resend(
    reservation_id: ReservationPathKey,
    user: CustomerUser,
    use_case: ResendConfirmation,
) -> ConfirmationResendResponse:
    """Queue and send the confirmation again for the caller's own booking.

    Raises:
        NotFound: If the booking is absent or not the caller's. HTTP 404.
        StateTransitionError: If it is not confirmed or has no address. HTTP 409.
        TooManyAttempts: If three re-sends happened this hour. HTTP 429.

    """
    outcome = use_case.execute(
        ResendBookingConfirmationCommand(
            actor=actor_of(user), key=ReservationKey.parse(str(reservation_id))
        )
    )
    return ConfirmationResendResponse(email_deliverable=outcome.email_deliverable)


@router.post(
    COUNTER_RESEND_PATH,
    response_model=ConfirmationResendResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Send a booking confirmation again from the counter",
    responses=RESPONSES,
)
def post_counter_confirmation_resend(
    reservation_id: ReservationPathKey,
    user: CounterUser,
    use_case: ResendConfirmation,
) -> ConfirmationResendResponse:
    """Queue and send the confirmation again for a booking at the caller's branch.

    Raises:
        NotFound: If the booking is absent. HTTP 404.
        BranchScopeError: If it is at another branch. HTTP 403.
        StateTransitionError: If it is not confirmed or has no address. HTTP 409.
        TooManyAttempts: If three re-sends happened this hour. HTTP 429.

    """
    outcome = use_case.execute(
        ResendBookingConfirmationCommand(
            actor=actor_of(user), key=ReservationKey.parse(str(reservation_id))
        )
    )
    return ConfirmationResendResponse(email_deliverable=outcome.email_deliverable)
