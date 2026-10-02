"""Response models for the catalogue, the branches, the availability search and a quote.

Field names on the wire are camelCase, as everywhere else at this boundary.
Three conventions are stated once here, as types, so no response can get one
of them wrong.

Money is a JSON string with two decimals, for example "280.00", and never a
number. A float cannot hold a rand amount exactly, and a client that parses
one has already changed the figure a customer is shown (BR-22).

A percentage is written the same way, for example "15.00".

A date is `YYYY-MM-DD` and a time of day is `HH:MM`.

Nothing here has a field for an asset tag, a serial number or a number of
units. Availability is a boolean for a branch and nothing else (US-07).

`ModelSortParameter` is the sort order as a request spells it. A request can
only name a member, and the member is mapped to the application's own
enumeration, which the query object maps to columns (C-28).
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from enum import Enum
from typing import Annotated, Final

from pydantic import ConfigDict, Field, PlainSerializer

from app.api.schemas import CamelModel, ProblemDetail
from app.application.catalogue.read_models import ModelSort
from app.domain.policies.pricing import PricingBasis

MONEY_FORMAT: Final[str] = "{:.2f}"
CLOCK_TIME_FORMAT: Final[str] = "%H:%M"

# How the two error answers of these routes are described in the OpenAPI
# document, so a generated client knows a refusal is a problem document.
REFUSED_QUERY_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "A query parameter was refused. `errors.fields` names it.",
}
UNKNOWN_MODEL_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "No published model carries this slug.",
}


def _money_text(amount: Decimal) -> str:
    """Write an amount with exactly two decimals."""
    return MONEY_FORMAT.format(amount)


def _clock_text(moment: time) -> str:
    """Write a time of day as hours and minutes."""
    return moment.strftime(CLOCK_TIME_FORMAT)


# `Money` here is how an amount is written on the wire. The value object of
# the same name in the domain is what the amount is worked out with.
Money = Annotated[Decimal, PlainSerializer(_money_text, return_type=str)]
Percentage = Annotated[Decimal, PlainSerializer(_money_text, return_type=str)]
ClockTime = Annotated[time, PlainSerializer(_clock_text, return_type=str)]


class ModelSortParameter(str, Enum):
    """The sort orders a request may name."""

    NAME = "name"
    DAILY_RATE_ASC = "dailyRateAsc"
    DAILY_RATE_DESC = "dailyRateDesc"


# Explicit and total, so a sort order cannot be added on one side only.
SORT_FROM_WIRE: Final[dict[ModelSortParameter, ModelSort]] = {
    ModelSortParameter.NAME: ModelSort.NAME,
    ModelSortParameter.DAILY_RATE_ASC: ModelSort.DAILY_RATE_ASC,
    ModelSortParameter.DAILY_RATE_DESC: ModelSort.DAILY_RATE_DESC,
}


class QuoteBasis(str, Enum):
    """Which of the two totals a quote charged for one unit, as a response spells it."""

    WEEKLY = "weekly"
    DAILY = "daily"


# Explicit and total, for the same reason as the sort order.
BASIS_TO_WIRE: Final[dict[PricingBasis, QuoteBasis]] = {
    PricingBasis.WEEKLY: QuoteBasis.WEEKLY,
    PricingBasis.DAILY: QuoteBasis.DAILY,
}


class BranchResponse(CamelModel):
    """One trading branch."""

    code: str
    name: str
    suburb: str
    city: str
    phone: str
    opens_at: ClockTime = Field(serialization_alias="opensAt")
    closes_at: ClockTime = Field(serialization_alias="closesAt")


class BranchListResponse(CamelModel):
    """The active branches, ordered by name."""

    items: list[BranchResponse]


class CategoryResponse(CamelModel):
    """One active category. `parentCode` is null for a top level category."""

    code: str
    name: str
    slug: str
    description: str
    parent_code: str | None = Field(serialization_alias="parentCode")
    sort_order: int = Field(serialization_alias="sortOrder")
    model_count: int = Field(serialization_alias="modelCount")

    # pydantic reserves the `model_` prefix for its own methods. `model_count`
    # collides with nothing, so the reservation is lifted for this class.
    model_config = ConfigDict(protected_namespaces=())


class CategoryListResponse(CamelModel):
    """The active categories, each parent followed by its children."""

    items: list[CategoryResponse]


class ModelSummaryResponse(CamelModel):
    """A published catalogue entry as it appears in a list."""

    sku: str
    slug: str
    name: str
    manufacturer: str
    model_number: str = Field(serialization_alias="modelNumber")
    category_code: str = Field(serialization_alias="categoryCode")
    category_name: str = Field(serialization_alias="categoryName")
    short_description: str = Field(serialization_alias="shortDescription")
    daily_rate: Money = Field(serialization_alias="dailyRate")
    weekly_rate: Money = Field(serialization_alias="weeklyRate")
    deposit_amount: Money = Field(serialization_alias="depositAmount")
    min_hire_days: int = Field(serialization_alias="minHireDays")
    max_hire_days: int = Field(serialization_alias="maxHireDays")
    image_path: str | None = Field(serialization_alias="imagePath")

    # `model_number` is the documented name and collides with nothing.
    model_config = ConfigDict(protected_namespaces=())


class ModelDetailResponse(ModelSummaryResponse):
    """A published catalogue entry as its own page shows it."""

    long_description: str | None = Field(serialization_alias="longDescription")
    late_fee_per_day: Money = Field(serialization_alias="lateFeePerDay")


class ModelPageResponse(CamelModel):
    """One page of published models."""

    items: list[ModelSummaryResponse]
    page: int
    page_size: int = Field(serialization_alias="pageSize")
    total: int


class BranchAvailabilityResponse(CamelModel):
    """Whether one branch can supply a model for the whole period asked about."""

    branch_code: str = Field(serialization_alias="branchCode")
    branch_name: str = Field(serialization_alias="branchName")
    available: bool


class ModelAvailabilityRowResponse(CamelModel):
    """One model of an availability search, with an answer from every branch."""

    model: ModelSummaryResponse
    branches: list[BranchAvailabilityResponse]


class AvailabilityPageResponse(CamelModel):
    """One page of an availability search.

    `to` is the day the equipment comes back. It is exclusive, so a unit is
    free again on that day.
    """

    from_date: date = Field(serialization_alias="from")
    to_date: date = Field(serialization_alias="to")
    hire_days: int = Field(serialization_alias="hireDays")
    items: list[ModelAvailabilityRowResponse]
    page: int
    page_size: int = Field(serialization_alias="pageSize")
    total: int


class ModelAvailabilityResponse(CamelModel):
    """Where one model is free for a period, in the quantity asked for."""

    from_date: date = Field(serialization_alias="from")
    to_date: date = Field(serialization_alias="to")
    hire_days: int = Field(serialization_alias="hireDays")
    quantity: int
    branches: list[BranchAvailabilityResponse]


class UnitQuoteResponse(CamelModel):
    """What one unit costs for the period, and how that was arrived at.

    `basis` is `weekly` when the complete weeks at the weekly rate and the
    days left over at the daily rate came to less than every day at the daily
    rate, and `daily` otherwise.
    """

    daily_rate: Money = Field(serialization_alias="dailyRate")
    weekly_rate: Money = Field(serialization_alias="weeklyRate")
    whole_weeks: int = Field(serialization_alias="wholeWeeks")
    remainder_days: int = Field(serialization_alias="remainderDays")
    basis: QuoteBasis
    amount_ex_vat: Money = Field(serialization_alias="amountExVat")


class QuoteResponse(CamelModel):
    """What a hire will cost.

    `totalIncVat` is the hire charge. The deposit is not in it, because a
    deposit is held and returned and not charged. `vatAmount` is worked out on
    the subtotal after the discount.
    """

    from_date: date = Field(serialization_alias="from")
    to_date: date = Field(serialization_alias="to")
    hire_days: int = Field(serialization_alias="hireDays")
    quantity: int
    per_unit: UnitQuoteResponse = Field(serialization_alias="perUnit")
    subtotal_ex_vat: Money = Field(serialization_alias="subtotalExVat")
    discount_percent: Percentage = Field(serialization_alias="discountPercent")
    discount_amount: Money = Field(serialization_alias="discountAmount")
    vat_rate: Percentage = Field(serialization_alias="vatRate")
    vat_amount: Money = Field(serialization_alias="vatAmount")
    total_inc_vat: Money = Field(serialization_alias="totalIncVat")
    deposit_per_unit: Money = Field(serialization_alias="depositPerUnit")
    deposit_total: Money = Field(serialization_alias="depositTotal")
    late_fee_per_day: Money = Field(serialization_alias="lateFeePerDay")
