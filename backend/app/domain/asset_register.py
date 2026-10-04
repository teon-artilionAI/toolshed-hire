"""The rules a unit is held to when an administrator registers it or edits it (FR-23, BR-34).

Every physical unit carries a tag painted on it, for example `TSH-DR-0042`. The
tag is unique across the business and never changes once it is assigned
(BR-34), and neither do the model the unit realises and the branch that holds
it. A unit is registered with all three and starts at INTAKE, because it is in
the building but nobody has inspected it yet. It reaches the shelf through the
asset state model like any other move.

What may change afterwards is the paperwork, which is the serial number, the
grade it is in, the last meter reading and the notes. `UnitDetails` holds
exactly those four, so an edit has no field through which a tag, a model or a
branch could reach it.

1. A tag is capital letters and digits in words joined by single hyphens,
   the form of a code, and fits the sixteen characters of its column.
2. A unit is acquired on or before today, because the day it was acquired is
   where its days in the fleet begin for the utilisation report.
3. The acquisition cost is zero or more, in whole cents, and fits its column
   (BR-22).
4. A meter reading is a whole number of hours, zero or more, that fits an
   INTEGER column. A unit without a meter has none.
5. Text is trimmed, blank optional text is kept as nothing, and every value
   fits its column.

A refusal names its field the way this layer names it, under `REFUSED_FIELD`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Final
from uuid import UUID

from app.domain.catalogue import Asset
from app.domain.catalogue_forms import (
    CODE_FORM,
    amount_held,
    field_refusal,
    optional_text,
    required_text,
)
from app.domain.enums import AssetStatus, ConditionGrade

ASSET_TAG: Final[str] = "asset_tag"
MODEL_ID: Final[str] = "model_id"
BRANCH_CODE: Final[str] = "branch_code"
SERIAL_NUMBER: Final[str] = "serial_number"
CONDITION_GRADE: Final[str] = "condition_grade"
ACQUIRED_ON: Final[str] = "acquired_on"
ACQUISITION_COST: Final[str] = "acquisition_cost"
HOUR_METER_READING: Final[str] = "hour_meter_reading"
NOTES: Final[str] = "notes"
STATUS: Final[str] = "status"

# The widths of the columns in the design document. The notes are TEXT, and
# this keeps one request from storing a book.
ASSET_TAG_MAX_LENGTH: Final[int] = 16
SERIAL_NUMBER_MAX_LENGTH: Final[int] = 60
NOTES_MAX_LENGTH: Final[int] = 2000
# The largest value an INTEGER column holds.
LARGEST_METER_READING: Final[int] = 2_147_483_647
NO_HOURS: Final[int] = 0
# Where a unit starts. It is in the building and has not been inspected.
FIRST_STATUS: Final[AssetStatus] = AssetStatus.INTAKE

TAG_RULE: Final[str] = "BR-34"
TAG_FORM_MESSAGE: Final[str] = (
    "Use capital letters and digits, with a single hyphen between words, for example "
    "TSH-DR-0042."
)
ACQUIRED_LATER_MESSAGE: Final[str] = (
    "A unit cannot be acquired after today. Enter the day it was bought."
)
NEGATIVE_READING_MESSAGE: Final[str] = "Enter a meter reading of zero hours or more."
READING_TOO_LARGE_MESSAGE: Final[str] = (
    f"Enter a meter reading of at most {LARGEST_METER_READING:,} hours."
)


@dataclass(frozen=True, slots=True)
class UnitDetails:
    """What an administrator may change about a unit once it is registered.

    Attributes:
        serial_number: The manufacturer's serial number, or None.
        condition_grade: The grade the unit is in.
        hour_meter_reading: The last meter reading, for a unit that has a meter.
        notes: Anything the office wants to keep about the unit, or None.

    """

    serial_number: str | None
    condition_grade: ConditionGrade
    hour_meter_reading: int | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class NewUnitTerms:
    """What an administrator decides about a unit when it is registered.

    Attributes:
        asset_tag: The tag painted on the unit. It never changes (BR-34).
        acquired_on: The day the business acquired it.
        acquisition_cost: What it cost, excluding VAT.
        details: The paperwork that may change later.

    """

    asset_tag: str
    acquired_on: date
    acquisition_cost: Decimal
    details: UnitDetails


@dataclass(frozen=True, slots=True)
class RegisteredUnit:
    """One unit as the register holds it, its place in the lifecycle and its paperwork.

    Attributes:
        unit: The unit as the asset state model sees it, with its tag, model,
            branch, status, grade, meter reading and retirement.
        serial_number: The manufacturer's serial number, or None.
        acquired_on: The day the business acquired it.
        acquisition_cost: What it cost, excluding VAT.
        notes: What the office keeps about it, or None.

    """

    unit: Asset
    serial_number: str | None
    acquired_on: date
    acquisition_cost: Decimal
    notes: str | None

    @property
    def details(self) -> UnitDetails:
        """Return the paperwork an administrator may change."""
        return UnitDetails(
            serial_number=self.serial_number,
            condition_grade=self.unit.condition_grade,
            hour_meter_reading=self.unit.hour_meter_reading,
            notes=self.notes,
        )

    def with_details(self, details: UnitDetails) -> RegisteredUnit:
        """Return the unit with new paperwork and the same tag, model, branch and status."""
        return replace(
            self,
            unit=replace(
                self.unit,
                condition_grade=details.condition_grade,
                hour_meter_reading=details.hour_meter_reading,
            ),
            serial_number=details.serial_number,
            notes=details.notes,
        )


def checked_details(details: UnitDetails) -> UnitDetails:
    """Return the paperwork of a unit trimmed, or refuse the first field that breaks a rule.

    Raises:
        ValidationFailure: Naming the field.

    """
    return UnitDetails(
        serial_number=optional_text(
            SERIAL_NUMBER, details.serial_number, SERIAL_NUMBER_MAX_LENGTH
        ),
        condition_grade=details.condition_grade,
        hour_meter_reading=_meter_reading(details.hour_meter_reading),
        notes=optional_text(NOTES, details.notes, NOTES_MAX_LENGTH),
    )


def checked_new_unit(terms: NewUnitTerms, *, today: date) -> NewUnitTerms:
    """Return the terms of a new unit trimmed, or refuse the first field that breaks a rule.

    Args:
        terms: What the administrator entered.
        today: The current business day.

    Raises:
        ValidationFailure: Naming the field.

    """
    tag = required_text(ASSET_TAG, terms.asset_tag, ASSET_TAG_MAX_LENGTH)
    if CODE_FORM.fullmatch(tag) is None:
        raise field_refusal(ASSET_TAG, TAG_FORM_MESSAGE, rule=TAG_RULE)
    if terms.acquired_on > today:
        raise field_refusal(ACQUIRED_ON, ACQUIRED_LATER_MESSAGE)
    return NewUnitTerms(
        asset_tag=tag,
        acquired_on=terms.acquired_on,
        acquisition_cost=amount_held(ACQUISITION_COST, terms.acquisition_cost),
        details=checked_details(terms.details),
    )


def registered(
    terms: NewUnitTerms, *, unit_id: UUID, product_model_id: UUID, branch_id: UUID
) -> RegisteredUnit:
    """Return a new unit as the register holds it, at INTAKE.

    Args:
        terms: The checked terms of the unit.
        unit_id: The key the unit is stored under.
        product_model_id: The model it realises.
        branch_id: The branch that holds it.

    """
    details = terms.details
    return RegisteredUnit(
        unit=Asset(
            id=unit_id,
            asset_tag=terms.asset_tag,
            product_model_id=product_model_id,
            branch_id=branch_id,
            status=FIRST_STATUS,
            condition_grade=details.condition_grade,
            hour_meter_reading=details.hour_meter_reading,
        ),
        serial_number=details.serial_number,
        acquired_on=terms.acquired_on,
        acquisition_cost=terms.acquisition_cost,
        notes=details.notes,
    )


def _meter_reading(reading: int | None) -> int | None:
    """Return a meter reading the column can hold, or refuse it.

    Raises:
        ValidationFailure: Naming `hour_meter_reading`.

    """
    if reading is None:
        return None
    if reading < NO_HOURS:
        raise field_refusal(HOUR_METER_READING, NEGATIVE_READING_MESSAGE)
    if reading > LARGEST_METER_READING:
        raise field_refusal(HOUR_METER_READING, READING_TOO_LARGE_MESSAGE)
    return reading
