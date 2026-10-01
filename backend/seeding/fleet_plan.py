"""Work out every unit of the fleet and its tag, without touching a database.

The plan is a pure function of the seed data. The pinned units keep the tags
that are already painted on them. Every other unit is numbered upward within
its tag prefix, taking the product models in SKU order and, inside a model, the
branches in the order the data lists them, and stepping over any number a
pinned unit already carries. The same data therefore always gives the same
tags, which is what lets a second run match every unit it wrote the first time.

One consequence is worth knowing before the data is edited. A model added
later can sort ahead of existing ones and shift the numbers after it. A tag is
painted on a machine, so stock bought after the first load belongs in the
pinned list with the tag it was given, not in a unit count.
"""

from __future__ import annotations

import re
import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Final

from app.domain.enums import AssetStatus, ConditionGrade
from seed_data.types import PinnedAssetSeed, ProductModelSeed
from seeding.errors import SeedDataError

TAG_COMPANY_CODE: Final[str] = "TSH"
TAG_NUMBER_DIGITS: Final[int] = 4
FIRST_TAG_NUMBER: Final[int] = 1
LAST_TAG_NUMBER: Final[int] = 10**TAG_NUMBER_DIGITS - 1
TAG_PATTERN: Final[re.Pattern[str]] = re.compile(
    rf"{TAG_COMPANY_CODE}-(?P<prefix>[A-Z]{{2,4}})-(?P<number>\d{{{TAG_NUMBER_DIGITS}}})"
)

# A generated unit gets a purchase date spread across these years. The offset
# comes from a checksum of its tag, so it looks scattered and is the same on
# every run. The built in hash() is salted per process and would not be.
GENERATED_ACQUISITION_START: Final[date] = date(2022, 1, 17)
GENERATED_ACQUISITION_SPAN_DAYS: Final[int] = 1400
# A unit bought from this day on is still grade A. An older one has seen
# enough hires to be grade B.
GRADE_A_ACQUIRED_FROM: Final[date] = date(2024, 1, 1)


@dataclass(frozen=True, slots=True)
class PlannedAsset:
    """One unit the loader has to make sure exists, pinned or generated."""

    asset_tag: str
    sku: str
    branch_code: str
    status: AssetStatus
    condition_grade: ConditionGrade
    serial_number: str | None
    acquired_on: date
    acquisition_cost: Decimal
    hour_meter_reading: int | None
    retired_on: date | None
    is_pinned: bool


def format_tag(prefix: str, number: int) -> str:
    """Return the asset tag for a prefix and a number, for example TSH-DR-0042."""
    return f"{TAG_COMPANY_CODE}-{prefix}-{number:0{TAG_NUMBER_DIGITS}d}"


def parse_tag(asset_tag: str) -> tuple[str, int]:
    """Split an asset tag into its prefix and its number.

    Raises:
        SeedDataError: If the tag is not the company code, a prefix of two to
            four capitals and four digits.

    """
    match = TAG_PATTERN.fullmatch(asset_tag)
    if match is None:
        raise SeedDataError(
            f"Asset tag {asset_tag!r} is not in the form {format_tag('DR', 42)}, which is "
            f"{TAG_COMPANY_CODE}, a prefix of two to four capitals and {TAG_NUMBER_DIGITS} digits."
        )
    return match.group("prefix"), int(match.group("number"))


def plan_fleet(
    models: Sequence[ProductModelSeed],
    pinned: Sequence[PinnedAssetSeed],
    branch_order: Sequence[str],
) -> tuple[PlannedAsset, ...]:
    """Return every unit of the fleet, the pinned ones first.

    Args:
        models: The product models, in any order. They are sorted by SKU here.
        pinned: The units whose tags are fixed.
        branch_order: The branch codes in the order units are numbered.

    Raises:
        SeedDataError: If a pinned unit names an unknown model or branch, a tag
            is malformed, repeated or carries the wrong prefix, a unit count is
            negative or names an unknown branch, or a prefix runs out of numbers.

    """
    models_by_sku = _index_models(models)
    planned_pinned = _plan_pinned(pinned, models_by_sku, branch_order)
    taken: dict[str, set[int]] = {}
    for unit in planned_pinned:
        prefix, number = parse_tag(unit.asset_tag)
        taken.setdefault(prefix, set()).add(number)
    planned_generated = _plan_generated(models_by_sku, branch_order, taken)
    return (*planned_pinned, *planned_generated)


def _index_models(models: Sequence[ProductModelSeed]) -> dict[str, ProductModelSeed]:
    """Return the models keyed by SKU, refusing a SKU that appears twice."""
    by_sku: dict[str, ProductModelSeed] = {}
    for model in models:
        if model.sku in by_sku:
            raise SeedDataError(f"Product model SKU {model.sku} appears more than once.")
        by_sku[model.sku] = model
    return by_sku


