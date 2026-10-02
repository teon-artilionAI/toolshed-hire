"""What the two reservation routers share, which is the path key and the response.

A reservation is written out the same way by every route that returns one, so
the mapping from what a use case hands back to the shape the contract gives a
reservation is here once. Nothing is worked out in it. Every figure and every
flag was decided before it reached this module.
"""

from __future__ import annotations

from typing import Annotated, Final

from fastapi import Path

from app.api.reservation_schemas import (
    ReservationLineResponse,
    ReservationPageResponse,
    ReservationResponse,
)
from app.application.booking.views import ReservationView, ReservationViewPage

RESERVATIONS_PREFIX: Final[str] = "/reservations"
# The tag of both routers, which is the module they belong to.
BOOKING_TAG: Final[str] = "booking"
# The name of the route that reads one reservation. The `Location` header of a
# new reservation is built from it.
READ_RESERVATION_ROUTE_NAME: Final[str] = "read_reservation"
# A key is a UUID and a reference is shorter, so nothing longer names a reservation.
RESERVATION_KEY_MAX_LENGTH: Final[int] = 36

ReservationPathKey = Annotated[
    str,
    Path(
        alias="id",
        min_length=1,
        max_length=RESERVATION_KEY_MAX_LENGTH,
        description="The key of the reservation, or its reference.",
    ),
]


def reservation_response(view: ReservationView) -> ReservationResponse:
    """Write a reservation in the shape the contract gives it."""
    detail = view.detail
    return ReservationResponse(
        id=detail.id,
        reference=detail.reference,
        status=detail.status,
        branch_code=detail.branch_code,
        branch_name=detail.branch_name,
        from_date=detail.start_date,
        to_date=detail.end_date,
        hire_days=detail.hire_days,
        lines=[
            ReservationLineResponse(
                model_slug=line.model_slug,
                model_name=line.model_name,
                quantity=line.quantity,
                daily_rate=line.daily_rate,
                weekly_rate=line.weekly_rate,
                deposit_per_unit=line.deposit_per_unit,
                line_subtotal_ex_vat=line.line_subtotal_ex_vat,
                allocated_count=line.allocated_count,
                asset_tags=list(line.asset_tags),
            )
            for line in detail.lines
        ],
        subtotal_ex_vat=detail.subtotal_ex_vat,
        discount_percent=detail.discount_percent,
        vat_amount=detail.vat_amount,
        estimated_total_inc_vat=detail.estimated_total_inc_vat,
        deposit_total=detail.deposit_total,
        hold_expires_at=detail.hold_expires_at,
        confirmed_at=detail.confirmed_at,
        cancelled_at=detail.cancelled_at,
        cancellation_reason=detail.cancellation_reason,
        can_hold=view.can_hold,
        can_confirm=view.can_confirm,
        can_cancel=view.can_cancel,
        customer_name=detail.customer_name,
        created_at=detail.created_at,
    )


def reservation_page_response(page: ReservationViewPage) -> ReservationPageResponse:
    """Write one page of reservations in the shape the contract gives it."""
    return ReservationPageResponse(
        items=[reservation_response(view) for view in page.items],
        page=page.page,
        page_size=page.page_size,
        total=page.total,
    )
