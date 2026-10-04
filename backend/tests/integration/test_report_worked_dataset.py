"""The report of a fleet whose September was worked out by hand, on PostgreSQL (FR-24, US-33).

The fleet and the figures of every unit are in `tests/support/report_dataset.py`,
in two tables in its docstring. Every expected figure here is one of those
rows, or those rows added up as the comment beside it shows. None of them was
read back from the code.

The report is read through the real query object and the real application
code, with a clock that stands on the twentieth at ten in the morning in Cape
Town. The sweep is left out, because it is proved by the API tests and here it
would only lapse the hold that ran out, which the report already leaves out.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Final
from uuid import uuid4

import pytest
from sqlmodel import Session

from app.application.reporting.dashboard import ReadAdminDashboard
from app.application.reporting.fleet_figures import FleetFigures
from app.application.reporting.read_report import ReadUtilisationReport, ReportQuery
from app.application.reporting.report_models import GroupBy, ReportLine, UtilisationReport
from app.domain.enums import UserRole
from app.domain.identity import Actor
from app.infrastructure.admin_dashboard import SqlAdminDashboard
from app.infrastructure.branch_repository import SqlBranchRepository
from app.infrastructure.fleet_report import SqlFleetReport
from tests.support.clock import FixedClock
from tests.support.factories import Factory
from tests.support.report_dataset import (
    NOW,
    OCTOBER_FIRST,
    SEPTEMBER_FIRST,
    Dataset,
    build_report_dataset,
)

pytestmark = pytest.mark.postgres

ADMIN: Final[Actor] = Actor(user_id=uuid4(), role=UserRole.ADMIN, branch_id=None)

# One row a line is compared by: the key, the units, the days on hire, the
# serviceable days, the utilisation, the four parts and gross contribution.
type Row = tuple[str, int, int, int, str | None, str, str, str, str, str]

BY_ASSET: Final[list[Row]] = [
    ("TSH-HM-0001", 1, 10, 30, "33.33", "730.63", "0.00", "0.00", "0.00", "730.63"),
    ("TSH-HM-0002", 1, 9, 30, "30.00", "212.63", "208.70", "0.00", "0.00", "421.33"),
    ("TSH-MX-0001", 1, 7, 25, "28.00", "299.99", "0.00", "400.00", "350.00", "349.99"),
    # Three lines at R0.00, in the order of their keys.
    ("TSH-DR-0001", 1, 3, 4, "75.00", "0.00", "0.00", "0.00", "0.00", "0.00"),
    ("TSH-DR-0002", 1, 0, 0, None, "0.00", "0.00", "0.00", "0.00", "0.00"),
    ("TSH-MX-0002", 1, 8, 16, "50.00", "0.00", "0.00", "0.00", "0.00", "0.00"),
    ("TSH-HM-0003", 1, 3, 23, "13.04", "0.00", "0.00", "0.00", "180.00", "-180.00"),
]
BY_MODEL: Final[list[Row]] = [
    # HM-0001, HM-0002 and HM-0003. 10 + 9 + 3 = 22 over 30 + 30 + 23 = 83 is 26.51.
    ("hammer", 3, 22, 83, "26.51", "943.26", "208.70", "0.00", "180.00", "971.96"),
    # MX-0001 and MX-0002. 7 + 8 = 15 over 25 + 16 = 41 is 36.59.
    ("mixer", 2, 15, 41, "36.59", "299.99", "0.00", "400.00", "350.00", "349.99"),
    # DR-0001 and DR-0002. 3 + 0 over 4 + 0 is 75.00.
    ("drill", 2, 3, 4, "75.00", "0.00", "0.00", "0.00", "0.00", "0.00"),
]
BY_CATEGORY: Final[list[Row]] = [
    # The hammers and the drills. 22 + 3 = 25 over 83 + 4 = 87 is 28.74.
    ("drilling", 5, 25, 87, "28.74", "943.26", "208.70", "0.00", "180.00", "971.96"),
    ("concrete", 2, 15, 41, "36.59", "299.99", "0.00", "400.00", "350.00", "349.99"),
]
BY_BRANCH: Final[list[Row]] = [
    # HM-0001, HM-0002, MX-0001 and DR-0001. 10 + 9 + 7 + 3 = 29 over 30 + 30 + 25 + 4 = 89.
    ("CBD", 4, 29, 89, "32.58", "1243.25", "208.70", "400.00", "350.00", "1501.95"),
    # HM-0003, MX-0002 and DR-0002. 3 + 8 + 0 = 11 over 23 + 16 + 0 = 39.
    ("BLV", 3, 11, 39, "28.21", "0.00", "0.00", "0.00", "180.00", "-180.00"),
]
# Every unit. 29 + 11 = 40 over 89 + 39 = 128 is 31.25. The hire revenue is
# the charge on the whole hire, 725.25, and the second hire, 518.00.
TOTALS: Final[Row] = (
    "", 7, 40, 128, "31.25", "1243.25", "208.70", "400.00", "530.00", "1321.95"
)  # fmt: skip


@pytest.fixture
def dataset(postgres_session: Session, postgres_factory: Factory) -> Dataset:
    """Return the committed fleet of the worked dataset."""
    return build_report_dataset(postgres_session, postgres_factory)


def report_of(session: Session, **asked: object) -> UtilisationReport:
    """Return every line of the report of September, as an administrator asked for it."""
    clock = FixedClock(NOW)
    fleet = SqlFleetReport(session)
    reads = ReadUtilisationReport(
        FleetFigures(fleet, clock), fleet, SqlBranchRepository(session), lambda: None
    )
    query = ReportQuery(actor=ADMIN, starts_on=SEPTEMBER_FIRST, ends_on=OCTOBER_FIRST)
    return reads.everything(replace(query, **asked))


def row_of(line: ReportLine) -> Row:
    """Return a line of the report as a row of the tables above."""
    parts = line.contribution
    return (
        line.key,
        line.asset_count,
        line.days_on_hire,
        line.serviceable_days,
        str(line.utilisation_percent) if line.utilisation_percent is not None else None,
        str(parts.hire_revenue.amount),
        str(parts.late_fees.amount),
        str(parts.damage_recovery.amount),
        str(parts.repair_costs.amount),
        str(parts.gross_contribution.amount),
    )


def totals_row(report: UtilisationReport) -> Row:
    """Return the totals of a report as a row of the tables above."""
    totals = report.totals
    parts = totals.contribution
    return (
        "",
        totals.asset_count,
        totals.days_on_hire,
        totals.serviceable_days,
        str(totals.utilisation_percent) if totals.utilisation_percent is not None else None,
        str(parts.hire_revenue.amount),
        str(parts.late_fees.amount),
        str(parts.damage_recovery.amount),
        str(parts.repair_costs.amount),
        str(parts.gross_contribution.amount),
    )


class TestEveryGrouping:
    """Each grouping of September is the hand worked table, in order, with the same totals."""

    @pytest.mark.parametrize(
        ("group_by", "expected"),
        [
            (GroupBy.ASSET, BY_ASSET),
            (GroupBy.MODEL, BY_MODEL),
            (GroupBy.CATEGORY, BY_CATEGORY),
            (GroupBy.BRANCH, BY_BRANCH),
        ],
    )
    def test_the_lines_and_the_totals_are_the_ones_worked_by_hand(
        self,
        postgres_session: Session,
        dataset: Dataset,
        group_by: GroupBy,
        expected: list[Row],
    ) -> None:
        report = report_of(postgres_session, group_by=group_by)
        assert [row_of(line) for line in report.lines] == expected
        assert totals_row(report) == TOTALS


class TestTheFilters:
    """A filter narrows the units, and a unit's share of a whole hire stays the same."""

    def test_one_branch(self, postgres_session: Session, dataset: Dataset) -> None:
        report = report_of(postgres_session, branch_code="BLV")
        assert [row_of(line) for line in report.lines] == BY_ASSET[4:]
        assert totals_row(report) == (
            "", 3, 11, 39, "28.21", "0.00", "0.00", "0.00", "180.00", "-180.00"
        )  # fmt: skip

    def test_one_category_keeps_the_mixer_share_of_the_hire_of_three(
        self, postgres_session: Session, dataset: Dataset
    ) -> None:
        report = report_of(postgres_session, category_slug=dataset.concrete_slug)
        assert [row_of(line) for line in report.lines] == [BY_ASSET[2], BY_ASSET[5]]


