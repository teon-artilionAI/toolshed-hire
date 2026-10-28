"""Loads the trading calendar of one branch or of several, in two queries.

A branch's calendar is its weekly hours and its live closure days, together
with the public holidays the domain works out for itself. The hours are a row
per weekday and the closures a handful a year, so both are read whole. Two
statements answer for any number of branches, which keeps a list of branches
from turning into a query per branch.

A closure day with no branch closes every branch, so it is read into the
calendar of each.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Collection
from datetime import date
from uuid import UUID

from sqlmodel import Session, col, or_, select

from app.domain.trading_calendar import BranchCalendar, OpeningHours
from app.infrastructure.models import BranchTradingHours, ClosureDay
from app.infrastructure.query_log import logged_query

logger = logging.getLogger(__name__)


def load_calendars(session: Session, branch_ids: Collection[UUID]) -> dict[UUID, BranchCalendar]:
    """Return the trading calendar of every branch named, keyed by branch.

    Args:
        session: The session to read through.
        branch_ids: The branches to answer for. A branch with no hours rows gets
            a calendar on which it never opens, which is what its rows say.

    """
    if not branch_ids:
        return {}
    wanted = list(branch_ids)
    hours_statement = select(BranchTradingHours).where(
        col(BranchTradingHours.branch_id).in_(wanted)
    )
    closures_statement = select(ClosureDay).where(
        col(ClosureDay.cancelled_at).is_(None),
        or_(col(ClosureDay.branch_id).in_(wanted), col(ClosureDay.branch_id).is_(None)),
    )
    with logged_query(
        logger, "identity.branch_calendars", {"branch_count": len(wanted)}
    ) as outcome:
        hours_rows = session.exec(hours_statement).all()
        closure_rows = session.exec(closures_statement).all()
        outcome.row_count = len(hours_rows) + len(closure_rows)

    weeks: dict[UUID, dict[int, OpeningHours]] = defaultdict(dict)
    for row in hours_rows:
        weeks[row.branch_id][row.weekday] = OpeningHours(row.opens_at, row.closes_at)
    every_branch: dict[date, str] = {}
    own: dict[UUID, dict[date, str]] = defaultdict(dict)
    for closure in closure_rows:
        if closure.branch_id is None:
            every_branch[closure.day] = closure.reason
        else:
            own[closure.branch_id][closure.day] = closure.reason
    return {
        branch_id: BranchCalendar(
            weekly=weeks[branch_id],
            # A branch's own reason wins over one given for every branch.
            closures={**every_branch, **own[branch_id]},
        )
        for branch_id in wanted
    }


def load_calendar(session: Session, branch_id: UUID) -> BranchCalendar:
    """Return the trading calendar of one branch."""
    return load_calendars(session, [branch_id])[branch_id]


def hours_rows_for(branch_id: UUID, calendar: BranchCalendar) -> list[BranchTradingHours]:
    """Return the rows that store a calendar's weekly hours for a branch.

    The seed and the test factories give a new branch its week through this, so
    the rows match what `load_calendars` reads back.
    """
    return [
        BranchTradingHours(
            branch_id=branch_id, weekday=weekday, opens_at=hours.opens, closes_at=hours.closes
        )
        for weekday, hours in sorted(calendar.weekly.items())
    ]
