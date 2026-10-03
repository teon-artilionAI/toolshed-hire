"""The counter's dashboard and diary, which are FR-16, US-18 and US-19.

The dashboard shows a branch what is due today. The collections are the
confirmed bookings whose hire has started, the returns are the hires due back
today with a unit still out, and the overdue hires are those due back before
today with a unit still out. Each list holds at most fifty rows, and the counts
are the true totals. The diary shows the collections and the returns of a
branch for one to seven days from any date.

Both are reads, but a read can be the first thing to happen after a hold has
run out or a branch has closed on a booking nobody collected. So the sweep runs
first, once the question has passed its checks (BR-13, BR-17).

Which branch is read follows one rule for both (BR-43). Counter staff read
their own branch, and naming another is refused with 403. An administrator
belongs to no branch and names one, and leaving it out is refused with a 422
that names `branchCode`.

Two figures depend on the day and on who is asking, and they are worked out
here. Whether staff may mark a collection as not collected comes from the rule
the route enforces, `no_show_refusal`, so the button and the route agree. What
an overdue hire has run up comes from the late fee policy the read is handed,
asked for each unit still out exactly as a return today would ask it, so the
dashboard shows what the counter would charge.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final

from app.application.availability.search import UNKNOWN_BRANCH_MESSAGE
from app.application.booking.access import is_staff
from app.application.clock import Clock
from app.application.hire.overview_models import (
    BranchDashboard,
    BranchDiary,
    DiaryCollection,
    DiaryDay,
    DiaryRows,
    OverdueEntry,
    ReturnEntry,
)
from app.application.hire.ports import CounterOverviewQuery
from app.application.identity.ports import BranchRepository
from app.application.refusal import refused
from app.domain.enums import UserRole
from app.domain.errors import AuthorisationFailure, BranchScopeError
from app.domain.identity import BRANCH_SCOPE_RULE, Actor, Branch, within_branch_scope
from app.domain.money import Money
from app.domain.no_show import no_show_refusal
from app.domain.policies.late_fee import LateFeePolicy

logger = logging.getLogger(__name__)

# Each list of the dashboard holds at most this many rows.
DASHBOARD_LIST_LIMIT: Final[int] = 50
MINIMUM_DIARY_DAYS: Final[int] = 1
MAXIMUM_DIARY_DAYS: Final[int] = 7
DEFAULT_DIARY_DAYS: Final[int] = 1
ONE_DAY: Final[timedelta] = timedelta(days=1)
# The names the contract gives the three parameters, which a refusal names.
BRANCH_CODE_PARAMETER: Final[str] = "branchCode"
FROM_PARAMETER: Final[str] = "from"
DAYS_PARAMETER: Final[str] = "days"

BRANCH_REQUIRED_MESSAGE: Final[str] = "Choose the branch to show."
OWN_BRANCH_ONLY_MESSAGE: Final[str] = (
    "Counter staff can only open the dashboard and the diary of their own branch."
)
STAFF_ONLY_MESSAGE: Final[str] = "Only a member of staff can open the dashboard or the diary."
DAYS_OUT_OF_RANGE_MESSAGE: Final[str] = (
    f"Choose from {MINIMUM_DIARY_DAYS} to {MAXIMUM_DIARY_DAYS} days."
)
DATE_TOO_FAR_MESSAGE: Final[str] = "Choose an earlier date."


@dataclass(frozen=True, slots=True)
class DashboardQuery:
    """Who is asking for the dashboard, and of which branch.

    Attributes:
        actor: The member of staff, with the role and the branch they hold.
        branch_code: The branch named, or None. Counter staff may leave it
            out and an administrator may not.

    """

    actor: Actor
    branch_code: str | None = None


@dataclass(frozen=True, slots=True)
class DiaryQuery:
    """Who is asking for the diary, of which branch, from when and for how long.

    Attributes:
        actor: The member of staff, with the role and the branch they hold.
        branch_code: The branch named, or None, as for the dashboard.
        first_day: The first day to show, or None for today.
        days: How many days to show, from one to seven.

    """

    actor: Actor
    branch_code: str | None = None
    first_day: date | None = None
    days: int = DEFAULT_DIARY_DAYS


class ReadCounterOverview:
    """The dashboard and the diary of a branch, for a member of staff."""

    def __init__(
        self,
        overview: CounterOverviewQuery,
        branches: BranchRepository,
        clock: Clock,
        lapse_due_bookings: Callable[[], object],
        policy: LateFeePolicy,
    ) -> None:
        """Keep the ports the reads go through, the clock, the sweep and the late fee policy.

        Args:
            overview: Reads the bookings and hires of a branch.
            branches: Finds the branch named or the one staff belong to.
            clock: Where the current business day comes from.
            lapse_due_bookings: Runs the sweep, before every answer.
            policy: The late fee policy, which says what an overdue hire has
                run up so far.

        """
        self._overview = overview
        self._branches = branches
        self._clock = clock
        self._lapse_due_bookings = lapse_due_bookings
        self._policy = policy

    def dashboard(self, query: DashboardQuery) -> BranchDashboard:
        """Return what is due today at the branch the caller may read.

        Raises:
            AuthorisationFailure: If the caller is not staff.
            BranchScopeError: If counter staff name another branch.
            ValidationFailure: Naming `branchCode` when an administrator names
                no branch or one that is not trading.

        """
        actor = query.actor
        _log_request("counter.dashboard_requested", actor, query.branch_code)
        branch = self._branch_for(actor, query.branch_code)
        self._lapse_due_bookings()
        today = self._clock.today()
        rows = self._overview.dashboard(branch.id, today, DASHBOARD_LIST_LIMIT)
        dashboard = BranchDashboard(
            branch=branch,
            business_day=today,
            counts=rows.counts,
            collections_due=rows.collections_due,
            returns_due=rows.returns_due,
            overdue=tuple(
                _overdue_entry(rental, today, self._policy) for rental in rows.overdue
            ),
        )
        logger.info(
            "counter.dashboard_finished",
            extra={
                "branch_code": branch.code,
                "business_day": today.isoformat(),
                "collections_due": rows.counts.collections_due,
                "returns_due": rows.counts.returns_due,
                "overdue": rows.counts.overdue,
            },
        )
        return dashboard

    def diary(self, query: DiaryQuery) -> BranchDiary:
        """Return the collections and the returns of the branch, day by day.

        Raises:
            ValidationFailure: Naming `days` when it is outside one to seven,
                `from` when the run would end past the last date there is, or
                `branchCode` as for the dashboard.
            AuthorisationFailure: If the caller is not staff.
            BranchScopeError: If counter staff name another branch.

        """
        actor = query.actor
        _log_request("counter.diary_requested", actor, query.branch_code)
        if not MINIMUM_DIARY_DAYS <= query.days <= MAXIMUM_DIARY_DAYS:
            raise refused(DAYS_PARAMETER, DAYS_OUT_OF_RANGE_MESSAGE, {"days": query.days})
        today = self._clock.today()
        first_day = query.first_day or today
        if first_day > date.max - ONE_DAY * (query.days - MINIMUM_DIARY_DAYS):
            raise refused(FROM_PARAMETER, DATE_TOO_FAR_MESSAGE, {"from": first_day.isoformat()})
        last_day = first_day + ONE_DAY * (query.days - MINIMUM_DIARY_DAYS)
        branch = self._branch_for(actor, query.branch_code)
        self._lapse_due_bookings()
        rows = self._overview.diary(branch.id, first_day, last_day)
        diary = BranchDiary(
            branch=branch,
            days=tuple(
                _diary_day(actor, branch, rows, first_day + ONE_DAY * offset, today)
                for offset in range(query.days)
            ),
        )
        logger.info(
            "counter.diary_finished",
            extra={
                "branch_code": branch.code,
                "first_day": first_day.isoformat(),
                "days": query.days,
                "collection_count": len(rows.collections),
                "return_count": len(rows.returns),
            },
        )
        return diary

    def _branch_for(self, actor: Actor, branch_code: str | None) -> Branch:
        """Return the branch the caller reads, by the rule of BR-43.

        Raises:
            AuthorisationFailure: If the caller is not staff.
            BranchScopeError: If counter staff name a branch that is not
                theirs, or carry no branch at all.
            ValidationFailure: Naming `branchCode` when an administrator names
                no branch, or one that is not trading.

        """
        if not is_staff(actor):
            raise AuthorisationFailure(
                STAFF_ONLY_MESSAGE, {"required_roles": ["ADMIN", "COUNTER_STAFF"]}
            )
        if actor.role is UserRole.COUNTER_STAFF:
            own = self._branches.get(actor.branch_id) if actor.branch_id is not None else None
            if own is None or (branch_code is not None and branch_code != own.code):
                raise BranchScopeError(
                    OWN_BRANCH_ONLY_MESSAGE, {"branch": branch_code}, rule=BRANCH_SCOPE_RULE
                )
            return own
        if branch_code is None:
            raise refused(BRANCH_CODE_PARAMETER, BRANCH_REQUIRED_MESSAGE)
        branch = self._branches.find_active_by_code(branch_code)
        if branch is None:
            raise refused(BRANCH_CODE_PARAMETER, UNKNOWN_BRANCH_MESSAGE, {"branch": branch_code})
        return branch


def _log_request(event: str, actor: Actor, branch_code: str | None) -> None:
    """Write the line that says who asked for which branch."""
    logger.info(
        event,
        extra={
            "actor_user_id": str(actor.user_id),
            "actor_role": actor.role.value,
            "branch_code": branch_code,
        },
    )


def _overdue_entry(rental: ReturnEntry, today: date, policy: LateFeePolicy) -> OverdueEntry:
    """Return an overdue rental with how late it is and what its units still out have run up."""
    accrued = Money.zero()
    days_overdue = (today - rental.due_back_on).days
    for fee_per_day in rental.fees_per_day_of_units_out():
        late = policy.late_fee(
            due_back_on=rental.due_back_on,
            returned_on=today,
            fee_per_day=Money.create(fee_per_day),
        )
        accrued = accrued.add(late.amount)
    return OverdueEntry(
        rental=rental, days_overdue=days_overdue, late_fee_accrued=accrued.rounded().amount
    )


def _diary_day(
    actor: Actor, branch: Branch, rows: DiaryRows, business_day: date, today: date
) -> DiaryDay:
    """Return one day of the diary, with whether each collection may be marked by the caller."""
    may_act = within_branch_scope(actor, branch.id)
    return DiaryDay(
        business_day=business_day,
        collections=tuple(
            DiaryCollection(
                entry=entry,
                can_mark_no_show=(
                    may_act and no_show_refusal(entry.status, entry.start_date, today) is None
                ),
            )
            for entry in rows.collections
            if entry.start_date == business_day
        ),
        returns=tuple(rental for rental in rows.returns if rental.due_back_on == business_day),
    )
