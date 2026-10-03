"""Request and response models for damage reports.

Field names on the wire are camelCase, as everywhere else at this boundary. An
amount is a string with at most two decimals, for example "450.00", in a
request as in a response, and a number is refused, so no amount ever passes
through a float.

`chargeableToCustomer` has no default and accepts a JSON boolean and nothing
else, so a report that leaves the decision out is answered 422 naming the
field (BR-40). The checks here are about shape. The rules, that an amount to
recover follows from the decision and stays under the replacement value, are
the domain's, and a refusal of either names its field under `errors.fields`
all the same.

A list of reports is `{"items": [...], "page": 1, "pageSize": 20, "total": 0}`,
as every list of this API is.
"""

from __future__ import annotations

from typing import Annotated, Final, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, StrictBool, StringConstraints

from app.api.account_schemas import StrictRequest
from app.api.catalogue_schemas import Money
from app.api.reservation_schemas import Timestamp
from app.api.schemas import CamelModel, ProblemDetail
from app.domain.enums import DamageSeverity, DamageStatus

# An amount in rand with at most two decimals, no larger than the money columns hold.
MONEY_PATTERN: Final[str] = r"^\d{1,10}(\.\d{1,2})?$"
ASSET_TAG_MAX_LENGTH: Final[int] = 16
DESCRIPTION_MAX_LENGTH: Final[int] = 2000
RESOLUTION_NOTES_MAX_LENGTH: Final[int] = 2000

AmountText = Annotated[str, StringConstraints(strip_whitespace=True, pattern=MONEY_PATTERN)]
AssetTagText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_upper=True, min_length=1, max_length=ASSET_TAG_MAX_LENGTH
    ),
]
DescriptionText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=DESCRIPTION_MAX_LENGTH)
]
NotesText = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=RESOLUTION_NOTES_MAX_LENGTH)
]

REPORT_REFUSED_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": (
        "The unit is out on hire or retired, it waits for the report of another hire, or the "
        "deposit of the hire was already settled, and `detail` says which."
    ),
}
REPORT_MOVE_REFUSED_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": (
        "The report cannot make that move from where it stands, or a booking still holds the "
        "unit it would retire, and `detail` says which."
    ),
}
UNKNOWN_REPORT_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "There is no such damage report.",
}


class DamageReportRequest(StrictRequest):
    """A damage report as the counter files it."""

    asset_tag: AssetTagText = Field(validation_alias="assetTag")
    rental_item_id: UUID | None = Field(default=None, validation_alias="rentalItemId")
    severity: DamageSeverity
    description: DescriptionText
    repair_estimate: AmountText = Field(validation_alias="repairEstimate")
    chargeable_to_customer: StrictBool = Field(validation_alias="chargeableToCustomer")
    recovery_amount: AmountText | None = Field(default=None, validation_alias="recoveryAmount")


class ResolutionRequest(StrictRequest):
    """How an administrator closes a report."""

    outcome: Literal["RESOLVED", "WRITTEN_OFF"]
    actual_repair_cost: AmountText | None = Field(
        default=None, validation_alias="actualRepairCost"
    )
    resolution_notes: NotesText | None = Field(default=None, validation_alias="resolutionNotes")


class DamageReportResponse(CamelModel):
    """One damage report, as staff read it."""

    id: UUID
    reference: str
    asset_tag: str = Field(serialization_alias="assetTag")
    model_name: str = Field(serialization_alias="modelName")
    branch_code: str = Field(serialization_alias="branchCode")
    rental_id: UUID | None = Field(serialization_alias="rentalId")
    rental_reference: str | None = Field(serialization_alias="rentalReference")
    rental_item_id: UUID | None = Field(serialization_alias="rentalItemId")
    severity: DamageSeverity
    status: DamageStatus
    description: str
    repair_estimate: Money = Field(serialization_alias="repairEstimate")
    actual_repair_cost: Money | None = Field(serialization_alias="actualRepairCost")
    chargeable_to_customer: bool = Field(serialization_alias="chargeableToCustomer")
    recovery_charged: Money | None = Field(serialization_alias="recoveryCharged")
    replacement_value: Money = Field(serialization_alias="replacementValue")
    reported_at: Timestamp = Field(serialization_alias="reportedAt")
    reported_by_name: str = Field(serialization_alias="reportedByName")
    resolved_at: Timestamp | None = Field(serialization_alias="resolvedAt")
    resolution_notes: str | None = Field(serialization_alias="resolutionNotes")

    # `model_name` is the documented name and collides with nothing.
    model_config = ConfigDict(protected_namespaces=())


class DamageReportPageResponse(CamelModel):
    """One page of damage reports, newest first."""

    items: list[DamageReportResponse]
    page: int
    page_size: int = Field(serialization_alias="pageSize")
    total: int
