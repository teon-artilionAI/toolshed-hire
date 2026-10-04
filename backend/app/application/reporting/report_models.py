"""What the utilisation report and the admin dashboard are answered with.

A report is one line for each asset, model, category or branch, highest gross
contribution first, and the totals over every line, not only the page. Money
stays `Contribution` and `Money` until the HTTP boundary writes it (BR-22).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Final

from app.domain.contribution import Contribution
from app.domain.enums import AssetStatus

NONE_COUNTED: Final[int] = 0


class GroupBy(str, Enum):
    """What one line of the report stands for."""

    ASSET = "asset"
    MODEL = "model"
    CATEGORY = "category"
    BRANCH = "branch"


@dataclass(frozen=True, slots=True)
class ReportLine:
    """One line of the report, for one asset, model, category or branch.

    Attributes:
        key: What the line stands for, the asset tag, the model slug, the
            category slug or the branch code.
        label: The name a reader knows it by.
        branch_code: The branch, on a line for a unit or a branch.
        category_name: The category, on a line for a unit, a model or a category.
        model_name: The model, on a line for a unit or a model.
        asset_tag: The tag, on a line for a unit.
        status: The status now, on a line for a unit.
        asset_count: How many units the line covers.
        days_on_hire: Their days on hire, added up.
        serviceable_days: Their serviceable days, added up.
        utilisation_percent: The first over the second as a percentage, or
            None when there was no serviceable day.
        contribution: Their four parts of gross contribution, added up.

    """

    key: str
    label: str
    branch_code: str | None
    category_name: str | None
    model_name: str | None
    asset_tag: str | None
    status: AssetStatus | None
    asset_count: int
    days_on_hire: int
    serviceable_days: int
    utilisation_percent: Decimal | None
    contribution: Contribution


@dataclass(frozen=True, slots=True)
class ReportTotals:
    """The figures of every line of a report together.

    Attributes:
        asset_count: How many units the report covers.
        days_on_hire: Their days on hire, added up.
        serviceable_days: Their serviceable days, added up.
        utilisation_percent: The first over the second, or None.
        contribution: Their four parts of gross contribution, added up.

    """

    asset_count: int
    days_on_hire: int
    serviceable_days: int
    utilisation_percent: Decimal | None
    contribution: Contribution


@dataclass(frozen=True, slots=True)
class UtilisationReport:
    """Every line of a report, highest gross contribution first, with the totals.

    Attributes:
        starts_on: The first day of the period.
        ends_on: The first day after it.
        group_by: What each line stands for.
        lines: Every line.
        totals: The figures of every line together.

    """

    starts_on: date
    ends_on: date
    group_by: GroupBy
    lines: tuple[ReportLine, ...]
    totals: ReportTotals


@dataclass(frozen=True, slots=True)
class UtilisationReportPage:
    """One page of the lines of a report, with the totals over every line.

    Attributes:
        report: The report, every line of it.
        items: The lines on this page.
        page: The page, counted from one.
        page_size: How many lines a page holds.

    """

    report: UtilisationReport
    items: tuple[ReportLine, ...]
    page: int
    page_size: int

    @property
    def total(self) -> int:
        """Return how many lines the report has, on every page."""
        return len(self.report.lines)


@dataclass(frozen=True, slots=True)
class BranchCounts:
    """What is due and where the units stand, at one branch or across them.

    The first three are counted the way the counter's dashboard counts them.

    Attributes:
        collections_due: Confirmed bookings whose hire has started.
        returns_due: Hires due back today with a unit still out.
        overdue: Hires due back before today with a unit still out.
        on_hire: Units out on hire.
        quarantined: Units in quarantine.
        under_repair: Units under repair.
        available: Units on the shelf.

    """

    collections_due: int
    returns_due: int
    overdue: int
    on_hire: int
    quarantined: int
    under_repair: int
    available: int

    @classmethod
    def none(cls) -> BranchCounts:
        """Return counts that are all nought."""
        return cls(
            collections_due=NONE_COUNTED,
            returns_due=NONE_COUNTED,
            overdue=NONE_COUNTED,
            on_hire=NONE_COUNTED,
            quarantined=NONE_COUNTED,
            under_repair=NONE_COUNTED,
            available=NONE_COUNTED,
        )

    def plus(self, other: BranchCounts) -> BranchCounts:
        """Return these counts and another's added together."""
        return BranchCounts(
            collections_due=self.collections_due + other.collections_due,
            returns_due=self.returns_due + other.returns_due,
            overdue=self.overdue + other.overdue,
            on_hire=self.on_hire + other.on_hire,
            quarantined=self.quarantined + other.quarantined,
            under_repair=self.under_repair + other.under_repair,
            available=self.available + other.available,
        )


@dataclass(frozen=True, slots=True)
class BranchPosition:
    """Where one branch stands today.

    Attributes:
        branch_code: The branch code.
        branch_name: The branch name.
        counts: What is due there and where its units stand.

    """

    branch_code: str
    branch_name: str
    counts: BranchCounts


@dataclass(frozen=True, slots=True)
class AttentionCounts:
    """What across the business waits for an administrator.

    Attributes:
        open_damage_reports: Reports open or under repair.
        customers_on_hold: Customer accounts on hold.
        failed_notifications: Messages that could not be sent.

    """

    open_damage_reports: int
    customers_on_hold: int
    failed_notifications: int


@dataclass(frozen=True, slots=True)
class MonthToDate:
    """Utilisation and gross contribution from the first of the month to the end of today.

    Attributes:
        starts_on: The first day of the month.
        ends_on: Tomorrow, so today is counted in full.
        utilisation_percent: Across every branch, or None.
        gross_contribution: Across every branch, to the cent.

    """

    starts_on: date
    ends_on: date
    utilisation_percent: Decimal | None
    gross_contribution: Decimal


@dataclass(frozen=True, slots=True)
class AdminDashboard:
    """The business across every branch today.

    Attributes:
        business_day: Today, in Cape Town.
        branches: Each trading branch.
        totals: The branches added up.
        month_to_date: The report's two figures for the month so far.
        attention: What waits for an administrator.

    """

    business_day: date
    branches: tuple[BranchPosition, ...]
    totals: BranchCounts
    month_to_date: MonthToDate
    attention: AttentionCounts
