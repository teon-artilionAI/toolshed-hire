"""Searching availability, which is FR-03 and FR-04.

A visitor asks where the catalogue is free for a period, or where one model is
free in a given quantity. Nothing is held and nothing is written, so there is
no unit of work here. The answer comes from the `AvailabilityQuery` port, and
this module owns the rules that decide whether the question may be asked at
all.

The period is built as a `BookingPeriod`, so a search and a booking agree
about what a period is. That gives BR-02, the half open bounds, and BR-03, the
limit of twenty eight days. `ensure_within_booking_window` gives BR-04 and
BR-05, no start in the past and none more than ninety days ahead. The day it
is comes from the clock, in the business time zone.

Every refusal names the parameter that caused it, so the screen can put the
sentence beside the right input.

The hire limits of a single model are checked on the single model question
only. A search across the catalogue answers whether a unit is free, and the
limits of each model travel with it in the summary.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Final

from app.application.availability.allocation import MAXIMUM_QUANTITY, MINIMUM_QUANTITY
from app.application.availability.ports import AvailabilityQuery
from app.application.availability.read_models import (
    AvailabilityPage,
    AvailabilitySearch,
    ModelAvailabilityAnswer,
)
from app.application.catalogue.browse import ensure_category_exists
from app.application.catalogue.ports import CatalogueQuery
from app.application.catalogue.read_models import ModelDetail, ModelSearch
from app.application.clock import Clock
from app.application.identity.ports import BranchDirectory
from app.application.refusal import refused
from app.domain.errors import DetailValue, NotFound, ValidationFailure
from app.domain.period import BookingPeriod, InvalidBookingPeriod, ensure_within_booking_window

logger = logging.getLogger(__name__)

# The names of the parameters a search carries, as a refusal reports them.
FROM_PARAMETER: Final[str] = "from"
TO_PARAMETER: Final[str] = "to"
BRANCH_PARAMETER: Final[str] = "branch"
QUANTITY_PARAMETER: Final[str] = "quantity"


class SearchAvailability:
    """Where the fleet is free, as a visitor asks it."""

    def __init__(
        self,
        availability: AvailabilityQuery,
        catalogue: CatalogueQuery,
        branches: BranchDirectory,
        clock: Clock,
    ) -> None:
        """Keep the ports the search reads through and the clock it dates by.

        Args:
            availability: Answers where units are free.
            catalogue: Checks the category and finds the single model.
            branches: Checks the branch a search is narrowed to.
            clock: Where the current business day comes from.

        """
        self._availability = availability
        self._catalogue = catalogue
        self._branches = branches
        self._clock = clock

    def across_catalogue(
        self, start: date, end: date, models: ModelSearch, branch_code: str | None = None
    ) -> AvailabilityPage:
        """Answer for one page of the catalogue at every active branch.

        Args:
            start: The first day of the hire.
            end: The day the equipment comes back, which is free again.
            models: Which models to answer for, in what order, and which page.
            branch_code: When set, only models free at this branch are listed.

        Raises:
            ValidationFailure: If the period, the category or the branch is
                refused. The failure names the parameter.

        """
        period = self._hire_period(start, end)
        ensure_category_exists(self._catalogue, models.category_slug)
        self._ensure_branch_exists(branch_code)
        return self._availability.search(
            AvailabilitySearch(period=period, models=models, branch_code=branch_code)
        )

    def for_model(
        self, slug: str, start: date, end: date, quantity: int
    ) -> ModelAvailabilityAnswer:
        """Answer where one model is free in the quantity asked for.

        Args:
            slug: The slug of a published model.
            start: The first day of the hire.
            end: The day the equipment comes back, which is free again.
            quantity: How many units are wanted at one branch.

        Raises:
            ValidationFailure: If the period or the quantity is refused, or if
                the period is outside the hire limits of the model.
            NotFound: If no published model carries the slug.

        """
        period = self._hire_period(start, end)
        _ensure_quantity_in_range(quantity)
        model = self._catalogue.find_model(slug)
        if model is None:
            logger.info("availability.model_not_found", extra={"slug": slug})
            raise NotFound(
                f"Attempted to check availability of catalogue model {slug!r}, "
                "which does not exist.",
                {"slug": slug},
            )
        _ensure_within_hire_limits(model, period)
        answers = self._availability.for_model(slug, period, quantity)
        return ModelAvailabilityAnswer(period=period, quantity=quantity, branches=tuple(answers))

    def _hire_period(self, start: date, end: date) -> BookingPeriod:
        """Build the period of a search, refusing one a booking would refuse.

        Raises:
            ValidationFailure: Naming `to` when the dates cannot form a hire
                period, and `from` when the hire starts in the past or beyond
                the booking horizon.

        """
        try:
            period = BookingPeriod(start, end)
        except InvalidBookingPeriod as error:
            raise refused(
                TO_PARAMETER,
                str(error),
                {"from": start.isoformat(), "to": end.isoformat()},
            ) from error
        try:
            ensure_within_booking_window(period, self._clock.today())
        except ValidationFailure as failure:
            raise refused(FROM_PARAMETER, failure.message, failure.detail) from failure
        return period

    def _ensure_branch_exists(self, branch_code: str | None) -> None:
        """Refuse a search narrowed to a branch that is not trading.

        Raises:
            ValidationFailure: Naming `branch` when the code is not the code
                of an active branch.

        """
        if branch_code is None:
            return
        known = {branch.code for branch in self._branches.list_active()}
        if branch_code not in known:
            logger.info("availability.unknown_branch_refused", extra={"branch": branch_code})
            raise refused(
                BRANCH_PARAMETER,
                f"Attempted to search branch {branch_code!r}, which is not a trading branch.",
                {"branch": branch_code, "known_branches": sorted(known)},
            )


def _ensure_quantity_in_range(quantity: int) -> None:
    """Refuse a quantity a reservation line could not carry."""
    if not MINIMUM_QUANTITY <= quantity <= MAXIMUM_QUANTITY:
        raise refused(
            QUANTITY_PARAMETER,
            f"Attempted to check availability of {quantity} units. A booking holds between "
            f"{MINIMUM_QUANTITY} and {MAXIMUM_QUANTITY} units of one model.",
            {"minimum": MINIMUM_QUANTITY, "maximum": MAXIMUM_QUANTITY, "received": quantity},
        )


def _ensure_within_hire_limits(model: ModelDetail, period: BookingPeriod) -> None:
    """Refuse a period shorter or longer than the model may be hired for.

    Raises:
        ValidationFailure: Naming `to`, because the return day is the bound a
            visitor moves to make the hire longer or shorter.

    """
    detail: dict[str, DetailValue] = {
        "sku": model.sku,
        "hire_days": period.days,
        "min_hire_days": model.min_hire_days,
        "max_hire_days": model.max_hire_days,
    }
    if period.days > model.max_hire_days:
        raise refused(
            TO_PARAMETER,
            f"Attempted to check a hire of {period.days} days for {model.name}. "
            f"This model is hired for at most {model.max_hire_days} days.",
            detail,
        )
    if period.days < model.min_hire_days:
        raise refused(
            TO_PARAMETER,
            f"Attempted to check a hire of {period.days} days for {model.name}. "
            f"This model is hired for at least {model.min_hire_days} days.",
            detail,
        )
