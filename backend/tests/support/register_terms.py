"""A unit of the register as the domain holds it, for the tests of the register's use cases.

A test starts from a store that holds a trading branch, a model and one unit
of it on the shelf, and changes the one thing it is about, so a refusal can
only come from that. The paperwork keeps every rule.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Final
from uuid import uuid4

import pytest

from app.application.refusal import refused_parameter_of
from app.domain.asset_register import NewUnitTerms, RegisteredUnit, UnitDetails, registered
from app.domain.enums import AssetStatus, ConditionGrade
from app.domain.errors import ValidationFailure
from tests.support.memory_register import RegisterStore, a_branch, a_model

NEW_TAG: Final[str] = "TSH-DR-0099"
HELD_TAG: Final[str] = "TSH-DR-0042"
TODAY: Final[date] = date(2026, 3, 2)
REASON: Final[str] = "Failed its inspection on arrival."


def paperwork(**changes: object) -> UnitDetails:
    """Return paperwork that keeps every rule, with any field changed."""
    kept = UnitDetails(
        serial_number="SN-882731",
        condition_grade=ConditionGrade.A,
        hour_meter_reading=120,
        notes=None,
    )
    return replace(kept, **changes)


def stocked() -> tuple[RegisterStore, RegisteredUnit]:
    """Return a store with a trading branch, a model and one unit on the shelf there."""
    store = RegisterStore()
    branch = a_branch()
    model = a_model()
    store.branches[branch.code] = branch
    store.models[model.id] = model
    unit = registered(
        NewUnitTerms(
            asset_tag=HELD_TAG,
            acquired_on=date(2025, 6, 1),
            acquisition_cost=Decimal("3900.00"),
            details=paperwork(),
        ),
        unit_id=uuid4(),
        product_model_id=model.id,
        branch_id=branch.id,
    )
    on_shelf = replace(unit, unit=replace(unit.unit, status=AssetStatus.AVAILABLE))
    store.keep(on_shelf)
    return store, on_shelf


def refused_name(refusal: pytest.ExceptionInfo[ValidationFailure]) -> str | None:
    """Return the name on the wire of the field a refusal names."""
    return refused_parameter_of(refusal.value)


__all__ = [
    "HELD_TAG",
    "NEW_TAG",
    "REASON",
    "TODAY",
    "paperwork",
    "refused_name",
    "stocked",
]
