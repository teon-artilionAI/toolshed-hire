"""How the utilisation report and the admin dashboard are written in the shape of the contract.

Nothing is worked out here. Every figure was decided before it reached this
module, and this only maps the read models to the responses.
"""

from __future__ import annotations

from app.api.report_schemas import (
    AdminDashboardResponse,
    BranchCountsResponse,
    BranchPositionResponse,
    MonthToDateResponse,
    ReportDefinitionsResponse,
    ReportFiguresResponse,
    ReportLineResponse,
    UtilisationReportResponse,
)
from app.application.reporting.definitions import (
    GROSS_CONTRIBUTION_DEFINITION,
    UTILISATION_DEFINITION,
)
from app.application.reporting.report_models import (
    AdminDashboard,
    BranchCounts,
    BranchPosition,
    ReportLine,
    ReportTotals,
    UtilisationReportPage,
)


def report_page_response(found: UtilisationReportPage) -> UtilisationReportResponse:
    """Write one page of the report, with its definitions and the totals over every line."""
    report = found.report
    return UtilisationReportResponse(
        from_date=report.starts_on,
        to_date=report.ends_on,
        group_by=report.group_by,
        definitions=ReportDefinitionsResponse(
            utilisation=UTILISATION_DEFINITION,
            gross_contribution=GROSS_CONTRIBUTION_DEFINITION,
        ),
        totals=_totals(report.totals),
        items=[_line(line) for line in found.items],
        page=found.page,
        page_size=found.page_size,
        total=found.total,
    )


def dashboard_response(dashboard: AdminDashboard) -> AdminDashboardResponse:
    """Write the business across every branch today."""
    month = dashboard.month_to_date
    attention = dashboard.attention
    return AdminDashboardResponse(
        business_day=dashboard.business_day,
        branches=[_position(branch) for branch in dashboard.branches],
        totals=_counts(dashboard.totals),
        month_to_date=MonthToDateResponse(
            from_date=month.starts_on,
            to_date=month.ends_on,
            utilisation_percent=month.utilisation_percent,
            gross_contribution=month.gross_contribution,
        ),
        open_damage_reports=attention.open_damage_reports,
        customers_on_hold=attention.customers_on_hold,
        failed_notifications=attention.failed_notifications,
    )


def _line(line: ReportLine) -> ReportLineResponse:
    """Write one line of the report."""
    parts = line.contribution
    return ReportLineResponse(
        key=line.key,
        label=line.label,
        branch_code=line.branch_code,
        category_name=line.category_name,
        model_name=line.model_name,
        asset_tag=line.asset_tag,
        status=line.status,
        asset_count=line.asset_count,
        days_on_hire=line.days_on_hire,
        serviceable_days=line.serviceable_days,
        utilisation_percent=line.utilisation_percent,
        hire_revenue_ex_vat=parts.hire_revenue.amount,
        late_fees_ex_vat=parts.late_fees.amount,
        damage_recovery_ex_vat=parts.damage_recovery.amount,
        repair_costs=parts.repair_costs.amount,
        gross_contribution=parts.gross_contribution.amount,
    )


def _totals(totals: ReportTotals) -> ReportFiguresResponse:
    """Write the figures of every line together."""
    parts = totals.contribution
    return ReportFiguresResponse(
        asset_count=totals.asset_count,
        days_on_hire=totals.days_on_hire,
        serviceable_days=totals.serviceable_days,
        utilisation_percent=totals.utilisation_percent,
        hire_revenue_ex_vat=parts.hire_revenue.amount,
        late_fees_ex_vat=parts.late_fees.amount,
        damage_recovery_ex_vat=parts.damage_recovery.amount,
        repair_costs=parts.repair_costs.amount,
        gross_contribution=parts.gross_contribution.amount,
    )


def _position(branch: BranchPosition) -> BranchPositionResponse:
    """Write where one branch stands today."""
    counts = branch.counts
    return BranchPositionResponse(
        branch_code=branch.branch_code,
        branch_name=branch.branch_name,
        collections_due=counts.collections_due,
        returns_due=counts.returns_due,
        overdue=counts.overdue,
        on_hire=counts.on_hire,
        quarantined=counts.quarantined,
        under_repair=counts.under_repair,
        available=counts.available,
    )


def _counts(counts: BranchCounts) -> BranchCountsResponse:
    """Write what is due and where the units stand."""
    return BranchCountsResponse(
        collections_due=counts.collections_due,
        returns_due=counts.returns_due,
        overdue=counts.overdue,
        on_hire=counts.on_hire,
        quarantined=counts.quarantined,
        under_repair=counts.under_repair,
        available=counts.available,
    )
