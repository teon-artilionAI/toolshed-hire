"""Request and response models for returns, losses, the balance payment and the lists of rentals.

Field names on the wire are camelCase, as everywhere else at this boundary.
The return request names every field it accepts. Its checks are about shape.
That each unit is listed once, is on the rental and has a meter reading no
lower than the one it went out with are rules of the domain, and a refusal of
any of them names its field under `errors.fields` all the same.

`flaggedForDamage` is accepted now so the counter's form does not change when
damage and quarantine arrive in the next change. Here every unit that comes
back goes back on the shelf.

A list of rentals is `{"items": [...], "page": 1, "pageSize": 20, "total": 0}`,
as every list of this API is. A customer's list carries `assetTag` null on
every item.
"""

from __future__ import annotations

from typing import Annotated, Final
from uuid import UUID

from pydantic import Field, StringConstraints

from app.api.account_schemas import StrictRequest
from app.api.hire_schemas import (
    ACCESSORIES_MAX_LENGTH,
    HOUR_METER_MAX,
    HOUR_METER_MIN,
    MAXIMUM_UNITS,
    MINIMUM_UNITS,
    RentalResponse,
)
from app.api.schemas import CamelModel, ProblemDetail
from app.domain.charge import PAYMENT_REFERENCE_MAX_LENGTH
from app.domain.enums import ConditionGrade

# The longest note the counter may write about one unit coming back.
NOTES_MAX_LENGTH: Final[int] = 1000

PaymentReference = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=PAYMENT_REFERENCE_MAX_LENGTH),
]

RETURN_REFUSED_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "A unit named is already back, so nothing was returned.",
}
LOSS_REFUSED_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": (
        "The unit is already back, or it is not yet more than fourteen days past its due "
        "date, and `detail` says which."
    ),
}
NOTHING_DUE_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "Nothing is owed on the rental, so there is no balance to pay.",
}
UNKNOWN_RENTAL_OR_ITEM_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "There is no such rental, or the unit is not on it.",
}


class ReturnItemRequest(StrictRequest):
    """What the counter records about one unit as it comes back."""

    rental_item_id: UUID = Field(validation_alias="rentalItemId")
    condition_in: ConditionGrade = Field(validation_alias="conditionIn")
    hour_meter_in: Annotated[int, Field(ge=HOUR_METER_MIN, le=HOUR_METER_MAX)] | None = Field(
        default=None, validation_alias="hourMeterIn"
    )
    accessories_in: Annotated[str, Field(max_length=ACCESSORIES_MAX_LENGTH)] | None = Field(
        default=None, validation_alias="accessoriesIn"
    )
    notes: Annotated[str, Field(max_length=NOTES_MAX_LENGTH)] | None = None
    flagged_for_damage: bool = Field(default=False, validation_alias="flaggedForDamage")


class ReturnRequest(StrictRequest):
    """One or more units of a rental that came back."""

    items: Annotated[
        list[ReturnItemRequest], Field(min_length=MINIMUM_UNITS, max_length=MAXIMUM_UNITS)
    ]


class BalancePaymentRequest(StrictRequest):
    """The simulated payment of a balance, by the reference the customer was given."""

    payment_reference: PaymentReference = Field(validation_alias="paymentReference")


class RentalPageResponse(CamelModel):
    """One page of rentals."""

    items: list[RentalResponse]
    page: int
    page_size: int = Field(serialization_alias="pageSize")
    total: int
