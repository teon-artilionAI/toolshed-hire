"""Working the report out for one period, once its question has passed its checks.

The report and the admin dashboard both need the figures of a period, and this
is the one place they are worked out. It turns the period into the instants it
begins and ends at in Cape Town, reads the fleet through the query object,
puts each unit's figures together and groups them into lines. It checks
nothing and runs no sweep, because each caller does both first.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Final
from uuid import UUID

from app.application.clock import Clock
from app.application.reporting.evidence import ReportScope
from app.application.reporting.grouping import report_lines, totals_of
from app.application.reporting.ports import FleetReportQuery
from app.application.reporting.report_models import GroupBy, UtilisationReport
from app.application.reporting.unit_figures import figures_of
from app.domain.business_time import business_instant
from app.domain.report_days import DaySpan

logger = logging.getLogger(__name__)

# A business day begins at midnight in Cape Town.
START_OF_DAY: Final[time] = time(0, 0)


@dataclass(frozen=True, slots=True)
class FleetQuestion:
    """The period, the grouping and the filters a report is worked out for.

    Attributes:
        starts_on: The first day of the period.
        ends_on: The first day after it.
        group_by: What each line stands for.
        branch_id: Only the units of this branch, or None.
        category_slug: Only the units of this category and its children, or None.

    """

    starts_on: date
    ends_on: date
    group_by: GroupBy
    branch_id: UUID | None = None
    category_slug: str | None = None


class FleetFigures:
    """Works out every line of the report for one period."""

    def __init__(self, fleet: FleetReportQuery, clock: Clock) -> None:
        """Keep the query object the fleet is read through and the clock."""
        self._fleet = fleet
        self._clock = clock

    def report(self, question: FleetQuestion) -> UtilisationReport:
        """Return every line of the report, highest gross contribution first, with the totals."""
        today = self._clock.today()
        scope = ReportScope(
            starts_on=question.starts_on,
            ends_on=question.ends_on,
            starts_at=_instant_beginning(question.starts_on),
            ends_at=_instant_beginning(question.ends_on),
            now=self._clock.now(),
            branch_id=question.branch_id,
            category_slug=question.category_slug,
        )
        evidence = self._fleet.evidence(scope)
        figures = figures_of(evidence, DaySpan(question.starts_on, question.ends_on), today)
        report = UtilisationReport(
            starts_on=question.starts_on,
            ends_on=question.ends_on,
            group_by=question.group_by,
            lines=report_lines(figures, question.group_by),
            totals=totals_of(figures),
        )
        logger.info(
            "report.figures_worked_out",
            extra={
                "from": question.starts_on.isoformat(),
                "to": question.ends_on.isoformat(),
                "group_by": question.group_by.value,
                "unit_count": len(evidence.units),
                "dated_fact_count": len(evidence.dated),
                "shared_hire_row_count": len(evidence.shared_hire),
                "line_count": len(report.lines),
            },
        )
        return report


def _instant_beginning(day: date) -> datetime:
    """Return the instant a business day begins at, in UTC."""
    return business_instant(day, START_OF_DAY).astimezone(UTC)
