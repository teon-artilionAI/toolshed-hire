"""Request and response models for the reservation routes.

Field names on the wire are camelCase, as everywhere else at this boundary.
The conventions the catalogue responses state apply here too. Money and a
percentage are strings with two decimals, and a date is `YYYY-MM-DD`.

One more is stated here. An instant is written as ISO 8601 with an offset, as
a clock in Cape Town shows it, for example `2026-10-02T15:30:00+02:00`. The
business keeps one time zone, so a customer reads when their hold runs out
without converting anything.

`canHold`, `canConfirm` and `canCancel` say what the caller may do to the
reservation right now. They are worked out on the server from the state of the
reservation and from who is asking, so a screen never repeats the rules of the
lifecycle.

`assetTags` is filled for counter staff and administrators. A customer is sent
an empty list, because a customer never learns which unit they were given
(US-07).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Final
from uuid import UUID

from pydantic import ConfigDict, Field, PlainSerializer, StringConstraints

from app.api.catalogue_schemas import Money, Percentage
from app.api.schemas import MAXIMUM_QUANTITY, MINIMUM_QUANTITY, CamelModel, ProblemDetail
from app.application.booking.cancel_reservation import REASON_MAX_LENGTH
from app.domain.business_time import in_business_time
from app.domain.enums import ReservationStatus

TIMESTAMP_PRECISION: Final[str] = "seconds"
# The widths of the columns the two codes are stored in.
BRANCH_CODE_MAX_LENGTH: Final[int] = 4
MODEL_SLUG_MAX_LENGTH: Final[int] = 140
MINIMUM_LINES: Final[int] = 1
# Far more than a hire carries. The bound keeps one request from asking the
# catalogue about an unlimited number of models.
MAXIMUM_LINES: Final[int] = 20
NOTES_MAX_LENGTH: Final[int] = 1000

# How the refusals of these routes are described in the OpenAPI document, so a
# generated client knows each one is a problem document.
REFUSED_BODY_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "A field was refused. `errors.fields` names it.",
}
REFUSED_DATES_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "The dates of the draft can no longer be booked.",
}
REFUSED_QUERY_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "A query parameter was refused. `errors.fields` names it.",
}
NOT_PERMITTED_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": (
        "The caller may not do this. The problem type says why, which is the role, the "
        "branch, an account on hold or an email address that is not verified."
    ),
}
UNKNOWN_RESERVATION_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "There is no such reservation, or it is not the caller's.",
}
CONFLICT_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": (
        "The move is not permitted from the status the reservation is in, or a unit could "
        "not be held for the period."
    ),
}


def _timestamp_text(moment: datetime) -> str:
    """Write an instant as ISO 8601 with the offset of the business time zone."""
    return in_business_time(moment).isoformat(timespec=TIMESTAMP_PRECISION)


Timestamp = Annotated[datetime, PlainSerializer(_timestamp_text, return_type=str)]
TrimmedText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ReservationLineRequest(CamelModel):
    """One model and how many of it."""

    model_slug: Annotated[TrimmedText, Field(max_length=MODEL_SLUG_MAX_LENGTH)] = Field(
        validation_alias="modelSlug"
    )
    quantity: Annotated[int, Field(ge=MINIMUM_QUANTITY, le=MAXIMUM_QUANTITY)]

    # `model_slug` is the documented name and collides with nothing.
    model_config = ConfigDict(protected_namespaces=())


class CreateReservationRequest(CamelModel):
    """A request for a draft reservation.

    The period is half open. `to` is the day the equipment comes back and is
    not charged. `customerProfileId` is for staff, who book for a named
    customer. A customer leaves it null and books for themselves.
    """

    branch_code: Annotated[TrimmedText, Field(max_length=BRANCH_CODE_MAX_LENGTH)] = Field(
        validation_alias="branchCode"
    )
    from_date: date = Field(validation_alias="from")
    to_date: date = Field(validation_alias="to")
    lines: Annotated[
        list[ReservationLineRequest], Field(min_length=MINIMUM_LINES, max_length=MAXIMUM_LINES)
    ]
    customer_profile_id: UUID | None = Field(default=None, validation_alias="customerProfileId")
    notes: Annotated[str, Field(max_length=NOTES_MAX_LENGTH)] | None = None


class CancellationRequest(CamelModel):
    """Why a reservation is being cancelled, when the caller wants to say."""

    reason: Annotated[str, Field(max_length=REASON_MAX_LENGTH)] | None = None


class ReservationLineResponse(CamelModel):
    """One line of a reservation, with the rates it was priced at."""

    model_slug: str = Field(serialization_alias="modelSlug")
    model_name: str = Field(serialization_alias="modelName")
    quantity: int
    daily_rate: Money = Field(serialization_alias="dailyRate")
    weekly_rate: Money = Field(serialization_alias="weeklyRate")
    deposit_per_unit: Money = Field(serialization_alias="depositPerUnit")
    line_subtotal_ex_vat: Money = Field(serialization_alias="lineSubtotalExVat")
    allocated_count: int = Field(serialization_alias="allocatedCount")
    asset_tags: list[str] = Field(serialization_alias="assetTags")

    # `model_slug` and `model_name` are the documented names and collide with nothing.
    model_config = ConfigDict(protected_namespaces=())


class ReservationResponse(CamelModel):
    """One reservation, as the caller is allowed to see it.

    `subtotalExVat` is the hire after the trade discount, and `vatAmount` is
    worked out on it, so the two add up to `estimatedTotalIncVat`. The deposit
    is not in that total, because a deposit is held and given back.
    """

    id: UUID
    reference: str
    status: ReservationStatus
    branch_code: str = Field(serialization_alias="branchCode")
    branch_name: str = Field(serialization_alias="branchName")
    from_date: date = Field(serialization_alias="from")
    to_date: date = Field(serialization_alias="to")
    hire_days: int = Field(serialization_alias="hireDays")
    lines: list[ReservationLineResponse]
    subtotal_ex_vat: Money = Field(serialization_alias="subtotalExVat")
    discount_percent: Percentage = Field(serialization_alias="discountPercent")
    vat_amount: Money = Field(serialization_alias="vatAmount")
    estimated_total_inc_vat: Money = Field(serialization_alias="estimatedTotalIncVat")
    deposit_total: Money = Field(serialization_alias="depositTotal")
    hold_expires_at: Timestamp | None = Field(serialization_alias="holdExpiresAt")
    confirmed_at: Timestamp | None = Field(serialization_alias="confirmedAt")
    cancelled_at: Timestamp | None = Field(serialization_alias="cancelledAt")
    cancellation_reason: str | None = Field(serialization_alias="cancellationReason")
    can_hold: bool = Field(serialization_alias="canHold")
    can_confirm: bool = Field(serialization_alias="canConfirm")
    can_cancel: bool = Field(serialization_alias="canCancel")
    customer_name: str = Field(serialization_alias="customerName")
    created_at: Timestamp = Field(serialization_alias="createdAt")


class ReservationPageResponse(CamelModel):
    """One page of reservations, newest first."""

    items: list[ReservationResponse]
    page: int
    page_size: int = Field(serialization_alias="pageSize")
    total: int
