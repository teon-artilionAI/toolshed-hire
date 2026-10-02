"""Searching availability, which is FR-03 and FR-04.

A visitor asks where the catalogue is free for a period, or where one model is
free in a given quantity. Nothing is held and nothing is written, so there is
no unit of work here. The answer comes from the `AvailabilityQuery` port, and
this module owns the rules that decide whether the question may be asked at
all.

The period, the quantity and the hire limits of a model are checked by
`app/application/availability/hire_request.py`, which a quote uses as well, so
a search, a quote and a booking agree about what may be asked (BR-02 to
BR-05). The day it is comes from the clock, in the business time zone.

Every refusal names the parameter that caused it, so the screen can put the
sentence beside the right input. The sentence is written for the visitor. The
rule and the values that were tried go to the log.

The hire limits of a single model are checked on the single model question
only. A search across the catalogue answers whether a unit is free, and the
limits of each model travel with it in the summary.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Final

from app.application.availability.hire_request import (
    ensure_quantity_in_range,
    ensure_within_hire_limits,
    requested_period,
)
from app.application.availability.ports import AvailabilityQuery
from app.application.availability.read_models import (
    AvailabilityPage,
    AvailabilitySearch,
    ModelAvailabilityAnswer,
)
from app.application.catalogue.browse import MODEL_NOT_FOUND_MESSAGE, ensure_category_exists
from app.application.catalogue.ports import CatalogueQuery
from app.application.catalogue.read_models import ModelSearch
from app.application.clock import Clock
from app.application.identity.ports import BranchDirectory
from app.application.refusal import refused
from app.domain.errors import NotFound

logger = logging.getLogger(__name__)

# The name of the parameter a search carries its branch in.
BRANCH_PARAMETER: Final[str] = "branch"
UNKNOWN_BRANCH_MESSAGE: Final[str] = (
    "We do not have a branch with that code. Choose a branch from the list."
)


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
        period = requested_period(start, end, self._clock.today())
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
        period = requested_period(start, end, self._clock.today())
        ensure_quantity_in_range(quantity)
        model = self._catalogue.find_model(slug)
        if model is None:
            logger.info(
                "availability.model_not_found",
                extra={"slug": slug, "attempted": "check availability of a catalogue model"},
            )
            raise NotFound(MODEL_NOT_FOUND_MESSAGE, {"slug": slug})
        ensure_within_hire_limits(model, period)
        answers = self._availability.for_model(slug, period, quantity)
        return ModelAvailabilityAnswer(period=period, quantity=quantity, branches=tuple(answers))

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
                UNKNOWN_BRANCH_MESSAGE,
                {"branch": branch_code, "known_branches": sorted(known)},
            )

