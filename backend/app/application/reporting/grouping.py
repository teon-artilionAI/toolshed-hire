"""Grouping the figures of each unit into the lines of the report, ranking them and paging them.

A line for a model, a category or a branch adds up the day counts and the
four parts of gross contribution of its units, and its utilisation and its
gross contribution are worked out from those sums by the domain, so a line is
never an average of percentages. The totals are the same sums over every
unit, not only the page.

Lines are ranked by gross contribution, highest first, and two lines with the
same figure by their key, so the order never changes between two reads of the
same data and a page boundary never moves.

This is done in memory, which costs nothing at four hundred units. The README
says what degrades first as the fleet grows and how it would move into the
database.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from types import MappingProxyType
from typing import Final

from app.application.catalogue.read_models import FIRST_PAGE
from app.application.reporting.evidence import UnitRow
from app.application.reporting.report_models import (
    GroupBy,
    ReportLine,
    ReportTotals,
    UtilisationReport,
    UtilisationReportPage,
)
from app.application.reporting.unit_figures import UnitFigures
from app.domain.contribution import Contribution
from app.domain.utilisation import utilisation_percent

# What a unit is grouped by, for each kind of line.
_KEY_OF: Final[Mapping[GroupBy, Callable[[UnitRow], str]]] = MappingProxyType(
    {
        GroupBy.ASSET: lambda unit: unit.asset_tag,
        GroupBy.MODEL: lambda unit: unit.model_slug,
        GroupBy.CATEGORY: lambda unit: unit.category_slug,
        GroupBy.BRANCH: lambda unit: unit.branch_code,
    }
)


def report_lines(figures: Sequence[UnitFigures], group_by: GroupBy) -> tuple[ReportLine, ...]:
    """Return one line for each asset, model, category or branch, highest contribution first."""
    groups: dict[str, list[UnitFigures]] = {}
    key_of = _KEY_OF[group_by]
    for figure in figures:
        groups.setdefault(key_of(figure.unit), []).append(figure)
    lines = [_line_of(key, members, group_by) for key, members in groups.items()]
    return tuple(sorted(lines, key=_ranking))


def totals_of(figures: Sequence[UnitFigures]) -> ReportTotals:
    """Return the figures of every unit together."""
    days_on_hire, serviceable_days, contribution = _summed(figures)
    return ReportTotals(
        asset_count=len(figures),
        days_on_hire=days_on_hire,
        serviceable_days=serviceable_days,
        utilisation_percent=utilisation_percent(days_on_hire, serviceable_days),
        contribution=contribution,
    )


def page_of(report: UtilisationReport, page: int, page_size: int) -> UtilisationReportPage:
    """Return one page of the lines of a report, counted from one."""
    first = (page - FIRST_PAGE) * page_size
    return UtilisationReportPage(
        report=report,
        items=report.lines[first : first + page_size],
        page=page,
        page_size=page_size,
    )


def _line_of(key: str, members: Sequence[UnitFigures], group_by: GroupBy) -> ReportLine:
    """Return the line of one group, its units added up."""
    unit = members[0].unit
    days_on_hire, serviceable_days, contribution = _summed(members)
    is_asset = group_by is GroupBy.ASSET
    return ReportLine(
        key=key,
        label=_label_of(unit, group_by),
        branch_code=unit.branch_code if group_by in {GroupBy.ASSET, GroupBy.BRANCH} else None,
        category_name=(
            unit.category_name
            if group_by in {GroupBy.ASSET, GroupBy.MODEL, GroupBy.CATEGORY}
            else None
        ),
        model_name=unit.model_name if group_by in {GroupBy.ASSET, GroupBy.MODEL} else None,
        asset_tag=unit.asset_tag if is_asset else None,
        status=unit.status if is_asset else None,
        asset_count=len(members),
        days_on_hire=days_on_hire,
        serviceable_days=serviceable_days,
        utilisation_percent=utilisation_percent(days_on_hire, serviceable_days),
        contribution=contribution,
    )


def _label_of(unit: UnitRow, group_by: GroupBy) -> str:
    """Return the name a reader knows a line by."""
    labels = {
        GroupBy.ASSET: unit.asset_tag,
        GroupBy.MODEL: unit.model_name,
        GroupBy.CATEGORY: unit.category_name,
        GroupBy.BRANCH: unit.branch_name,
    }
    return labels[group_by]


def _summed(figures: Sequence[UnitFigures]) -> tuple[int, int, Contribution]:
    """Return the days on hire, the serviceable days and the contribution of units together."""
    contribution = Contribution.nothing()
    for figure in figures:
        contribution = contribution.plus(figure.contribution)
    return (
        sum(figure.days.days_on_hire for figure in figures),
        sum(figure.days.serviceable_days for figure in figures),
        contribution,
    )


def _ranking(line: ReportLine) -> tuple[Decimal, str]:
    """Return what a line is ranked by, highest gross contribution first and then its key."""
    return (-line.contribution.gross_contribution.amount, line.key)
