"""Request and response models of the asset register, `AdminAsset` and its history.

Field names on the wire are camelCase, as everywhere else at this boundary.
Money is a string with two decimals, both ways, so no amount passes through a
float, a day is `YYYY-MM-DD` and an instant is ISO 8601 with the offset of
Cape Town. A list is `{"items": [...], "page": 1, "pageSize": 20, "total": 0}`.

A registration names the tag, the model and the branch, which never change
afterwards (BR-34), and the paperwork. An edit names any of the serial number,
the grade, the meter reading and the notes. A field an edit leaves out keeps
its value, and a field it sends as null is cleared, which the grade does not
allow. Every body refuses a field it does not know, so an edit that sends the
tag, the model or the branch is refused naming it.

A move names the status to go to and, to take a unit out of service, the
reason. `allowedTransitions` is worked out on the server from the asset state
model, so the screen offers exactly the moves the route accepts.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Final
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints, field_validator

from app.api.account_schemas import StrictRequest
from app.api.admin_catalogue_schemas import MoneyText, refuse_null
from app.api.catalogue_schemas import Money
from app.api.reservation_schemas import BRANCH_CODE_MAX_LENGTH, Timestamp, TrimmedText
from app.api.schemas import CamelModel, ProblemDetail
from app.application.catalogue.asset_read_models import AssetHistoryKind
from app.domain import asset_register as unit_rules
from app.domain.enums import AssetStatus, ConditionGrade
from app.domain.override_reason import REASON_MAX_LENGTH

AssetTagText = Annotated[str, Field(max_length=unit_rules.ASSET_TAG_MAX_LENGTH)]
SerialText = Annotated[str, Field(max_length=unit_rules.SERIAL_NUMBER_MAX_LENGTH)]
NotesText = Annotated[str, Field(max_length=unit_rules.NOTES_MAX_LENGTH)]
# Blank is accepted here, because a move back to the shelf needs no reason.
# The domain holds a reason that is given to five characters or more.
MoveReasonText = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=REASON_MAX_LENGTH)
]

UNKNOWN_UNIT_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "No unit carries that tag.",
}
MOVE_REFUSED_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": (
        "The move is not one the unit may make from the status it is in, which `detail` "
        "names, or a booking or an open damage report still holds the unit and `detail` "
        "names it."
    ),
}


class AssetCreateRequest(StrictRequest):
    """A new unit. It starts at INTAKE, and its tag, model and branch never change."""

    asset_tag: AssetTagText = Field(validation_alias="assetTag")
    model_id: UUID = Field(validation_alias="modelId")
    branch_code: Annotated[TrimmedText, Field(max_length=BRANCH_CODE_MAX_LENGTH)] = Field(
        validation_alias="branchCode"
    )
    serial_number: SerialText | None = Field(default=None, validation_alias="serialNumber")
    condition_grade: ConditionGrade = Field(validation_alias="conditionGrade")
    acquired_on: date = Field(validation_alias="acquiredOn")
    acquisition_cost: MoneyText = Field(validation_alias="acquisitionCost")
    hour_meter_reading: int | None = Field(default=None, validation_alias="hourMeterReading")
    notes: NotesText | None = None

    model_config = ConfigDict(protected_namespaces=())


class AssetUpdateRequest(StrictRequest):
    """The paperwork of a unit to change, any of it. Never the tag, the model or the branch."""

    serial_number: SerialText | None = Field(default=None, validation_alias="serialNumber")
    condition_grade: ConditionGrade | None = Field(
        default=None, validation_alias="conditionGrade"
    )
    hour_meter_reading: int | None = Field(default=None, validation_alias="hourMeterReading")
    notes: NotesText | None = None

    @field_validator("condition_grade", mode="before")
    @classmethod
    def not_null(cls, value: object) -> object:
        """Refuse null for the grade, which every unit has."""
        return refuse_null(value)


class AssetTransitionRequest(StrictRequest):
    """The status to move a unit to by hand, and why."""

    to: AssetStatus
    reason: MoveReasonText | None = None


class AdminAssetResponse(CamelModel):
    """One unit as the register shows it, retired or not.

    `allowedTransitions` lists the statuses an administrator may move it to by
    hand, from the asset state model. `activeAllocationCount` counts the
    bookings that hold it now and `openDamageReports` its reports that are
    open or under repair.
    """

    id: UUID
    asset_tag: str = Field(serialization_alias="assetTag")
    model_id: UUID = Field(serialization_alias="modelId")
    model_name: str = Field(serialization_alias="modelName")
    model_slug: str = Field(serialization_alias="modelSlug")
    category_name: str = Field(serialization_alias="categoryName")
    branch_code: str = Field(serialization_alias="branchCode")
    branch_name: str = Field(serialization_alias="branchName")
    serial_number: str | None = Field(serialization_alias="serialNumber")
    status: AssetStatus
    condition_grade: ConditionGrade = Field(serialization_alias="conditionGrade")
    acquired_on: date = Field(serialization_alias="acquiredOn")
    acquisition_cost: Money = Field(serialization_alias="acquisitionCost")
    hour_meter_reading: int | None = Field(serialization_alias="hourMeterReading")
    notes: str | None
    retired_on: date | None = Field(serialization_alias="retiredOn")
    active_allocation_count: int = Field(serialization_alias="activeAllocationCount")
    open_damage_reports: int = Field(serialization_alias="openDamageReports")
    allowed_transitions: list[AssetStatus] = Field(serialization_alias="allowedTransitions")

    model_config = ConfigDict(protected_namespaces=())


class AssetHistoryEntryResponse(CamelModel):
    """One line of a unit's history. `reference` is the booking, rental or report, or null."""

    at: Timestamp
    kind: AssetHistoryKind
    summary: str
    reference: str | None


class AdminAssetDetailResponse(AdminAssetResponse):
    """One unit with its history, the newest first, at most fifty entries."""

    history: list[AssetHistoryEntryResponse]


class AdminAssetPageResponse(CamelModel):
    """One page of the units, in tag order."""

    items: list[AdminAssetResponse]
    page: int
    page_size: int = Field(serialization_alias="pageSize")
    total: int


__all__ = [
    "MOVE_REFUSED_RESPONSE",
    "UNKNOWN_UNIT_RESPONSE",
    "AdminAssetDetailResponse",
    "AdminAssetPageResponse",
    "AdminAssetResponse",
    "AssetCreateRequest",
    "AssetHistoryEntryResponse",
    "AssetTransitionRequest",
    "AssetUpdateRequest",
]
