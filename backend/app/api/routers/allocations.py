"""The allocation endpoint.

This is the path the skeleton exists to prove. A signed in caller posts a
product model, a branch and a half open period, the use case holds specific
tagged units inside one transaction, and the database has the last word.

When the exclusion constraint rejects the insert the use case raises
AssetUnavailableConflict, the domain error handler maps it to 409, and the
response is a problem document naming the period and the quantity. It is never
a 500, because a losing race is a normal outcome of a correct design rather
than a fault.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import AnyRoleUser, SessionDependency
from app.api.schemas import AllocatedAssetResponse, AllocationRequest, AllocationResponse
from app.application.reserve import ReservationCommand, create_reservation_with_allocation
from app.domain.enums import UserRole
from app.domain.errors import AuthorisationFailure, ValidationFailure
from app.domain.period import BookingPeriod, InvalidBookingPeriod
from app.infrastructure.models import UserAccount

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/allocations", tags=["allocations"])


@router.post(
    "",
    response_model=AllocationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Hold specific assets for a hire period",
    responses={
        status.HTTP_409_CONFLICT: {
            "description": "No free unit exists for the requested period.",
        }
    },
)
def post_allocation(
    payload: AllocationRequest, user: AnyRoleUser, session: SessionDependency
) -> AllocationResponse:
    """Create a held reservation and allocate specific assets to it.

    Args:
        payload: The product model, branch, half open period and quantity.
        user: The active account making the request.
        session: The request scoped session. The use case owns the commit.

    Returns:
        The committed reservation with the tagged units held.

    Raises:
        ValidationFailure: If the period is not a valid hire period.
        AuthorisationFailure: If a customer tries to book on someone else's behalf.
        AssetUnavailableConflict: If no free unit exists. Mapped to HTTP 409.

    """
    period = _build_period(payload)
    customer_user_id = _resolve_customer(user, payload)

    logger.info(
        "allocations.request_received",
        extra={
            "actor_user_id": str(user.id),
            "actor_role": user.role.value,
            "customer_user_id": str(customer_user_id),
            "branch_id": str(payload.branch_id),
            "product_model_id": str(payload.product_model_id),
            "period": period.as_postgres_daterange(),
            "quantity": payload.quantity,
        },
    )

    result = create_reservation_with_allocation(
        session,
        ReservationCommand(
            customer_user_id=customer_user_id,
            created_by_user_id=user.id,
            branch_id=payload.branch_id,
            product_model_id=payload.product_model_id,
            period=period,
            quantity=payload.quantity,
        ),
    )

    logger.info(
        "allocations.request_completed",
        extra={
            "reference": result.reference,
            "reservation_id": str(result.reservation_id),
            "allocated_count": len(result.allocated),
        },
    )
    return AllocationResponse(
        reservation_id=result.reservation_id,
        reference=result.reference,
        reservation_line_id=result.reservation_line_id,
        status=result.status.value,
        start_date=period.start,
        end_date=period.end,
        allocated=[
            AllocatedAssetResponse(
                allocation_id=item.allocation_id,
                asset_id=item.asset_id,
                asset_tag=item.asset_tag,
            )
            for item in result.allocated
        ],
    )


def _build_period(payload: AllocationRequest) -> BookingPeriod:
    """Turn the request dates into a validated BookingPeriod.

    Raises:
        ValidationFailure: If the pair of dates cannot form a hire period. The
            domain error is translated here so the caller gets a 422 rather
            than the ValueError subclass leaking to the catch all handler.

    """
    try:
        return BookingPeriod(payload.start_date, payload.end_date)
    except InvalidBookingPeriod as exc:
        raise ValidationFailure(
            str(exc),
            {
                "start_date": payload.start_date.isoformat(),
                "end_date": payload.end_date.isoformat(),
            },
        ) from exc


def _resolve_customer(user: UserAccount, payload: AllocationRequest) -> UUID:
    """Decide whose booking this is.

    Counter staff and administrators book on behalf of a customer standing at
    the counter. A customer may only book for themselves, and asking to book
    for another account is refused rather than quietly rewritten.

    Raises:
        AuthorisationFailure: If a customer names an account other than their own.

    """
    if user.role is UserRole.CUSTOMER:
        if payload.customer_user_id is not None and payload.customer_user_id != user.id:
            logger.warning(
                "allocations.customer_impersonation_rejected",
                extra={
                    "actor_user_id": str(user.id),
                    "requested_customer_user_id": str(payload.customer_user_id),
                },
            )
            raise AuthorisationFailure(
                "A customer may only create a booking for their own account. "
                "Attempted to book on behalf of another account.",
                {"required_roles": ["COUNTER_STAFF", "ADMIN"]},
            )
        return user.id
    return payload.customer_user_id or user.id
