"""What a list of rentals is asked with and answers, as small frozen dataclasses.

`RentalSearch` is the question the repository is asked. `RentalPage` is one
page of the answer, every rental on it a `RentalDetail` with its items and its
charges. The page limits are the ones every list of this API keeps, from one
to fifty rentals a page.

A rental is overdue when a unit is still out after the day it was due back
(BR-52). The search is handed today's business day so the repository can say
which rentals that is without reading a clock of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.application.booking.read_models import (
    DEFAULT_PAGE_SIZE,
    MAXIMUM_PAGE_SIZE,
    MINIMUM_PAGE_SIZE,
)
from app.application.catalogue.read_models import FIRST_PAGE, MAXIMUM_PAGE
from app.application.hire.read_models import RentalDetail
from app.domain.enums import RentalStatus


@dataclass(frozen=True, slots=True)
class RentalSearch:
    """Which rentals to list, and which page of them.

    Attributes:
        today: The current business day, which decides what is overdue.
        branch_id: Only rentals that went out from this branch, or None.
        status: Only rentals in this status, or None for every status.
        overdue_only: Only rentals with a unit still out after its due date.
        customer_profile_id: Only the rentals of this customer, or None.
        overdue_first: True to put the overdue rentals first, the most
            overdue first, ahead of the rest, which are newest first. False
            for newest first throughout.
        page: The page wanted, counted from one.
        page_size: How many rentals a page holds.

    """

    today: date
    branch_id: UUID | None = None
    status: RentalStatus | None = None
    overdue_only: bool = False
    customer_profile_id: UUID | None = None
    overdue_first: bool = False
    page: int = FIRST_PAGE
    page_size: int = DEFAULT_PAGE_SIZE

    def __post_init__(self) -> None:
        """Refuse a search no caller should be able to build.

        The HTTP boundary validates the same limits and answers with a 422.
        This is the second line, so a caller inside the system cannot hand the
        repository a negative offset or an unbounded page.

        Raises:
            ValueError: If the page or the page size is out of range.

        """
        if not FIRST_PAGE <= self.page <= MAXIMUM_PAGE:
            raise ValueError(
                f"Attempted to list rentals for page {self.page}. A page is between "
                f"{FIRST_PAGE} and {MAXIMUM_PAGE}."
            )
        if not MINIMUM_PAGE_SIZE <= self.page_size <= MAXIMUM_PAGE_SIZE:
            raise ValueError(
                f"Attempted to list rentals with a page size of {self.page_size}. A page "
                f"holds between {MINIMUM_PAGE_SIZE} and {MAXIMUM_PAGE_SIZE} rentals."
            )

    @property
    def offset(self) -> int:
        """Return how many rentals come before the page wanted."""
        return (self.page - FIRST_PAGE) * self.page_size


@dataclass(frozen=True, slots=True)
class RentalPage:
    """One page of a list of rentals.

    Attributes:
        items: The rentals on the page, each with its items and its charges.
        page: The page this is, counted from one.
        page_size: How many rentals a page holds.
        total: How many rentals match across every page.

    """

    items: tuple[RentalDetail, ...]
    page: int
    page_size: int
    total: int
