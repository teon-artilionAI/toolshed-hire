"""Request and response models of the owner's closure days.

Field names on the wire are camelCase, as everywhere else at this boundary. A
day is an ISO 8601 date and an instant is ISO 8601 with the offset of Cape
Town.

A new closure names its branch, or null for every branch, the day and the
reason. The body refuses a field it does not know. The checks here are about
shape, a type and a length. The rules, that the day is today or later and at
most a year ahead and that the branch is trading, are in the domain and the
use case, and both refuse a field in the same place, under `errors.fields`.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Final, Literal
from uuid import UUID

from pydantic import Field

from app.api.account_schemas import StrictRequest
from app.api.reservation_schemas import BRANCH_CODE_MAX_LENGTH, Timestamp, TrimmedText
from app.api.schemas import CamelModel, ProblemDetail
from app.domain.closure_day import CLOSURE_REASON_MAX_LENGTH

ClosureReasonText = Annotated[TrimmedText, Field(max_length=CLOSURE_REASON_MAX_LENGTH)]
ClosureBranchCode = Annotated[TrimmedText, Field(max_length=BRANCH_CODE_MAX_LENGTH)]

UNKNOWN_CLOSURE_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "There is no such closure day.",
}
CLOSURE_REFUSED_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": (
        "The day is closed already, at that branch or at every branch. `detail` names the "
        "closure to cancel first."
    ),
}
CANCEL_REFUSED_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "The closure day was cancelled already.",
}


class ClosureDayRequest(StrictRequest):
    """A day to close, at one branch or at every branch, and why. Customers read the reason."""

    branch_code: ClosureBranchCode | None = Field(default=None, validation_alias="branchCode")
    day: date
    reason: ClosureReasonText


class ClosedDayEntryResponse(CamelModel):
    """One day the owner's list shows as closed.

    `branchCode` is null for a day every branch is closed. `closureId` is the
    key to cancel a closure day by, and null for a public holiday, which
    cannot be cancelled.
    """

    day: date
    branch_code: str | None = Field(serialization_alias="branchCode")
    reason: str
    kind: Literal["public_holiday", "closure"]
    closure_id: UUID | None = Field(serialization_alias="closureId")


class ClosedDayListResponse(CamelModel):
    """Every public holiday and live closure day in the span, by day."""

    items: list[ClosedDayEntryResponse]


class ClosureDayResponse(CamelModel):
    """One closure day, as it was added or as it is once cancelled.

    `branchCode` is null for a closure of every branch. `cancelledAt` is null
    while the closure is live.
    """

    id: UUID
    branch_code: str | None = Field(serialization_alias="branchCode")
    day: date
    reason: str
    created_at: Timestamp = Field(serialization_alias="createdAt")
    cancelled_at: Timestamp | None = Field(serialization_alias="cancelledAt")


class StrandedBookingResponse(CamelModel):
    """A booking or a hire out that falls on the day about to close.

    `hireDay` is `collection` when a held or confirmed booking starts that day,
    `return` when it ends that day, and `due_back` when the equipment of a hire
    still out is due back that day. A hire's `reference` is the hire's own, and
    its `from` is the day it was collected. Nothing is changed. The owner rings
    the customer.
    """

    reference: str
    branch_code: str = Field(serialization_alias="branchCode")
    customer_name: str = Field(serialization_alias="customerName")
    customer_phone: str = Field(serialization_alias="customerPhone")
    from_date: date = Field(serialization_alias="from")
    to_date: date = Field(serialization_alias="to")
    hire_day: Literal["collection", "return", "due_back"] = Field(serialization_alias="hireDay")


class StrandedBookingListResponse(CamelModel):
    """The bookings and hires out a closure would strand, by start, and how many in all.

    `items` holds at most two hundred. `total` counts every one of them.
    """

    items: list[StrandedBookingResponse]
    total: int


__all__ = [
    "CANCEL_REFUSED_RESPONSE",
    "CLOSURE_REFUSED_RESPONSE",
    "UNKNOWN_CLOSURE_RESPONSE",
    "ClosedDayEntryResponse",
    "ClosedDayListResponse",
    "ClosureDayRequest",
    "ClosureDayResponse",
    "StrandedBookingListResponse",
    "StrandedBookingResponse",
]
