"""Record shapes for the Toolshed Hire seed data.

I keep these as frozen dataclasses with no behaviour, so the data modules can be
imported anywhere without touching a database or the file system. Every limit I
mention in a docstring mirrors the column the value is loaded into.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from typing import Literal

type AssetStatusName = Literal[
    "INTAKE", "AVAILABLE", "ON_HIRE", "QUARANTINED", "UNDER_REPAIR", "LOST", "RETIRED"
]
type ConditionGradeName = Literal["A", "B", "C"]

# I repeat the allowed values as tuples so a loader can validate without
# unpacking the type aliases above.
ASSET_STATUS_NAMES: tuple[AssetStatusName, ...] = (
    "INTAKE",
    "AVAILABLE",
    "ON_HIRE",
    "QUARANTINED",
    "UNDER_REPAIR",
    "LOST",
    "RETIRED",
)
CONDITION_GRADE_NAMES: tuple[ConditionGradeName, ...] = ("A", "B", "C")


@dataclass(frozen=True, slots=True)
class BranchSeed:
    """One trading branch.

    I use the code as the natural key, at most four characters. The opening and
    closing times are local South African time.
    """

    code: str
    name: str
    street_address: str
    suburb: str
    city: str
    postal_code: str
    phone: str
    opens_at: time
    closes_at: time


@dataclass(frozen=True, slots=True)
class CategorySeed:
    """One catalogue category.

    I use the code as the natural key, at most sixteen characters. A category
    with a parent code is a child, and a child never has children of its own.
    """

    code: str
    name: str
    slug: str
    description: str
    parent_code: str | None
    sort_order: int


@dataclass(frozen=True, slots=True)
class ProductModelSeed:
    """One catalogue entry that customers shop for.

    I use the SKU as the natural key. The daily and weekly rates exclude VAT,
    and the deposit and the late fee are charged per unit. The tag prefix is the
    letter code inside an asset tag such as TSH-DR-0042. The units per branch
    mapping counts the units a loader still has to generate for each branch
    code, on top of any pinned assets that already exist for the model.
    """

    sku: str
    name: str
    slug: str
    category_code: str
    manufacturer: str
    model_number: str
    short_description: str
    long_description: str | None
    daily_rate: Decimal
    weekly_rate: Decimal
    deposit_amount: Decimal
    late_fee_per_day: Decimal
    replacement_value: Decimal
    min_hire_days: int
    max_hire_days: int
    tag_prefix: str
    units_per_branch: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class PinnedAssetSeed:
    """One physical unit whose tag is already printed and must not change.

    I use the asset tag as the natural key. The SKU and the branch code point at
    a product model and a branch in this package. The hour meter reading is set
    only for powered plant that carries a meter. The retirement date is set
    exactly when the status is RETIRED, which is the rule the asset table checks.
    """

    asset_tag: str
    sku: str
    branch_code: str
    status: AssetStatusName
    condition_grade: ConditionGradeName
    serial_number: str | None
    acquired_on: date
    acquisition_cost: Decimal
    hour_meter_reading: int | None
    retired_on: date | None = None
