"""The corrections of the admin console, charges and allocations (BR-24, BR-25, US-28, US-32).

`POST /api/admin/charges/{id}/waiver` waives a PENDING charge.
`POST /api/admin/charges/{id}/reversal` reverses a SETTLED charge with a new
negated one that points back at it, and leaves the original as it was.
`POST /api/admin/rentals/{id}/adjustments` adds an ADJUSTMENT charge for an
amount that includes VAT, positive or negative and never nothing, and only
negative once the hire is SETTLED, because a settled hire is never edited
(BR-53). Each takes a `reason` of 5 to 200 characters, works the rental's
deposit, balance and status out again through the settlement, and answers 200
with the `Rental` the hire routes return. A correction the charge or the hire
cannot take is a 409.

`POST /api/admin/allocations/{id}/release` releases one active allocation
with the reason REALLOCATED and writes the administrator's reason to the audit
event. It answers 200 with the `Reservation` that held it, which now holds one
unit fewer than it asks for. An allocation that is not active, or whose unit is
out on hire on its booking, is a 409.

Every route is for an administrator alone, read again under a row lock for the
length of the action (`FreshAdminUser`). Counter staff and customers are
refused with 403.
"""

from __future__ import annotations

from typing import Final

from fastapi import APIRouter, status

from app.api.admin_deps import AdjustRental, ForceRelease, ReverseCharge, WaiveCharge
from app.api.admin_presenter import ADMIN_PREFIX, AllocationPathKey, ChargePathKey
from app.api.admin_schemas import (
    ADJUSTMENT_REFUSED_RESPONSE,
    RELEASE_REFUSED_RESPONSE,
    REVERSAL_REFUSED_RESPONSE,
    UNKNOWN_ALLOCATION_RESPONSE,
    UNKNOWN_CHARGE_RESPONSE,
    WAIVER_REFUSED_RESPONSE,
    AdjustmentRequest,
    ReasonRequest,
)
from app.api.booking_deps import actor_of
from app.api.hire_presenter import HIRE_TAG, RentalPathKey, rental_response
from app.api.hire_schemas import UNKNOWN_RENTAL_RESPONSE, RentalResponse
from app.api.identity_deps import FreshAdminUser
from app.api.report_schemas import ADMIN_ONLY_RESPONSE
from app.api.reservation_presenter import reservation_response
from app.api.reservation_schemas import REFUSED_BODY_RESPONSE, ReservationResponse
from app.application.booking.force_release import ForceReleaseCommand
from app.application.hire.charge_corrections import AdjustmentCommand, ChargeCorrectionCommand
from app.application.hire.read_models import RentalKey
from app.domain.money import Money

# The force release belongs to the availability module, which owns the allocation.
AVAILABILITY_TAG: Final[str] = "availability"

router = APIRouter(prefix=ADMIN_PREFIX)

CORRECTION_RESPONSES: Final[dict[int | str, dict[str, object]]] = {
    status.HTTP_403_FORBIDDEN: ADMIN_ONLY_RESPONSE,
    status.HTTP_404_NOT_FOUND: UNKNOWN_CHARGE_RESPONSE,
    status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_BODY_RESPONSE,
}


@router.post(
    "/charges/{id}/waiver",
    response_model=RentalResponse,
    tags=[HIRE_TAG],
    summary="Waive a charge still owed, with a reason",
    responses={**CORRECTION_RESPONSES, status.HTTP_409_CONFLICT: WAIVER_REFUSED_RESPONSE},
)
def post_waiver(
    charge_id: ChargePathKey, payload: ReasonRequest, user: FreshAdminUser, use_case: WaiveCharge
) -> RentalResponse:
    """Waive the charge and work the rental out again, in one transaction.

    Raises:
        NotFound: If there is no such charge. HTTP 404.
        StateTransitionError: If the charge is not pending. HTTP 409.

    """
    command = ChargeCorrectionCommand(
        actor=actor_of(user), charge_id=charge_id, reason=payload.reason
    )
    return rental_response(use_case.execute(command))


@router.post(
    "/charges/{id}/reversal",
    response_model=RentalResponse,
    tags=[HIRE_TAG],
    summary="Reverse a settled charge with a new negated charge, with a reason",
    responses={**CORRECTION_RESPONSES, status.HTTP_409_CONFLICT: REVERSAL_REFUSED_RESPONSE},
)
def post_reversal(
    charge_id: ChargePathKey, payload: ReasonRequest, user: FreshAdminUser, use_case: ReverseCharge
) -> RentalResponse:
    """Reverse the charge and work the rental out again, in one transaction.

    Raises:
        NotFound: If there is no such charge. HTTP 404.
        StateTransitionError: If the charge is not settled, is a deposit
            movement, is itself a reversal or was reversed already. HTTP 409.

    """
    command = ChargeCorrectionCommand(
        actor=actor_of(user), charge_id=charge_id, reason=payload.reason
    )
    return rental_response(use_case.execute(command))


@router.post(
    "/rentals/{id}/adjustments",
    response_model=RentalResponse,
    tags=[HIRE_TAG],
    summary="Adjust a hire by an amount that includes VAT, with a reason",
    responses={
        **CORRECTION_RESPONSES,
        status.HTTP_404_NOT_FOUND: UNKNOWN_RENTAL_RESPONSE,
        status.HTTP_409_CONFLICT: ADJUSTMENT_REFUSED_RESPONSE,
    },
)
def post_adjustment(
    rental_key: RentalPathKey,
    payload: AdjustmentRequest,
    user: FreshAdminUser,
    use_case: AdjustRental,
) -> RentalResponse:
    """Add the adjustment and work the rental out again, in one transaction.

    Raises:
        NotFound: If there is no such rental. HTTP 404.
        ValidationFailure: If the amount is nothing. HTTP 422, naming
            `body.amountIncVat`.
        StateTransitionError: If the amount is owed and the hire is
            SETTLED. HTTP 409.

    """
    command = AdjustmentCommand(
        actor=actor_of(user),
        key=RentalKey.parse(rental_key),
        amount_inc_vat=Money.create(payload.amount_inc_vat),
        reason=payload.reason,
    )
    return rental_response(use_case.execute(command))


@router.post(
    "/allocations/{id}/release",
    response_model=ReservationResponse,
    tags=[AVAILABILITY_TAG],
    summary="Release one active allocation by hand, with a reason",
    responses={
        status.HTTP_403_FORBIDDEN: ADMIN_ONLY_RESPONSE,
        status.HTTP_404_NOT_FOUND: UNKNOWN_ALLOCATION_RESPONSE,
        status.HTTP_409_CONFLICT: RELEASE_REFUSED_RESPONSE,
        status.HTTP_422_UNPROCESSABLE_CONTENT: REFUSED_BODY_RESPONSE,
    },
)
def post_release(
    allocation_id: AllocationPathKey,
    payload: ReasonRequest,
    user: FreshAdminUser,
    use_case: ForceRelease,
) -> ReservationResponse:
    """Release the allocation with the reason REALLOCATED, in one transaction.

    Raises:
        NotFound: If there is no such allocation. HTTP 404.
        StateTransitionError: If it is not active, or its unit is out on hire
            on its booking. HTTP 409.

    """
    command = ForceReleaseCommand(
        actor=actor_of(user), allocation_id=allocation_id, reason=payload.reason
    )
    return reservation_response(use_case.execute(command))