class TestTheMonthSoFar:
    """The dashboard's month so far is the first to the twentieth, worked out by hand.

    Up to the end of the twentieth the units were on hire 10, 9, 7, 3, 3, 0
    and 0 days, 32 in all, and serviceable 20, 20, 15, 4, 13, 6 and 0 days,
    78 in all, so utilisation is 32 over 78, 41.03. The mixer at BLV has been
    in the fleet since the 15th, six days, and none of its bookings has begun.
    Every charge and both repairs fall before the twentieth, so gross
    contribution is the month's R1321.95.
    """

    def test_the_dashboard_counts_each_branch_and_the_month_so_far(
        self, postgres_session: Session, dataset: Dataset
    ) -> None:
        clock = FixedClock(NOW)
        dashboard = ReadAdminDashboard(
            SqlAdminDashboard(postgres_session),
            FleetFigures(SqlFleetReport(postgres_session), clock),
            clock,
            lambda: None,
        ).read(ADMIN)
        month = dashboard.month_to_date
        assert (month.starts_on, month.ends_on) == (SEPTEMBER_FIRST, date(2026, 9, 21))
        assert (str(month.utilisation_percent), str(month.gross_contribution)) == (
            "41.03",
            "1321.95",
        )
        positions = {branch.branch_code: branch.counts for branch in dashboard.branches}
        assert [branch.branch_code for branch in dashboard.branches] == ["BLV", "CBD"]
        assert (positions["CBD"].on_hire, positions["CBD"].available) == (1, 2)
        assert (positions["BLV"].available, positions["BLV"].collections_due) == (2, 0)
        assert dashboard.totals.available == 4
        attention = dashboard.attention
        assert (
            attention.open_damage_reports,
            attention.customers_on_hold,
            attention.failed_notifications,
        ) == (0, 1, 1)
