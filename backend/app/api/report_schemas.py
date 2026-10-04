"""Response models for the utilisation report and the admin dashboard.

Field names on the wire are camelCase, as everywhere else at this boundary.
Money is a string with two decimals and a date is `YYYY-MM-DD`. A percentage
is a string with two decimals as well, and it is null when there was no
serviceable day to measure it against.

Every figure here is called gross contribution and never profit, because the
system holds none of the costs that would make it one. The two definitions
travel with every report, so a screen shows them beside the figures.
"""

from __future__ import annotations

from datetime import date
from typing import Final

from pydantic import ConfigDict, Field

from app.api.catalogue_schemas import Money, Percentage
from app.api.schemas import CamelModel, ProblemDetail
from app.application.reporting.report_models import GroupBy
from app.domain.enums import AssetStatus

ADMIN_ONLY_RESPONSE: Final[dict[str, object]] = {
    "model": ProblemDetail,
    "description": "The caller is not an administrator.",
}
CSV_RESPONSE: Final[dict[str, object]] = {
    "description": (
        "Every line of the report as CSV, streamed. The first line says the figures are "
        "gross contribution and not profit, and repeats the two definitions."
    ),
    "content": {"text/csv": {"schema": {"type": "string"}}},
}


class ReportDefinitionsResponse(CamelModel):
    """The two definitions every figure of the report is read by."""

    utilisation: str
    gross_contribution: str = Field(serialization_alias="grossContribution")


class ReportFiguresResponse(CamelModel):
    """The figures of a line of the report, or of every line together."""

    asset_count: int = Field(serialization_alias="assetCount")
    days_on_hire: int = Field(serialization_alias="daysOnHire")
    serviceable_days: int = Field(serialization_alias="serviceableDays")
    utilisation_percent: Percentage | None = Field(serialization_alias="utilisationPercent")
    hire_revenue_ex_vat: Money = Field(serialization_alias="hireRevenueExVat")
    late_fees_ex_vat: Money = Field(serialization_alias="lateFeesExVat")
    damage_recovery_ex_vat: Money = Field(serialization_alias="damageRecoveryExVat")
    repair_costs: Money = Field(serialization_alias="repairCosts")
    gross_contribution: Money = Field(serialization_alias="grossContribution")


class ReportLineResponse(ReportFiguresResponse):
    """One line of the report, for an asset, a model, a category or a branch.

    `assetTag` and `status` are set on a line for an asset. `branchCode` is set
    on a line for an asset or a branch, `categoryName` on a line for an asset,
    a model or a category, and `modelName` on a line for an asset or a model.
    """

    key: str
    label: str
    branch_code: str | None = Field(serialization_alias="branchCode")
    category_name: str | None = Field(serialization_alias="categoryName")
    model_name: str | None = Field(serialization_alias="modelName")
    asset_tag: str | None = Field(serialization_alias="assetTag")
    status: AssetStatus | None

    # `model_name` is the documented name and collides with nothing.
    model_config = ConfigDict(protected_namespaces=())


class UtilisationReportResponse(CamelModel):
    """One page of the report, highest gross contribution first, with the totals over every line."""

    from_date: date = Field(serialization_alias="from")
    to_date: date = Field(serialization_alias="to")
    group_by: GroupBy = Field(serialization_alias="groupBy")
    definitions: ReportDefinitionsResponse
    totals: ReportFiguresResponse
    items: list[ReportLineResponse]
    page: int
    page_size: int = Field(serialization_alias="pageSize")
    total: int


class BranchCountsResponse(CamelModel):
    """What is due today and where the units stand, at a branch or across every branch."""

    collections_due: int = Field(serialization_alias="collectionsDue")
    returns_due: int = Field(serialization_alias="returnsDue")
    overdue: int
    on_hire: int = Field(serialization_alias="onHire")
    quarantined: int
    under_repair: int = Field(serialization_alias="underRepair")
    available: int


class BranchPositionResponse(BranchCountsResponse):
    """Where one trading branch stands today."""

    branch_code: str = Field(serialization_alias="branchCode")
    branch_name: str = Field(serialization_alias="branchName")


class MonthToDateResponse(CamelModel):
    """Utilisation and gross contribution from the first of the month to the end of today."""

    from_date: date = Field(serialization_alias="from")
    to_date: date = Field(serialization_alias="to")
    utilisation_percent: Percentage | None = Field(serialization_alias="utilisationPercent")
    gross_contribution: Money = Field(serialization_alias="grossContribution")


class AdminDashboardResponse(CamelModel):
    """The business across every branch today."""

    business_day: date = Field(serialization_alias="date")
    branches: list[BranchPositionResponse]
    totals: BranchCountsResponse
    month_to_date: MonthToDateResponse = Field(serialization_alias="monthToDate")
    open_damage_reports: int = Field(serialization_alias="openDamageReports")
    customers_on_hold: int = Field(serialization_alias="customersOnHold")
    failed_notifications: int = Field(serialization_alias="failedNotifications")
