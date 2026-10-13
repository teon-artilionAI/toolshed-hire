"""What the routes of the closure days share, the path key, the commands and the responses.

A request body becomes a command here and a read model becomes a response
here, once, so the router stays about its routes. Nothing is worked out in it
but the one thing the boundary owns, which is that a branch code is read in
capitals, the way the branches are known.
"""

from __future__ import annotations

from typing import Annotated, Final
from uuid import UUID

from fastapi import Path

from app.api.admin_user_presenter import branch_code
from app.api.booking_deps import actor_of
from app.api.closure_day_schemas import (
    ClosedDayEntryResponse,
    ClosedDayListResponse,
    ClosureDayRequest,
    ClosureDayResponse,
    StrandedBookingListResponse,
    StrandedBookingResponse,
)
from app.application.trading.closure_days import AddClosureDayCommand, CancelClosureDayCommand
from app.application.trading.closure_models import ClosedDayEntry, StrandedBookings
from app.domain.closure_day import ClosureDay
from app.infrastructure.models import UserAccount

# The tag of the router, which is the module the branches belong to.
BRANCHES_TAG: Final[str] = "branches"
CLOSURE_DAYS_PATH: Final[str] = "/closure-days"

ClosurePathKey = Annotated[UUID, Path(alias="id", description="The key of the closure day.")]


def add_command(user: UserAccount, request: ClosureDayRequest) -> AddClosureDayCommand:
    """Return the command that closes the day a request names."""
    return AddClosureDayCommand(
        actor=actor_of(user),
        branch_code=branch_code(request.branch_code),
        day=request.day,
        reason=request.reason,
    )


def cancel_command(user: UserAccount, closure_id: UUID) -> CancelClosureDayCommand:
    """Return the command that opens a closed day again."""
    return CancelClosureDayCommand(actor=actor_of(user), closure_id=closure_id)


def closure_response(closure: ClosureDay) -> ClosureDayResponse:
    """Write one closure day in the shape the contract gives it."""
    return ClosureDayResponse(
        id=closure.id,
        branch_code=closure.branch_code,
        day=closure.day,
        reason=closure.reason,
        created_at=closure.created_at,
        cancelled_at=closure.cancelled_at,
    )


def closed_days_response(entries: tuple[ClosedDayEntry, ...]) -> ClosedDayListResponse:
    """Write the owner's list of closed days."""
    return ClosedDayListResponse(
        items=[
            ClosedDayEntryResponse.model_validate(
                {
                    "day": entry.day,
                    "branch_code": entry.branch_code,
                    "reason": entry.reason,
                    "kind": entry.kind,
                    "closure_id": entry.closure_id,
                }
            )
            for entry in entries
        ]
    )


def stranded_response(found: StrandedBookings) -> StrandedBookingListResponse:
    """Write the bookings a closure would strand."""
    return StrandedBookingListResponse(
        items=[
            StrandedBookingResponse.model_validate(
                {
                    "reference": booking.reference,
                    "branch_code": booking.branch_code,
                    "customer_name": booking.customer_name,
                    "customer_phone": booking.customer_phone,
                    "from_date": booking.start,
                    "to_date": booking.end,
                    "hire_day": booking.hire_day,
                }
            )
            for booking in found.items
        ],
        total=found.total,
    )
