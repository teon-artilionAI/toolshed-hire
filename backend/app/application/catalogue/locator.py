"""The asset locator, which finds a unit at any branch (FR-15, US-10, BR-43).

A counter assistant whose branch has no unit free used to ring the other two.
The locator answers instead. It is matched against the asset tag and the model
name, across every branch, for counter staff and administrators alike, and it
only reads. Reading the location of a unit is never scoped by branch (BR-43).

Unlike the rest of the catalogue's read side, which a visitor reads and which
carries no tag and no count, this is for staff. It carries the tag, the status
and the grade of each unit, and for a unit on hire the day it is due back and
the rental it is out on.

A search is bounded the way the counter's customer search is. The text is two
to eighty characters and a page holds at most fifty units, so no request can
ask for the whole fleet at once. The text is logged by its length only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Final, Protocol

from app.application.booking.read_models import (
    DEFAULT_PAGE_SIZE,
    MAXIMUM_PAGE_SIZE,
    MINIMUM_PAGE_SIZE,
)
from app.application.catalogue.read_models import FIRST_PAGE, MAXIMUM_PAGE
from app.domain.enums import AssetStatus, ConditionGrade
from app.domain.identity import Actor

logger = logging.getLogger(__name__)

MINIMUM_LOCATOR_SEARCH_LENGTH: Final[int] = 2
MAXIMUM_LOCATOR_SEARCH_LENGTH: Final[int] = 80


@dataclass(frozen=True, slots=True)
class AssetSearch:
    """What the counter typed, and which page of the answer it wants.

    Attributes:
        text: Part of an asset tag or of a model name, without surrounding space.
        page: The page wanted, counted from one.
        page_size: How many units a page holds.

    """

    text: str
    page: int = FIRST_PAGE
    page_size: int = DEFAULT_PAGE_SIZE

    def __post_init__(self) -> None:
        """Refuse a search no caller should be able to build.

        The HTTP boundary checks the same limits and answers with a 422. This
        is the second line, so a caller inside the system cannot ask for the
        whole fleet at once.

        Raises:
            ValueError: If the text, the page or the page size is out of range.

        """
        if not MINIMUM_LOCATOR_SEARCH_LENGTH <= len(self.text) <= MAXIMUM_LOCATOR_SEARCH_LENGTH:
            raise ValueError(
                f"Attempted to locate units with {len(self.text)} characters. A search has "
                f"between {MINIMUM_LOCATOR_SEARCH_LENGTH} and {MAXIMUM_LOCATOR_SEARCH_LENGTH}."
            )
        if not FIRST_PAGE <= self.page <= MAXIMUM_PAGE:
            raise ValueError(
                f"Attempted to locate units for page {self.page}. A page is between "
                f"{FIRST_PAGE} and {MAXIMUM_PAGE}."
            )
        if not MINIMUM_PAGE_SIZE <= self.page_size <= MAXIMUM_PAGE_SIZE:
            raise ValueError(
                f"Attempted to locate units with a page size of {self.page_size}. A page "
                f"holds between {MINIMUM_PAGE_SIZE} and {MAXIMUM_PAGE_SIZE} units."
            )

    @property
    def offset(self) -> int:
        """Return how many units come before the page wanted."""
        return (self.page - FIRST_PAGE) * self.page_size


@dataclass(frozen=True, slots=True)
class AssetLocation:
    """Where one unit is and what state it is in.

    Attributes:
        asset_tag: The tag painted on the unit.
        model_name: The name of its model.
        model_slug: Its slug.
        category_name: The name of the model's category.
        branch_code: The branch the unit belongs to.
        branch_name: Its display name.
        status: Where the unit is in its lifecycle.
        condition_grade: The grade it was last recorded in.
        due_back_on: The day it is due back, while it is on hire.
        rental_reference: The rental it is out on, while it is on hire.

    """

    asset_tag: str
    model_name: str
    model_slug: str
    category_name: str
    branch_code: str
    branch_name: str
    status: AssetStatus
    condition_grade: ConditionGrade
    due_back_on: date | None
    rental_reference: str | None


@dataclass(frozen=True, slots=True)
class AssetLocationPage:
    """One page of the units a search found, in tag order."""

    items: tuple[AssetLocation, ...]
    page: int
    page_size: int
    total: int


class AssetLocatorQuery(Protocol):
    """Where the counter finds a unit."""

    def search(self, search: AssetSearch) -> AssetLocationPage:
        """Return one page of the units whose tag or model name holds the text, in tag order.

        The day a unit is due back and the rental it is out on are given only
        while it is on hire.
        """
        ...


class LocateAssets:
    """Find units at any branch for a member of staff."""

    def __init__(self, locator: AssetLocatorQuery) -> None:
        """Keep the query object the search goes through."""
        self._locator = locator

    def search(self, actor: Actor, search: AssetSearch) -> AssetLocationPage:
        """Return one page of the units the text matches, at every branch."""
        logger.info(
            "asset.locate_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "text_length": len(search.text),
                "page": search.page,
                "page_size": search.page_size,
            },
        )
        found = self._locator.search(search)
        logger.info(
            "asset.locate_finished",
            extra={"returned": len(found.items), "total": found.total, "page": found.page},
        )
        return found
