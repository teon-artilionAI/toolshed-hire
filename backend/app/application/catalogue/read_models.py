"""What the catalogue read side is asked with and what it hands back.

These are small frozen dataclasses with no behaviour beyond checking
themselves. The SQL that fills them lives in the infrastructure layer, behind
the `CatalogueQuery` port, so nothing here knows how a row is stored.

Nothing in this module carries an asset tag, a serial number or a count of
units. A customer never learns stock (US-07), and a type that has no field for
it cannot leak it.

Money stays `Decimal` all the way to the HTTP boundary, which writes it as a
string with two decimals (BR-22).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Final

FIRST_PAGE: Final[int] = 1
# Far beyond the last page of any catalogue this business will hold. The bound
# exists so the offset of a page can never overflow what the database accepts.
MAXIMUM_PAGE: Final[int] = 10_000
MINIMUM_PAGE_SIZE: Final[int] = 1
MAXIMUM_PAGE_SIZE: Final[int] = 50
DEFAULT_PAGE_SIZE: Final[int] = 24
MINIMUM_SEARCH_LENGTH: Final[int] = 2
# The width of the widest column the text search reads, the model name. A
# longer search text cannot match anything.
MAXIMUM_SEARCH_LENGTH: Final[int] = 120


class ModelSort(str, Enum):
    """The orders a list of models can be asked for.

    This is the server side enumeration behind control C-28. A request names
    one of these members and the query object maps the member to columns. No
    part of a request is ever placed in an ORDER BY clause.
    """

    NAME = "NAME"
    DAILY_RATE_ASC = "DAILY_RATE_ASC"
    DAILY_RATE_DESC = "DAILY_RATE_DESC"


@dataclass(frozen=True, slots=True)
class ModelSearch:
    """Which published models to list, in what order, and which page of them.

    Attributes:
        category_slug: The slug of a category, or None for every category. A
            parent category includes the models of its children.
        text: Free text matched without regard to case against the name, the
            manufacturer and the model number, or None for no text filter.
        sort: The order of the result.
        page: The page wanted, counted from one.
        page_size: How many models a page holds.

    """

    category_slug: str | None = None
    text: str | None = None
    sort: ModelSort = ModelSort.NAME
    page: int = FIRST_PAGE
    page_size: int = DEFAULT_PAGE_SIZE

    def __post_init__(self) -> None:
        """Refuse a search no caller should be able to build.

        The HTTP boundary validates the same limits and answers a visitor with
        a 422. This is the second line, so a caller inside the system cannot
        hand the query object a negative offset or an unbounded page.

        Raises:
            ValueError: If the page, the page size or the text is out of range.

        """
        if not FIRST_PAGE <= self.page <= MAXIMUM_PAGE:
            raise ValueError(
                f"Attempted to search the catalogue for page {self.page}. A page is "
                f"between {FIRST_PAGE} and {MAXIMUM_PAGE}."
            )
        if not MINIMUM_PAGE_SIZE <= self.page_size <= MAXIMUM_PAGE_SIZE:
            raise ValueError(
                f"Attempted to search the catalogue with a page size of {self.page_size}. "
                f"A page holds between {MINIMUM_PAGE_SIZE} and {MAXIMUM_PAGE_SIZE} models."
            )
        if self.text is not None and not (
            MINIMUM_SEARCH_LENGTH <= len(self.text) <= MAXIMUM_SEARCH_LENGTH
        ):
            raise ValueError(
                f"Attempted to search the catalogue with a text of {len(self.text)} "
                f"characters. A search text is between {MINIMUM_SEARCH_LENGTH} and "
                f"{MAXIMUM_SEARCH_LENGTH} characters."
            )

    @property
    def offset(self) -> int:
        """Return how many models come before the page wanted."""
        return (self.page - FIRST_PAGE) * self.page_size


@dataclass(frozen=True, slots=True)
class CategoryEntry:
    """One active category, with how many published models a visitor finds in it.

    Attributes:
        code: The short code of the category.
        name: The display name.
        slug: The name the category carries in an address.
        description: What the category holds. Empty when none was written.
        parent_code: The code of the parent, or None for a top level category.
        sort_order: Where the category sorts among its siblings.
        model_count: The published models in the category. For a parent this
            includes the models of its children.

    """

    code: str
    name: str
    slug: str
    description: str
    parent_code: str | None
    sort_order: int
    model_count: int


@dataclass(frozen=True, slots=True)
class ModelSummary:
    """A published catalogue entry as it appears in a list.

    Attributes:
        sku: The stock keeping unit.
        slug: The name the model carries in an address.
        name: The display name.
        manufacturer: Who makes it.
        model_number: The manufacturer's own model number.
        category_code: The code of the category that classifies it.
        category_name: The display name of that category.
        short_description: One or two sentences for a list.
        daily_rate: The rate for one day, excluding VAT.
        weekly_rate: The rate for each complete seven days, excluding VAT.
        deposit_amount: The deposit held for one unit.
        min_hire_days: The shortest hire the model may be booked for.
        max_hire_days: The longest hire the model may be booked for.
        image_path: Where the photograph is, or None when there is none.

    """

    sku: str
    slug: str
    name: str
    manufacturer: str
    model_number: str
    category_code: str
    category_name: str
    short_description: str
    daily_rate: Decimal
    weekly_rate: Decimal
    deposit_amount: Decimal
    min_hire_days: int
    max_hire_days: int
    image_path: str | None


@dataclass(frozen=True, slots=True)
class ModelDetail(ModelSummary):
    """A published catalogue entry as its own page shows it.

    Attributes:
        long_description: The full description, or None when none was written.
        late_fee_per_day: The fee for each day a unit comes back late.

    """

    long_description: str | None
    late_fee_per_day: Decimal


@dataclass(frozen=True, slots=True)
class ModelPage:
    """One page of a model search.

    Attributes:
        items: The models on the page, in the order asked for.
        page: The page this is, counted from one.
        page_size: How many models a page holds.
        total: How many models match the search across every page.

    """

    items: tuple[ModelSummary, ...]
    page: int
    page_size: int
    total: int
