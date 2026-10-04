"""The dependencies of the reporting module, the utilisation report and the admin dashboard.

This is the reporting part of the composition root. Both are reads, so each
query object is handed the request scoped session and the request closes it,
the way the counter's reads are wired in `app/api/counter_deps.py`. Both are
handed the sweep from `app/api/sweep_deps.py` and run it before they count
anything, and both work the report's figures out through the one
`FleetFigures`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.api.deps import ClockDependency, SessionDependency
from app.api.sweep_deps import ExpiredHoldSweeper
from app.application.reporting.dashboard import ReadAdminDashboard
from app.application.reporting.fleet_figures import FleetFigures
from app.application.reporting.ports import FleetReportQuery
from app.application.reporting.read_report import ReadUtilisationReport
from app.infrastructure.admin_dashboard import SqlAdminDashboard
from app.infrastructure.branch_repository import SqlBranchRepository
from app.infrastructure.fleet_report import SqlFleetReport


def get_fleet_report_query(session: SessionDependency) -> FleetReportQuery:
    """Return the SQL report query object over the request scoped session."""
    return SqlFleetReport(session)


FleetReportQueryDependency = Annotated[FleetReportQuery, Depends(get_fleet_report_query)]


def get_fleet_figures(fleet: FleetReportQueryDependency, clock: ClockDependency) -> FleetFigures:
    """Return what works the report's figures out, over the report query object."""
    return FleetFigures(fleet, clock)


FleetFiguresDependency = Annotated[FleetFigures, Depends(get_fleet_figures)]


def get_read_utilisation_report(
    figures: FleetFiguresDependency,
    fleet: FleetReportQueryDependency,
    session: SessionDependency,
    lapse_due_bookings: ExpiredHoldSweeper,
) -> ReadUtilisationReport:
    """Return the report, wired to its figures, its lookups and the sweep."""
    return ReadUtilisationReport(figures, fleet, SqlBranchRepository(session), lapse_due_bookings)


ReadUtilisationReportDependency = Annotated[
    ReadUtilisationReport, Depends(get_read_utilisation_report)
]


def get_read_admin_dashboard(
    figures: FleetFiguresDependency,
    session: SessionDependency,
    clock: ClockDependency,
    lapse_due_bookings: ExpiredHoldSweeper,
) -> ReadAdminDashboard:
    """Return the admin dashboard, wired to its counts, the report's figures and the sweep."""
    return ReadAdminDashboard(SqlAdminDashboard(session), figures, clock, lapse_due_bookings)


ReadAdminDashboardDependency = Annotated[ReadAdminDashboard, Depends(get_read_admin_dashboard)]