def _plan_pinned(
    pinned: Sequence[PinnedAssetSeed],
    models_by_sku: dict[str, ProductModelSeed],
    branch_order: Sequence[str],
) -> list[PlannedAsset]:
    """Return the pinned units as planned assets, each one checked against the data."""
    planned: list[PlannedAsset] = []
    seen: set[str] = set()
    for unit in pinned:
        model = models_by_sku.get(unit.sku)
        if model is None:
            raise SeedDataError(
                f"Pinned asset {unit.asset_tag} names SKU {unit.sku!r}, which is not a "
                "product model in the seed data."
            )
        if unit.branch_code not in branch_order:
            raise SeedDataError(
                f"Pinned asset {unit.asset_tag} names branch {unit.branch_code!r}. The known "
                f"branches are {list(branch_order)}."
            )
        prefix, _number = parse_tag(unit.asset_tag)
        if prefix != model.tag_prefix:
            raise SeedDataError(
                f"Pinned asset {unit.asset_tag} carries prefix {prefix}, but its model "
                f"{model.sku} uses {model.tag_prefix}."
            )
        if unit.asset_tag in seen:
            raise SeedDataError(f"Pinned asset tag {unit.asset_tag} appears more than once.")
        seen.add(unit.asset_tag)
        planned.append(_pinned_as_planned(unit))
    return planned


def _pinned_as_planned(unit: PinnedAssetSeed) -> PlannedAsset:
    """Convert one pinned record, turning its status and grade names into enums."""
    try:
        status = AssetStatus(unit.status)
        grade = ConditionGrade(unit.condition_grade)
    except ValueError as exc:
        raise SeedDataError(
            f"Pinned asset {unit.asset_tag} has status {unit.status!r} and grade "
            f"{unit.condition_grade!r}, and one of them is not a value the schema stores."
        ) from exc
    if (unit.retired_on is not None) != (status is AssetStatus.RETIRED):
        raise SeedDataError(
            f"Pinned asset {unit.asset_tag} has status {status.value} and retirement date "
            f"{unit.retired_on}. The date is set exactly when the status is RETIRED."
        )
    return PlannedAsset(
        asset_tag=unit.asset_tag,
        sku=unit.sku,
        branch_code=unit.branch_code,
        status=status,
        condition_grade=grade,
        serial_number=unit.serial_number,
        acquired_on=unit.acquired_on,
        acquisition_cost=unit.acquisition_cost,
        hour_meter_reading=unit.hour_meter_reading,
        retired_on=unit.retired_on,
        is_pinned=True,
    )


def _plan_generated(
    models_by_sku: dict[str, ProductModelSeed],
    branch_order: Sequence[str],
    taken: dict[str, set[int]],
) -> list[PlannedAsset]:
    """Return the units each model still needs, numbered in SKU order and then branch order."""
    planned: list[PlannedAsset] = []
    next_number: dict[str, int] = {}
    for sku in sorted(models_by_sku):
        model = models_by_sku[sku]
        _check_unit_counts(model, branch_order)
        for branch_code in branch_order:
            for _unit in range(model.units_per_branch.get(branch_code, 0)):
                number = _next_free_number(model.tag_prefix, next_number, taken)
                planned.append(_generated_unit(model, branch_code, number))
    return planned


def _check_unit_counts(model: ProductModelSeed, branch_order: Sequence[str]) -> None:
    """Refuse a unit count for an unknown branch or below zero."""
    for branch_code, count in model.units_per_branch.items():
        if branch_code not in branch_order:
            raise SeedDataError(
                f"Product model {model.sku} counts units for branch {branch_code!r}. The "
                f"known branches are {list(branch_order)}."
            )
        if count < 0:
            raise SeedDataError(
                f"Product model {model.sku} counts {count} units at {branch_code}. A count "
                "cannot be negative."
            )


def _next_free_number(prefix: str, next_number: dict[str, int], taken: dict[str, set[int]]) -> int:
    """Return the lowest number not yet used for a prefix and move the counter past it."""
    number = next_number.get(prefix, FIRST_TAG_NUMBER)
    pinned_numbers = taken.get(prefix, set())
    while number in pinned_numbers:
        number += 1
    if number > LAST_TAG_NUMBER:
        raise SeedDataError(
            f"Tag prefix {prefix} has run out of numbers. A tag holds {TAG_NUMBER_DIGITS} "
            f"digits, so the last one is {format_tag(prefix, LAST_TAG_NUMBER)}."
        )
    next_number[prefix] = number + 1
    return number


def _generated_unit(model: ProductModelSeed, branch_code: str, number: int) -> PlannedAsset:
    """Return one generated unit, available, with a date and a grade fixed by its tag."""
    asset_tag = format_tag(model.tag_prefix, number)
    offset_days = zlib.crc32(asset_tag.encode("ascii")) % GENERATED_ACQUISITION_SPAN_DAYS
    acquired_on = GENERATED_ACQUISITION_START + timedelta(days=offset_days)
    is_recent = acquired_on >= GRADE_A_ACQUIRED_FROM
    return PlannedAsset(
        asset_tag=asset_tag,
        sku=model.sku,
        branch_code=branch_code,
        status=AssetStatus.AVAILABLE,
        condition_grade=ConditionGrade.A if is_recent else ConditionGrade.B,
        serial_number=None,
        acquired_on=acquired_on,
        # I have no purchase records for these units, so each one is carried at
        # what it would cost to replace.
        acquisition_cost=model.replacement_value,
        hour_meter_reading=None,
        retired_on=None,
        is_pinned=False,
    )
