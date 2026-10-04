"""The admin dashboard, which is the business across every branch today (SC-19).

For each trading branch it counts what the counter's dashboard counts, the
collections due, the returns due today and the overdue hires, and where the
units stand, on hire, in quarantine, under repair and on the shelf. The totals
add the branches up. Beside them stand the report's two figures for the month
so far, from the first of the month up to the end of today, worked out by the
same code as the report, and three counts of what waits for an administrator,
the damage reports still open or under repair, the customers on hold and the
messages that could not be sent.

Reading it runs the sweep first, so a hold that ran out or a booking nobody
collected is not counted as due (BR-13, BR-17).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import timedelta
from typing import Final

from app.application.clock import Clock
from app.application.reporting.fleet_figures import FleetFigures, FleetQuestion
from app.application.reporting.ports import AdminDashboardQuery
from app.application.reporting.read_report import ensure_administrator
from app.application.reporting.report_models import (
    AdminDashboard,
    BranchCounts,
    GroupBy,
    MonthToDate,
)
from app.domain.identity import Actor

logger = logging.getLogger(__name__)

FIRST_OF_THE_MONTH: Final[int] = 1
ONE_DAY: Final[timedelta] = timedelta(days=1)


class ReadAdminDashboard:
    """The business across every branch today, for an administrator."""

    def __init__(
        self,
        positions: AdminDashboardQuery,
        figures: FleetFigures,
        clock: Clock,
        lapse_due_bookings: Callable[[], object],
    ) -> None:
        """Keep the counts, the report's figures, the clock and the sweep.

        Args:
            positions: Counts each branch and what waits for an administrator.
            figures: Works out the report's figures for the month so far.
            clock: Where today comes from.
            lapse_due_bookings: Runs the sweep before anything is counted.

        """
        self._positions = positions
        self._figures = figures
        self._clock = clock
        self._lapse_due_bookings = lapse_due_bookings

    def read(self, actor: Actor) -> AdminDashboard:
        """Return the business across every branch today, after running the sweep.

        Raises:
            AuthorisationFailure: If the caller is not an administrator.

        """
        logger.info(
            "report.dashboard_requested",
            extra={"actor_user_id": str(actor.user_id), "actor_role": actor.role.value},
        )
        ensure_administrator(actor)
        self._lapse_due_bookings()
        today = self._clock.today()
        branches = self._positions.branch_positions(today)
        totals = BranchCounts.none()
        for branch in branches:
            totals = totals.plus(branch.counts)
        month = self._figures.report(
            FleetQuestion(
                starts_on=today.replace(day=FIRST_OF_THE_MONTH),
                ends_on=today + ONE_DAY,
                group_by=GroupBy.BRANCH,
            )
        )
        dashboard = AdminDashboard(
            business_day=today,
            branches=branches,
            totals=totals,
            month_to_date=MonthToDate(
                starts_on=month.starts_on,
                ends_on=month.ends_on,
                utilisation_percent=month.totals.utilisation_percent,
                gross_contribution=month.totals.contribution.gross_contribution.amount,
            ),
            attention=self._positions.attention_counts(),
        )
        logger.info(
            "report.dashboard_finished",
            extra={
                "business_day": today.isoformat(),
                "branch_count": len(branches),
                "on_hire": totals.on_hire,
                "overdue": totals.overdue,
                "open_damage_reports": dashboard.attention.open_damage_reports,
            },
        )
        return dashboard
