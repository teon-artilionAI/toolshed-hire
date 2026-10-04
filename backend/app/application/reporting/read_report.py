"""The utilisation and gross contribution report, which is FR-24, US-33 and US-34.

An administrator asks for any period of up to 366 days, grouped by asset,
model, category or branch, and narrowed to a branch or a category if they like.
The answer is one line for each group, highest gross contribution first, with
the totals over every line, a page at a time on the screen and every line in
the CSV.

The checks come first, in the order a form shows them. The period has to end
after it starts and cover at most 366 days, the page has to exist, and a branch
or a category named has to be one there is. A refusal names the parameter it
refused (NFR-04).

A report counts the units bookings hold, so a hold that ran out or a booking
nobody collected would count days that are no longer booked. The sweep runs
before the figures are read, as it does before the counter's dashboard
(BR-13, BR-17).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Final
from uuid import UUID

from app.application.availability.search import UNKNOWN_BRANCH_MESSAGE
from app.application.catalogue.read_models import FIRST_PAGE, MAXIMUM_PAGE
from app.application.identity.ports import BranchRepository
from app.application.refusal import refused
from app.application.reporting.fleet_figures import FleetFigures, FleetQuestion
from app.application.reporting.grouping import page_of
from app.application.reporting.ports import FleetReportQuery
from app.application.reporting.report_models import (
    GroupBy,
    UtilisationReport,
    UtilisationReportPage,
)
from app.domain.enums import UserRole
from app.domain.errors import AuthorisationFailure
from app.domain.identity import Actor

logger = logging.getLogger(__name__)

MAXIMUM_REPORT_DAYS: Final[int] = 366
MINIMUM_PAGE_SIZE: Final[int] = 1
MAXIMUM_PAGE_SIZE: Final[int] = 100
DEFAULT_PAGE_SIZE: Final[int] = 20
# The names the contract gives the parameters, which a refusal names.
TO_PARAMETER: Final[str] = "to"
PAGE_PARAMETER: Final[str] = "page"
PAGE_SIZE_PARAMETER: Final[str] = "pageSize"
BRANCH_CODE_PARAMETER: Final[str] = "branchCode"
CATEGORY_SLUG_PARAMETER: Final[str] = "categorySlug"

ADMIN_ONLY_MESSAGE: Final[str] = "Only an administrator can read the reports."
END_NOT_AFTER_START_MESSAGE: Final[str] = "The end of the period has to be after its start."
PERIOD_TOO_LONG_MESSAGE: Final[str] = (
    f"A report can cover at most {MAXIMUM_REPORT_DAYS} days. Choose a shorter period."
)
PAGE_OUT_OF_RANGE_MESSAGE: Final[str] = f"Choose a page from {FIRST_PAGE} to {MAXIMUM_PAGE}."
PAGE_SIZE_OUT_OF_RANGE_MESSAGE: Final[str] = (
    f"Choose from {MINIMUM_PAGE_SIZE} to {MAXIMUM_PAGE_SIZE} lines a page."
)
UNKNOWN_CATEGORY_MESSAGE: Final[str] = (
    "We do not have that category. Choose a category from the list."
)


@dataclass(frozen=True, slots=True)
class ReportQuery:
    """What an administrator asks the report for.

    Attributes:
        actor: Who is asking.
        starts_on: The first day of the period.
        ends_on: The first day after it.
        group_by: What each line stands for.
        branch_code: Only the units held at this branch, or None.
        category_slug: Only the units of this category and its children, or None.
        page: The page wanted, counted from one. The CSV ignores it.
        page_size: How many lines a page holds. The CSV ignores it.

    """

    actor: Actor
    starts_on: date
    ends_on: date
    group_by: GroupBy = GroupBy.ASSET
    branch_code: str | None = None
    category_slug: str | None = None
    page: int = FIRST_PAGE
    page_size: int = DEFAULT_PAGE_SIZE


class ReadUtilisationReport:
    """The utilisation and gross contribution report, for an administrator."""

    def __init__(
        self,
        figures: FleetFigures,
        fleet: FleetReportQuery,
        branches: BranchRepository,
        lapse_due_bookings: Callable[[], object],
    ) -> None:
        """Keep what the report is worked out with, the lookups its checks need and the sweep.

        Args:
            figures: Works out the lines and the totals of a period.
            fleet: The query object, asked whether a category exists.
            branches: Finds the branch named.
            lapse_due_bookings: Runs the sweep before the figures are read.

        """
        self._figures = figures
        self._fleet = fleet
        self._branches = branches
        self._lapse_due_bookings = lapse_due_bookings

    def page(self, query: ReportQuery) -> UtilisationReportPage:
        """Return one page of the report, with the totals over every line.

        Raises:
            AuthorisationFailure: If the caller is not an administrator.
            ValidationFailure: Naming `to`, `page`, `pageSize`, `branchCode`
                or `categorySlug` when that parameter is refused.

        """
        ensure_administrator(query.actor)
        if not FIRST_PAGE <= query.page <= MAXIMUM_PAGE:
            raise refused(PAGE_PARAMETER, PAGE_OUT_OF_RANGE_MESSAGE, {"page": query.page})
        if not MINIMUM_PAGE_SIZE <= query.page_size <= MAXIMUM_PAGE_SIZE:
            raise refused(
                PAGE_SIZE_PARAMETER, PAGE_SIZE_OUT_OF_RANGE_MESSAGE, {"page_size": query.page_size}
            )
        found = page_of(self.everything(query), query.page, query.page_size)
        logger.info(
            "report.utilisation_page_finished",
            extra={"page": found.page, "page_size": found.page_size, "total": found.total},
        )
        return found

    def everything(self, query: ReportQuery) -> UtilisationReport:
        """Return every line of the report, for the CSV.

        Raises:
            AuthorisationFailure: If the caller is not an administrator.
            ValidationFailure: Naming `to`, `branchCode` or `categorySlug`
                when that parameter is refused.

        """
        actor = query.actor
        logger.info(
            "report.utilisation_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "from": query.starts_on.isoformat(),
                "to": query.ends_on.isoformat(),
                "group_by": query.group_by.value,
                "branch_code": query.branch_code,
                "category_slug": query.category_slug,
            },
        )
        ensure_administrator(actor)
        _ensure_period_reportable(query)
        branch_id = self._branch_id_of(query.branch_code)
        self._ensure_category_exists(query.category_slug)
        self._lapse_due_bookings()
        report = self._figures.report(
            FleetQuestion(
                starts_on=query.starts_on,
                ends_on=query.ends_on,
                group_by=query.group_by,
                branch_id=branch_id,
                category_slug=query.category_slug,
            )
        )
        logger.info(
            "report.utilisation_finished",
            extra={
                "actor_user_id": str(actor.user_id),
                "group_by": report.group_by.value,
                "line_count": len(report.lines),
                "asset_count": report.totals.asset_count,
            },
        )
        return report

    def _branch_id_of(self, branch_code: str | None) -> UUID | None:
        """Return the key of the trading branch named, or None when none is named.

        Raises:
            ValidationFailure: Naming `branchCode` when no trading branch has the code.

        """
        if branch_code is None:
            return None
        branch = self._branches.find_active_by_code(branch_code)
        if branch is None:
            raise refused(BRANCH_CODE_PARAMETER, UNKNOWN_BRANCH_MESSAGE, {"branch": branch_code})
        return branch.id

    def _ensure_category_exists(self, slug: str | None) -> None:
        """Refuse a category nobody has.

        Raises:
            ValidationFailure: Naming `categorySlug` when no category has the slug.

        """
        if slug is not None and not self._fleet.category_exists(slug):
            raise refused(CATEGORY_SLUG_PARAMETER, UNKNOWN_CATEGORY_MESSAGE, {"category": slug})


def ensure_administrator(actor: Actor) -> None:
    """Refuse anybody who is not an administrator.

    The routes admit administrators alone already. This holds the rule where
    the reports are worked out as well, so no other caller can reach them.

    Raises:
        AuthorisationFailure: If the actor is not an administrator.

    """
    if actor.role is not UserRole.ADMIN:
        raise AuthorisationFailure(ADMIN_ONLY_MESSAGE, {"required_roles": ["ADMIN"]})


def _ensure_period_reportable(query: ReportQuery) -> None:
    """Refuse a period that ends before it starts or runs past the longest a report covers.

    Raises:
        ValidationFailure: Naming `to`.

    """
    window = {"from": query.starts_on.isoformat(), "to": query.ends_on.isoformat()}
    if query.ends_on <= query.starts_on:
        raise refused(TO_PARAMETER, END_NOT_AFTER_START_MESSAGE, window)
    if (query.ends_on - query.starts_on).days > MAXIMUM_REPORT_DAYS:
        raise refused(TO_PARAMETER, PERIOD_TOO_LONG_MESSAGE, window)
