"""Reading damage reports, one at a time or as a list (FR-20, US-38).

Both reads are for staff, and the routes admit nobody else. Staff read the
reports of any branch, because reading is never scoped by branch (BR-43). A
list is narrowed by the tag of a unit, by status and by the branch that holds
the unit, newest first. An unknown tag finds nothing. An unknown branch code is
refused by name, the way the list of rentals refuses it.

A report is named by its key or its reference. One that does not exist is a
`NotFound`, in a sentence the counter can act on.

Each read takes a bounded number of statements however many reports there
are. One report is one statement. A list is the branch, the count and the page.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from app.application.availability.search import UNKNOWN_BRANCH_MESSAGE
from app.application.booking.read_models import DEFAULT_PAGE_SIZE
from app.application.catalogue.read_models import FIRST_PAGE
from app.application.hire.damage_models import (
    DamageReportDetail,
    DamageReportKey,
    DamageReportPage,
    DamageReportSearch,
)
from app.application.hire.list_rentals import BRANCH_CODE_PARAMETER
from app.application.refusal import refused
from app.application.unit_of_work import UnitOfWork
from app.domain.enums import DamageStatus
from app.domain.errors import NotFound
from app.domain.identity import Actor

logger = logging.getLogger(__name__)

REPORT_NOT_FOUND_MESSAGE: Final[str] = (
    "We could not find that damage report. Check the reference and try again."
)


@dataclass(frozen=True, slots=True)
class ListDamageReportsQuery:
    """Which damage reports a member of staff wants listed.

    Attributes:
        actor: Who is asking.
        asset_tag: Only the reports of the unit with this tag, in upper case.
        status: Only reports in this status.
        branch_code: Only reports of units held at this branch.
        page: The page wanted, counted from one.
        page_size: How many reports a page holds.

    """

    actor: Actor
    asset_tag: str | None = None
    status: DamageStatus | None = None
    branch_code: str | None = None
    page: int = FIRST_PAGE
    page_size: int = DEFAULT_PAGE_SIZE


def read_report(uow: UnitOfWork, key: DamageReportKey) -> DamageReportDetail:
    """Return one report as staff read it, inside an open unit of work.

    Raises:
        NotFound: If there is no such report.

    """
    detail = uow.damage_reports.find_detail(key)
    if detail is None:
        logger.info("damage_report.not_found", extra={"damage_report": str(key)})
        raise NotFound(REPORT_NOT_FOUND_MESSAGE, {"damage_report": str(key)})
    return detail


class ReadDamageReports:
    """Return one damage report, or a page of them, to a member of staff."""

    def __init__(self, uow: UnitOfWork) -> None:
        """Keep the unit of work the reads run in."""
        self._uow = uow

    def one(self, actor: Actor, key: DamageReportKey) -> DamageReportDetail:
        """Return one report.

        Raises:
            NotFound: If there is no such report.

        """
        logger.info(
            "damage_report.read_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "damage_report": str(key),
            },
        )
        with self._uow as uow:
            detail = read_report(uow, key)
        logger.info(
            "damage_report.read_finished",
            extra={"reference": detail.reference, "status": detail.status.value},
        )
        return detail

    def page(self, query: ListDamageReportsQuery) -> DamageReportPage:
        """Return one page of reports, newest first.

        Raises:
            ValidationFailure: Naming `branchCode` when the code is not the
                code of a trading branch.

        """
        actor = query.actor
        logger.info(
            "damage_report.list_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "asset_tag": query.asset_tag,
                "status": query.status.value if query.status else None,
                "branch_code": query.branch_code,
            },
        )
        with self._uow as uow:
            found = uow.damage_reports.search(
                DamageReportSearch(
                    asset_tag=query.asset_tag,
                    status=query.status,
                    branch_id=_branch_id_of(uow, query.branch_code),
                    page=query.page,
                    page_size=query.page_size,
                )
            )
        logger.info(
            "damage_report.list_finished",
            extra={
                "actor_user_id": str(actor.user_id),
                "page": found.page,
                "page_size": found.page_size,
                "total": found.total,
            },
        )
        return found


def _branch_id_of(uow: UnitOfWork, branch_code: str | None) -> UUID | None:
    """Return the key of the trading branch a list is narrowed to, or None.

    Raises:
        ValidationFailure: Naming `branchCode` when no trading branch has the code.

    """
    if branch_code is None:
        return None
    branch = uow.branches.find_active_by_code(branch_code)
    if branch is None:
        raise refused(BRANCH_CODE_PARAMETER, UNKNOWN_BRANCH_MESSAGE, {"branch": branch_code})
    return branch.id
