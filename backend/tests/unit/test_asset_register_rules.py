"""The rules of the asset register, a unit registered and edited, with no database (FR-23, BR-34).

A unit is registered with a tag of capital letters and digits joined by
single hyphens, acquired on or before today, at a cost of zero or more in
whole cents, and starts at INTAKE. Its paperwork is trimmed, blank text is
kept as nothing, and a meter reading is a whole number of hours that fits its
column. Changing the paperwork keeps the tag, the model, the branch and the
status exactly as they were. Each refusal names its field.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Final
from uuid import uuid4

import pytest

from app.domain.asset_register import (
    ACQUIRED_ON,
    ACQUISITION_COST,
    ASSET_TAG,
    HOUR_METER_READING,
    LARGEST_METER_READING,
    NOTES,
    NOTES_MAX_LENGTH,
    SERIAL_NUMBER,
    SERIAL_NUMBER_MAX_LENGTH,
    NewUnitTerms,
    UnitDetails,
    checked_details,
    checked_new_unit,
    registered,
)
from app.domain.customer_account import REFUSED_FIELD
from app.domain.enums import AssetStatus, ConditionGrade
from app.domain.errors import ValidationFailure

TODAY: Final[date] = date(2026, 3, 2)


def details(**changes: object) -> UnitDetails:
    """Return paperwork that keeps every rule, with any field changed."""
    kept = UnitDetails(
        serial_number="SN-882731",
        condition_grade=ConditionGrade.A,
        hour_meter_reading=120,
        notes="Bought with two chisels.",
    )
    return replace(kept, **changes)


def terms(**changes: object) -> NewUnitTerms:
    """Return the terms of a new hammer that keep every rule, with any field changed."""
    kept = NewUnitTerms(
        asset_tag="TSH-DR-0099",
        acquired_on=date(2026, 2, 1),
        acquisition_cost=Decimal("3900.00"),
        details=details(),
    )
    return replace(kept, **changes)


def refused_field_of(failure: pytest.ExceptionInfo[ValidationFailure]) -> object:
    """Return the field a refusal names."""
    return failure.value.detail[REFUSED_FIELD]


class TestRegistering:
    """A unit that keeps every rule is registered at INTAKE, trimmed."""

    def test_a_new_unit_starts_at_intake_with_its_tag_model_and_branch(self) -> None:
        model_id, branch_id, unit_id = uuid4(), uuid4(), uuid4()
        checked = checked_new_unit(terms(), today=TODAY)
        unit = registered(
            checked, unit_id=unit_id, product_model_id=model_id, branch_id=branch_id
        )
        assert (unit.unit.id, unit.unit.asset_tag, unit.unit.status) == (
            unit_id,
            "TSH-DR-0099",
            AssetStatus.INTAKE,
        )
        assert (unit.unit.product_model_id, unit.unit.branch_id) == (model_id, branch_id)
        assert (unit.unit.retired_on, unit.details) == (None, details())
        assert (unit.acquired_on, unit.acquisition_cost) == (date(2026, 2, 1), Decimal("3900.00"))

    def test_text_is_trimmed_and_blank_optional_text_is_kept_as_nothing(self) -> None:
        checked = checked_new_unit(
            terms(
                asset_tag="  TSH-DR-0099 ",
                details=details(serial_number="   ", notes=" Spare battery. "),
            ),
            today=TODAY,
        )
        assert (checked.asset_tag, checked.details.serial_number, checked.details.notes) == (
            "TSH-DR-0099",
            None,
            "Spare battery.",
        )

    def test_a_unit_acquired_today_with_no_meter_and_no_cost_is_accepted(self) -> None:
        checked = checked_new_unit(
            terms(
                acquired_on=TODAY,
                acquisition_cost=Decimal("0"),
                details=details(hour_meter_reading=None),
            ),
            today=TODAY,
        )
        assert (checked.acquisition_cost, checked.details.hour_meter_reading) == (
            Decimal("0.00"),
            None,
        )

    @pytest.mark.parametrize(
        ("changes", "field"),
        [
            ({"asset_tag": ""}, ASSET_TAG),
            ({"asset_tag": "tsh-dr-0099"}, ASSET_TAG),
            ({"asset_tag": "TSH DR 0099"}, ASSET_TAG),
            ({"asset_tag": "TSH--DR-0099"}, ASSET_TAG),
            ({"asset_tag": "TSH-DRILL-0000099"}, ASSET_TAG),
            ({"acquired_on": date(2026, 3, 3)}, ACQUIRED_ON),
            ({"acquisition_cost": Decimal("-0.01")}, ACQUISITION_COST),
            ({"acquisition_cost": Decimal("10.005")}, ACQUISITION_COST),
            ({"acquisition_cost": Decimal("10000000000.00")}, ACQUISITION_COST),
            (
                {"details": details(serial_number="S" * (SERIAL_NUMBER_MAX_LENGTH + 1))},
                SERIAL_NUMBER,
            ),
            ({"details": details(notes="N" * (NOTES_MAX_LENGTH + 1))}, NOTES),
            ({"details": details(hour_meter_reading=-1)}, HOUR_METER_READING),
            (
                {"details": details(hour_meter_reading=LARGEST_METER_READING + 1)},
                HOUR_METER_READING,
            ),
        ],
    )
    def test_a_field_that_breaks_a_rule_is_refused_naming_it(
        self, changes: dict[str, object], field: str
    ) -> None:
        with pytest.raises(ValidationFailure) as failure:
            checked_new_unit(terms(**changes), today=TODAY)
        assert refused_field_of(failure) == field

    def test_a_tag_of_the_wrong_form_says_what_a_tag_looks_like(self) -> None:
        with pytest.raises(ValidationFailure, match="TSH-DR-0042") as failure:
            checked_new_unit(terms(asset_tag="drill 42"), today=TODAY)
        assert failure.value.rule == "BR-34"


class TestEditing:
    """The paperwork changes and the tag, the model, the branch and the status stay."""

    def test_new_paperwork_keeps_everything_else_of_the_unit(self) -> None:
        unit = registered(
            checked_new_unit(terms(), today=TODAY),
            unit_id=uuid4(),
            product_model_id=uuid4(),
            branch_id=uuid4(),
        )
        new = details(
            serial_number=None,
            condition_grade=ConditionGrade.C,
            hour_meter_reading=None,
            notes=None,
        )
        edited = unit.with_details(new)
        assert edited.details == new
        assert replace(edited.unit, condition_grade=ConditionGrade.A, hour_meter_reading=120) == (
            unit.unit
        )
        assert (edited.acquired_on, edited.acquisition_cost) == (
            unit.acquired_on,
            unit.acquisition_cost,
        )

    def test_the_largest_reading_the_column_holds_is_accepted(self) -> None:
        checked = checked_details(details(hour_meter_reading=LARGEST_METER_READING))
        assert checked.hour_meter_reading == LARGEST_METER_READING

    def test_paperwork_that_breaks_a_rule_is_refused_naming_it(self) -> None:
        with pytest.raises(ValidationFailure) as failure:
            checked_details(details(hour_meter_reading=-5))
        assert refused_field_of(failure) == HOUR_METER_READING
