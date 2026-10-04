"""Categories and product models as the domain holds them, for the tests of the admin catalogue.

A test starts from a category or a model that keeps every rule and changes
the one field it is about, so a refusal can only come from that field. The
model is priced as the hammer of the design document's rate change is, R280 a
day before the change and R310 after it (US-30).
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Final
from uuid import UUID, uuid4

from app.domain.catalogue_entry_rules import CatalogueEntry, ModelTerms
from app.domain.category_rules import CatalogueCategory, CategoryTerms
from app.domain.enums import UserRole
from app.domain.identity import Actor

ADMINISTRATOR: Final[Actor] = Actor(user_id=uuid4(), role=UserRole.ADMIN)
DAILY_BEFORE: Final[Decimal] = Decimal("280.00")
DAILY_AFTER: Final[Decimal] = Decimal("310.00")
WEEKLY: Final[Decimal] = Decimal("1120.00")
DEPOSIT: Final[Decimal] = Decimal("600.00")
LATE_FEE: Final[Decimal] = Decimal("120.00")
REPLACEMENT: Final[Decimal] = Decimal("4200.00")


def category_terms(**changes: object) -> CategoryTerms:
    """Return the terms of an active top level category, with any field changed."""
    terms = CategoryTerms(
        code="DRILL",
        name="Drilling",
        slug="drilling",
        description="Rotary hammers and drills.",
        parent_category_id=None,
        sort_order=10,
        is_active=True,
    )
    return replace(terms, **changes)


def a_category(**changes: object) -> CatalogueCategory:
    """Return a stored category that keeps every rule, with any field of its terms changed."""
    return CatalogueCategory(id=uuid4(), terms=category_terms(**changes))


def model_terms(category_id: UUID, **changes: object) -> ModelTerms:
    """Return the terms of the rotary hammer at R280 a day, with any field changed."""
    terms = ModelTerms(
        sku="DR-BOSCH-GBH226",
        name="Bosch GBH 2-26 DRE rotary hammer",
        slug="bosch-gbh-2-26-dre-rotary-hammer",
        category_id=category_id,
        manufacturer="Bosch",
        model_number="GBH 2-26 DRE",
        short_description="SDS-plus rotary hammer, 800 W.",
        long_description=None,
        daily_rate=DAILY_BEFORE,
        weekly_rate=WEEKLY,
        deposit_amount=DEPOSIT,
        late_fee_per_day=LATE_FEE,
        replacement_value=REPLACEMENT,
        min_hire_days=1,
        max_hire_days=28,
    )
    return replace(terms, **changes)


def an_entry(category_id: UUID, *, published: bool = True, **changes: object) -> CatalogueEntry:
    """Return a stored product model of a category, with any field of its terms changed."""
    return CatalogueEntry(
        id=uuid4(), terms=model_terms(category_id, **changes), is_published=published
    )


__all__ = [
    "ADMINISTRATOR",
    "DAILY_AFTER",
    "DAILY_BEFORE",
    "WEEKLY",
    "a_category",
    "an_entry",
    "category_terms",
    "model_terms",
]
