"""The rules a product model of the catalogue is held to when an administrator creates or edits it.

A product model, the catalogue entry, carries the rates, the deposit, the late
fee and the replacement value that every booking copies when it is made
(BR-20). These are set once for all three branches (FR-22), so a mistake here
reaches every new booking at once, and the rules below are what stops one.

1. Every amount is zero or more, in whole cents, and fits its column (BR-22).
2. The weekly rate is at most seven days at the daily rate. The pricing
   policy charges whichever of the two totals is lower (BR-21), so a weekly
   rate above that would never be charged and would only mislead. What seven
   days cost is asked of the policy, which is where a rate is multiplied by
   days.
3. The shortest hire is at least one day, the longest at most the 28 days any
   hire may last (BR-03), and the shortest is never longer than the longest.
4. A SKU is of the form of a code and a slug of the form of a slug, as
   `app.domain.catalogue_forms` says, and text fits its column.
5. A model is only classified under an active category.

Creating a model and editing one both go through `checked_model_terms` and
`ensure_category_may_classify`, so the rules cannot differ between them. A
change of a rate never reaches an existing booking or rental, because each of
them holds its own copy of the figures.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final
from uuid import UUID

from app.domain.catalogue_forms import (
    amount_held,
    code_text,
    field_refusal,
    optional_text,
    required_text,
    slug_text,
)
from app.domain.category_rules import CatalogueCategory
from app.domain.money import Money
from app.domain.period import MAXIMUM_HIRE_DAYS, MINIMUM_HIRE_DAYS, PERIOD_BOUNDS_RULE
from app.domain.policies.standard_pricing import StandardPricingPolicy

SKU: Final[str] = "sku"
NAME: Final[str] = "name"
SLUG: Final[str] = "slug"
CATEGORY_ID: Final[str] = "category_id"
MANUFACTURER: Final[str] = "manufacturer"
MODEL_NUMBER: Final[str] = "model_number"
SHORT_DESCRIPTION: Final[str] = "short_description"
LONG_DESCRIPTION: Final[str] = "long_description"
DAILY_RATE: Final[str] = "daily_rate"
WEEKLY_RATE: Final[str] = "weekly_rate"
DEPOSIT_AMOUNT: Final[str] = "deposit_amount"
LATE_FEE_PER_DAY: Final[str] = "late_fee_per_day"
REPLACEMENT_VALUE: Final[str] = "replacement_value"
MIN_HIRE_DAYS: Final[str] = "min_hire_days"
MAX_HIRE_DAYS: Final[str] = "max_hire_days"
IS_PUBLISHED: Final[str] = "is_published"

# The widths of the columns in the design document.
SKU_MAX_LENGTH: Final[int] = 24
NAME_MAX_LENGTH: Final[int] = 120
SLUG_MAX_LENGTH: Final[int] = 140
MANUFACTURER_MAX_LENGTH: Final[int] = 80
MODEL_NUMBER_MAX_LENGTH: Final[int] = 60
SHORT_DESCRIPTION_MAX_LENGTH: Final[int] = 300

PRICING_RULE: Final[str] = "BR-21"
WEEKLY_RATE_MESSAGE: Final[str] = (
    "The weekly rate cannot be more than seven days at the daily rate."
)
SHORTEST_HIRE_MESSAGE: Final[str] = f"A hire is at least {MINIMUM_HIRE_DAYS} day."
LONGEST_HIRE_MESSAGE: Final[str] = f"A hire can be at most {MAXIMUM_HIRE_DAYS} days."
HIRE_DAYS_ORDER_MESSAGE: Final[str] = "The shortest hire cannot be longer than the longest hire."
INACTIVE_CATEGORY_MESSAGE: Final[str] = (
    "That category has been switched off. Choose an active category."
)


@dataclass(frozen=True, slots=True)
class ModelTerms:
    """What an administrator decides about a product model.

    Attributes:
        sku: The stock keeping unit, for example `DR-BOSCH-GBH226`. It never
            changes once the model exists.
        name: The display name.
        slug: The name it carries in an address.
        category_id: The category that classifies it.
        manufacturer: Who makes it.
        model_number: The manufacturer's own model number.
        short_description: One or two sentences for a list.
        long_description: The full description, or None.
        daily_rate: The rate for one day, excluding VAT.
        weekly_rate: The rate for each complete seven days, excluding VAT.
        deposit_amount: The deposit held for one unit.
        late_fee_per_day: The fee for each day a unit comes back late.
        replacement_value: The cap on damage recovery for one unit (BR-39).
        min_hire_days: The shortest hire the model may be booked for.
        max_hire_days: The longest hire the model may be booked for (BR-03).

    """

    sku: str
    name: str
    slug: str
    category_id: UUID
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


@dataclass(frozen=True, slots=True)
class CatalogueEntry:
    """A stored product model.

    Attributes:
        id: The product model key.
        terms: What it is, how it is priced and how long it may be hired for.
        is_published: True when visitors see it and may book it.

    """

    id: UUID
    terms: ModelTerms
    is_published: bool


def checked_model_terms(terms: ModelTerms) -> ModelTerms:
    """Return the terms trimmed and in whole cents, or refuse the first field that breaks a rule.

    Raises:
        ValidationFailure: Naming the field.

    """
    checked = ModelTerms(
        sku=code_text(SKU, terms.sku, SKU_MAX_LENGTH),
        name=required_text(NAME, terms.name, NAME_MAX_LENGTH),
        slug=slug_text(SLUG, terms.slug, SLUG_MAX_LENGTH),
        category_id=terms.category_id,
        manufacturer=required_text(MANUFACTURER, terms.manufacturer, MANUFACTURER_MAX_LENGTH),
        model_number=required_text(MODEL_NUMBER, terms.model_number, MODEL_NUMBER_MAX_LENGTH),
        short_description=required_text(
            SHORT_DESCRIPTION, terms.short_description, SHORT_DESCRIPTION_MAX_LENGTH
        ),
        long_description=optional_text(LONG_DESCRIPTION, terms.long_description, None),
        daily_rate=amount_held(DAILY_RATE, terms.daily_rate),
        weekly_rate=amount_held(WEEKLY_RATE, terms.weekly_rate),
        deposit_amount=amount_held(DEPOSIT_AMOUNT, terms.deposit_amount),
        late_fee_per_day=amount_held(LATE_FEE_PER_DAY, terms.late_fee_per_day),
        replacement_value=amount_held(REPLACEMENT_VALUE, terms.replacement_value),
        min_hire_days=terms.min_hire_days,
        max_hire_days=terms.max_hire_days,
    )
    _ensure_weekly_rate_may_be_charged(checked)
    _ensure_hire_days_in_order(checked)
    return checked


def ensure_category_may_classify(category: CatalogueCategory) -> None:
    """Refuse a category that has been switched off.

    Raises:
        ValidationFailure: Naming `category_id`.

    """
    if not category.terms.is_active:
        raise field_refusal(CATEGORY_ID, INACTIVE_CATEGORY_MESSAGE)


def _ensure_weekly_rate_may_be_charged(terms: ModelTerms) -> None:
    """Refuse a weekly rate the pricing policy would never charge (BR-21)."""
    most_a_week_may_cost = StandardPricingPolicy.week_at_the_daily_rate(Money(terms.daily_rate))
    if Money(terms.weekly_rate) > most_a_week_may_cost:
        raise field_refusal(WEEKLY_RATE, WEEKLY_RATE_MESSAGE, rule=PRICING_RULE)


def _ensure_hire_days_in_order(terms: ModelTerms) -> None:
    """Refuse hire limits outside the limits of any hire, or the wrong way round (BR-03)."""
    if terms.min_hire_days < MINIMUM_HIRE_DAYS:
        raise field_refusal(MIN_HIRE_DAYS, SHORTEST_HIRE_MESSAGE, rule=PERIOD_BOUNDS_RULE)
    if terms.max_hire_days > MAXIMUM_HIRE_DAYS:
        raise field_refusal(MAX_HIRE_DAYS, LONGEST_HIRE_MESSAGE, rule=PERIOD_BOUNDS_RULE)
    if terms.min_hire_days > terms.max_hire_days:
        raise field_refusal(MIN_HIRE_DAYS, HIRE_DAYS_ORDER_MESSAGE, rule=PERIOD_BOUNDS_RULE)
