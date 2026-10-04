"""What the administrator's catalogue is read with and what it hands back (FR-22, US-30).

These are small frozen dataclasses with no behaviour beyond checking
themselves. The SQL that fills them lives in the infrastructure layer, behind
the `AdminCatalogueQuery` port, and returns these and never a table row.

The administrator sees what a visitor never does, which is the categories that
were switched off, the models that are not published and how many units the
fleet holds of each model. Money stays `Decimal` all the way to the HTTP
boundary, which writes it as a string with two decimals (BR-22).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final
from uuid import UUID

from app.application.admin_lists import (
    FIRST_PAGE,
    MAXIMUM_PAGE,
    MAXIMUM_PAGE_SIZE,
    MINIMUM_PAGE_SIZE,
    offset_of,
)

# The list of categories is answered whole unless a page is asked for, so its
# page is the largest a list may have.
CATEGORY_PAGE_SIZE: Final[int] = MAXIMUM_PAGE_SIZE


def _ensure_page(page: int, page_size: int, subject: str) -> None:
    """Refuse a page no caller should be able to build.

    The HTTP boundary holds the same limits and answers a 422. This is the
    second line, so nothing inside the system can hand a query object a
    negative offset or an unbounded page.

    Raises:
        ValueError: If the page or its size is out of range.

    """
    if not FIRST_PAGE <= page <= MAXIMUM_PAGE:
        raise ValueError(
            f"Attempted to list {subject} for page {page}. A page is between {FIRST_PAGE} and "
            f"{MAXIMUM_PAGE}."
        )
    if not MINIMUM_PAGE_SIZE <= page_size <= MAXIMUM_PAGE_SIZE:
        raise ValueError(
            f"Attempted to list {subject} with a page size of {page_size}. A page holds between "
            f"{MINIMUM_PAGE_SIZE} and {MAXIMUM_PAGE_SIZE}."
        )


@dataclass(frozen=True, slots=True)
class AdminCategorySearch:
    """Which page of the categories to list, parents first."""

    page: int = FIRST_PAGE
    page_size: int = CATEGORY_PAGE_SIZE

    def __post_init__(self) -> None:
        """Refuse a page out of range.

        Raises:
            ValueError: If the page or its size is out of range.

        """
        _ensure_page(self.page, self.page_size, "categories")

    @property
    def offset(self) -> int:
        """Return how many categories come before the first one on the page."""
        return offset_of(self.page, self.page_size)


@dataclass(frozen=True, slots=True)
class AdminModelSearch:
    """Which product models to list, published or not, and which page of them.

    Attributes:
        text: Free text matched without regard to case against the SKU, the
            name, the manufacturer and the model number, or None.
        category_id: Only the models of this category, or None for every one.
        published: True for the published models only, False for the hidden
            ones only, None for both.
        page: The page, counted from one.
        page_size: How many models a page holds.

    """

    text: str | None
    category_id: UUID | None
    published: bool | None
    page: int
    page_size: int

    def __post_init__(self) -> None:
        """Refuse a page out of range.

        Raises:
            ValueError: If the page or its size is out of range.

        """
        _ensure_page(self.page, self.page_size, "product models")

    @property
    def offset(self) -> int:
        """Return how many models come before the first one on the page."""
        return offset_of(self.page, self.page_size)


@dataclass(frozen=True, slots=True)
class AdminCategoryEntry:
    """One category as the administrator sees it, active or not.

    Attributes:
        id: The category key.
        code: The short code.
        name: The display name.
        slug: The name it carries in an address.
        description: What it holds, or None.
        parent_category_id: The category it sits under, or None at the top.
        parent_name: The name of that category, or None.
        sort_order: Where it sorts among its siblings.
        is_active: False when it has been switched off.
        model_count: The product models it classifies itself, published or not.

    """

    id: UUID
    code: str
    name: str
    slug: str
    description: str | None
    parent_category_id: UUID | None
    parent_name: str | None
    sort_order: int
    is_active: bool
    model_count: int


@dataclass(frozen=True, slots=True)
class AdminCategoryPage:
    """One page of the categories, each parent followed by its children."""

    items: tuple[AdminCategoryEntry, ...]
    page: int
    page_size: int
    total: int


@dataclass(frozen=True, slots=True)
class AdminModelEntry:
    """One product model as the administrator sees it, published or not.

    Attributes:
        id: The product model key.
        sku: The stock keeping unit.
        name: The display name.
        slug: The name it carries in an address.
        category_id: The category that classifies it.
        category_name: That category's name.
        manufacturer: Who makes it.
        model_number: The manufacturer's own model number.
        short_description: One or two sentences for a list.
        long_description: The full description, or None.
        daily_rate: The rate for one day, excluding VAT.
        weekly_rate: The rate for each complete seven days, excluding VAT.
        deposit_amount: The deposit held for one unit.
        late_fee_per_day: The fee for each day a unit comes back late.
        replacement_value: The cap on damage recovery for one unit.
        min_hire_days: The shortest hire it may be booked for.
        max_hire_days: The longest hire it may be booked for.
        is_published: True when visitors see it.
        asset_count: The units of the fleet that realise it, whatever their status.
        updated_at: When it was last changed.

    """

    id: UUID
    sku: str
    name: str
    slug: str
    category_id: UUID
    category_name: str
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
    is_published: bool
    asset_count: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AdminModelPage:
    """One page of the product models, by name, and how many match across every page."""

    items: tuple[AdminModelEntry, ...]
    page: int
    page_size: int
    total: int
