"""Request and response models for checkout and the rental.

Field names on the wire are camelCase, as everywhere else at this boundary.
Money and a percentage are strings with two decimals, a date is `YYYY-MM-DD`
and an instant is ISO 8601 with the offset of Cape Town.

The checkout request names every field it accepts. Its checks are about shape.
That every unit of the reservation is listed once and that the agreement is
signed are rules of the domain, and a refusal of either names its field under
`errors.fields` all the same.

`assetTag` on a rental item is null for a customer, who never learns which
unit they were given (US-07). The routes of this change are for staff, who
always see it.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Final
from uuid import UUID

from pydantic import ConfigDict, Field

from app.api.account_schemas import StrictRequest
from app.api.catalogue_schemas import Money, Percentage
from app.api.reservation_schemas import MAXIMUM_LINES, Timestamp
from app.api.schemas import CamelModel, ProblemDetail
from app.domain.booking_line import MAXIMUM_LINE_QUANTITY
from app.domain.enums import (
    AccountStatus,
    ChargeStatus,
    ChargeType,
    ConditionGrade,
    IdDocType,
    RentalStatus,
    ReservationStatus,
)
from app.domain.rental import DamageAssessment, SettlementWait

# The most units one reservation can hold, so the most one checkout can list.
MAXIMUM_UNITS: Final[int] = MAXIMUM_LINES * MAXIMUM_LINE_QUANTITY
MINIMUM_UNITS: Final[int] = 1
# The width of the column accessories are stored in.
ACCESSORIES_MAX_LENGTH: Final[int] = 200
# The largest reading an INTEGER column holds.
HOUR_METER_MAX: Final[int] = 2_147_483_647
HOUR_METER_MIN: Final[int] = 0

CHECKOUT_REFUSED_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": (
        "The reservation is not confirmed or its hire has not started, and `detail` says "
        "which, or a unit cannot go out on hire."
    ),
}
UNKNOWN_RENTAL_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "There is no such rental.",
}


class CheckoutItemRequest(StrictRequest):
    """What the counter records about one unit as it goes out."""

    allocation_id: UUID = Field(validation_alias="allocationId")
    condition_out: ConditionGrade = Field(validation_alias="conditionOut")
    accessories_out: Annotated[str, Field(max_length=ACCESSORIES_MAX_LENGTH)] | None = Field(
        default=None, validation_alias="accessoriesOut"
    )
    hour_meter_out: Annotated[int, Field(ge=HOUR_METER_MIN, le=HOUR_METER_MAX)] | None = Field(
        default=None, validation_alias="hourMeterOut"
    )


class CheckoutRequest(StrictRequest):
    """Every unit of the reservation, once each, and the customer's signature."""

    items: Annotated[
        list[CheckoutItemRequest], Field(min_length=MINIMUM_UNITS, max_length=MAXIMUM_UNITS)
    ]
    agreement_signed: bool = Field(validation_alias="agreementSigned")


class CheckoutCustomerResponse(CamelModel):
    """The customer the equipment is handed to."""

    id: UUID
    display_name: str = Field(serialization_alias="displayName")
    phone: str
    id_document_type: IdDocType = Field(serialization_alias="idDocumentType")
    id_document_last4: str = Field(serialization_alias="idDocumentLast4")
    account_status: AccountStatus = Field(serialization_alias="accountStatus")


class CheckoutUnitResponse(CamelModel):
    """One unit the reservation holds, as the counter hands it over."""

    allocation_id: UUID = Field(serialization_alias="allocationId")
    asset_tag: str = Field(serialization_alias="assetTag")
    model_name: str = Field(serialization_alias="modelName")
    model_slug: str = Field(serialization_alias="modelSlug")
    condition_grade: ConditionGrade = Field(serialization_alias="conditionGrade")
    hour_meter: int | None = Field(serialization_alias="hourMeter")
    deposit_per_unit: Money = Field(serialization_alias="depositPerUnit")

    # `model_name` and `model_slug` are the documented names and collide with nothing.
    model_config = ConfigDict(protected_namespaces=())


class CheckoutPreviewResponse(CamelModel):
    """What the counter needs to hand the equipment of a reservation over.

    `refusal` is a sentence when `canCheckOut` is false. `rentalId` is set once
    the reservation has been collected.
    """

    reservation_id: UUID = Field(serialization_alias="reservationId")
    reference: str
    status: ReservationStatus
    branch_code: str = Field(serialization_alias="branchCode")
    branch_name: str = Field(serialization_alias="branchName")
    customer: CheckoutCustomerResponse
    from_date: date = Field(serialization_alias="from")
    to_date: date = Field(serialization_alias="to")
    hire_days: int = Field(serialization_alias="hireDays")
    units: list[CheckoutUnitResponse]
    hire_total_inc_vat: Money = Field(serialization_alias="hireTotalIncVat")
    deposit_total: Money = Field(serialization_alias="depositTotal")
    can_check_out: bool = Field(serialization_alias="canCheckOut")
    refusal: str | None
    rental_id: UUID | None = Field(serialization_alias="rentalId")


class RentalItemResponse(CamelModel):
    """One unit on a rental.

    `daysLateToday` and `lateFeeToday` are what the late fee would be if the
    unit came back today, worked out on the server. `replacementValue` is the
    value copied onto the booking line, the most a damage report may recover,
    and is null for a customer, as `assetTag` is.
    """

    id: UUID
    asset_tag: str | None = Field(serialization_alias="assetTag")
    model_name: str = Field(serialization_alias="modelName")
    model_slug: str = Field(serialization_alias="modelSlug")
    condition_out: ConditionGrade = Field(serialization_alias="conditionOut")
    condition_in: ConditionGrade | None = Field(serialization_alias="conditionIn")
    hour_meter_out: int | None = Field(serialization_alias="hourMeterOut")
    hour_meter_in: int | None = Field(serialization_alias="hourMeterIn")
    accessories_out: str | None = Field(serialization_alias="accessoriesOut")
    accessories_in: str | None = Field(serialization_alias="accessoriesIn")
    returned_at: Timestamp | None = Field(serialization_alias="returnedAt")
    days_late: int = Field(serialization_alias="daysLate")
    late_fee_per_day: Money = Field(serialization_alias="lateFeePerDay")
    days_late_today: int = Field(serialization_alias="daysLateToday")
    late_fee_today: Money = Field(serialization_alias="lateFeeToday")
    damage_assessment: DamageAssessment = Field(serialization_alias="damageAssessment")
    replacement_value: Money | None = Field(serialization_alias="replacementValue")

    # `model_name` and `model_slug` are the documented names and collide with nothing.
    model_config = ConfigDict(protected_namespaces=())


class ChargeResponse(CamelModel):
    """One money line on a rental. A deposit release is a negative amount."""

    id: UUID
    charge_type: ChargeType = Field(serialization_alias="type")
    description: str
    amount_ex_vat: Money = Field(serialization_alias="amountExVat")
    vat_rate: Percentage = Field(serialization_alias="vatRate")
    vat_amount: Money = Field(serialization_alias="vatAmount")
    amount_inc_vat: Money = Field(serialization_alias="amountIncVat")
    status: ChargeStatus
    raised_at: Timestamp = Field(serialization_alias="raisedAt")
    rental_item_id: UUID | None = Field(serialization_alias="rentalItemId")


class RentalResponse(CamelModel):
    """One rental, as the caller is allowed to see it."""

    id: UUID
    reference: str
    status: RentalStatus
    reservation_id: UUID = Field(serialization_alias="reservationId")
    reservation_reference: str = Field(serialization_alias="reservationReference")
    branch_code: str = Field(serialization_alias="branchCode")
    branch_name: str = Field(serialization_alias="branchName")
    customer_profile_id: UUID = Field(serialization_alias="customerProfileId")
    customer_name: str = Field(serialization_alias="customerName")
    customer_phone: str = Field(serialization_alias="customerPhone")
    from_date: date = Field(serialization_alias="from")
    due_back_on: date = Field(serialization_alias="dueBackOn")
    checked_out_at: Timestamp = Field(serialization_alias="checkedOutAt")
    returned_at: Timestamp | None = Field(serialization_alias="returnedAt")
    items: list[RentalItemResponse]
    charges: list[ChargeResponse]
    deposit_held: Money = Field(serialization_alias="depositHeld")
    deposit_withheld: Money = Field(serialization_alias="depositWithheld")
    deposit_refunded: Money = Field(serialization_alias="depositRefunded")
    balance_due: Money = Field(serialization_alias="balanceDue")
    settled_at: Timestamp | None = Field(serialization_alias="settledAt")
    agreement_signed: bool = Field(serialization_alias="agreementSigned")
    can_return: bool = Field(serialization_alias="canReturn")
    settlement_waiting_on: SettlementWait | None = Field(
        serialization_alias="settlementWaitingOn"
    )


# Declared after the rental, because the repeated checkout answers with one.
ALREADY_CHECKED_OUT_RESPONSE: Final[dict[str, object]] = {
    "model": RentalResponse,
    "description": "The reservation was already checked out. The rental it opened, unchanged.",
}
