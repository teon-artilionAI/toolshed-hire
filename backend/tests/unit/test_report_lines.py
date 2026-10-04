"""The figures of each unit and the lines of the report, from evidence built by hand.

These pin what the application layer makes of the rows a query object reads,
with no database. The period is September 2026 and today is the twentieth.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Final
from uuid import uuid4

from app.application.reporting.evidence import DatedRow, EvidenceKind, FleetEvidence
from app.application.reporting.grouping import page_of, report_lines, totals_of
from app.application.reporting.report_models import GroupBy, UtilisationReport
from app.application.reporting.unit_figures import UnitFigures, figures_of, hire_shares
from app.domain.enums import AssetStatus
from app.domain.money import Money
from app.domain.report_days import DaySpan
from tests.support.report_fakes import (
    a_booking,
    a_change,
    a_fact,
    a_hire,
    a_unit,
    shared,
)

SEPTEMBER: Final[DaySpan] = DaySpan(date(2026, 9, 1), date(2026, 10, 1))
TODAY: Final[date] = date(2026, 9, 20)


def day(number: int) -> date:
    """Return a day of September 2026."""
    return date(2026, 9, number)


def rand(text: str) -> Money:
    """Return an amount of money from its text."""
    return Money.create(text)


HAMMER_ONE = a_unit("TSH-HM-0001", hire_revenue="518.00")
HAMMER_TWO = a_unit("TSH-HM-0002", late_fees="208.70")
MIXER = a_unit(
    "TSH-MX-0001",
    model="mixer",
    category="concrete",
    damage_recovery="400.00",
    repair_costs="350.00",
)
HAMMER_AWAY = a_unit("TSH-HM-0003", branch="BLV", repair_costs="180.00")
DRILL_IN_INTAKE = a_unit(
    "TSH-DR-0002", model="drill", branch="BLV", status=AssetStatus.INTAKE, acquired_on=day(18)
)
CHARGE = uuid4()
EVIDENCE: Final[FleetEvidence] = FleetEvidence(
    units=(HAMMER_ONE, HAMMER_TWO, MIXER, HAMMER_AWAY, DRILL_IN_INTAKE),
    dated=(
        a_hire(HAMMER_ONE, day(2), day(9)),
        a_hire(HAMMER_ONE, day(18)),
        a_hire(HAMMER_TWO, day(2), day(11)),
        a_hire(MIXER, day(2), day(9)),
        a_change(MIXER, day(9), AssetStatus.ON_HIRE, AssetStatus.QUARANTINED),
        a_change(MIXER, day(14), AssetStatus.UNDER_REPAIR, AssetStatus.AVAILABLE),
        a_fact(MIXER, EvidenceKind.DAMAGE, day(10), day(14)),
        a_fact(HAMMER_AWAY, EvidenceKind.DAMAGE, day(5), day(12)),
        a_booking(HAMMER_AWAY, day(15), day(18)),
    ),
    shared_hire=(
        shared(CHARGE, "725.25", HAMMER_ONE, "425.25", 2),
        shared(CHARGE, "725.25", HAMMER_TWO, "425.25", 2),
        shared(CHARGE, "725.25", MIXER, "300.00", 1),
    ),
)


def figures() -> tuple[UnitFigures, ...]:
    """Return the figures of the five units of the evidence."""
    return figures_of(EVIDENCE, SEPTEMBER, TODAY)


def by_tag() -> dict[str, UnitFigures]:
    """Return the figures of each unit by its tag."""
    return {figure.unit.asset_tag: figure for figure in figures()}


class TestEachUnit:
    """Each unit's days and money, put together from its facts."""

    def test_the_days_of_each_unit(self) -> None:
        counted = {
            tag: (figure.days.days_on_hire, figure.days.serviceable_days)
            for tag, figure in by_tag().items()
        }
        assert counted == {
            "TSH-HM-0001": (10, 30),
            "TSH-HM-0002": (9, 30),
            "TSH-MX-0001": (7, 25),
            "TSH-HM-0003": (3, 23),
            "TSH-DR-0002": (0, 0),
        }

    def test_each_unit_is_given_its_share_of_the_whole_hire(self) -> None:
        assert hire_shares(EVIDENCE.shared_hire) == {
            HAMMER_ONE.asset_id: rand("212.63"),
            HAMMER_TWO.asset_id: rand("212.63"),
            MIXER.asset_id: rand("299.99"),
        }

    def test_the_share_is_added_to_the_hire_charged_on_the_unit_alone(self) -> None:
        assert by_tag()["TSH-HM-0001"].contribution.hire_revenue == rand("730.63")
        assert by_tag()["TSH-MX-0001"].contribution.gross_contribution == rand("349.99")

    def test_a_fact_with_nothing_to_date_it_by_is_passed_over(self) -> None:
        undated = FleetEvidence(
            units=(HAMMER_ONE,),
            dated=(
                a_hire(HAMMER_ONE, day(2), day(5)),
                DatedRow(asset_id=HAMMER_ONE.asset_id, kind=EvidenceKind.STATUS),
                DatedRow(asset_id=HAMMER_ONE.asset_id, kind=EvidenceKind.HIRE),
                DatedRow(asset_id=HAMMER_ONE.asset_id, kind=EvidenceKind.BOOKING),
            ),
            shared_hire=(),
        )
        assert figures_of(undated, SEPTEMBER, TODAY)[0].days.days_on_hire == 3


class TestTheLines:
    """Lines add their units up and are ranked by gross contribution."""

    def test_a_line_for_each_unit_highest_contribution_first(self) -> None:
        lines = report_lines(figures(), GroupBy.ASSET)
        assert [(line.key, line.contribution.gross_contribution) for line in lines] == [
            ("TSH-HM-0001", rand("730.63")),
            ("TSH-HM-0002", rand("421.33")),
            ("TSH-MX-0001", rand("349.99")),
            ("TSH-DR-0002", rand("0.00")),
            ("TSH-HM-0003", rand("-180.00")),
        ]

    def test_a_line_for_a_unit_says_what_and_where_it_is(self) -> None:
        line = report_lines(figures(), GroupBy.ASSET)[0]
        assert (line.label, line.asset_tag, line.branch_code, line.status) == (
            "TSH-HM-0001",
            "TSH-HM-0001",
            "CBD",
            AssetStatus.AVAILABLE,
        )
        assert (line.model_name, line.category_name) == ("Hammer", "Drilling")
        assert line.utilisation_percent == Decimal("33.33")

    def test_a_line_for_a_model_adds_its_units_up(self) -> None:
        hammers = report_lines(figures(), GroupBy.MODEL)[0]
        assert (hammers.key, hammers.label, hammers.asset_count) == ("hammer", "Hammer", 3)
        assert (hammers.days_on_hire, hammers.serviceable_days) == (22, 83)
        assert hammers.utilisation_percent == Decimal("26.51")
        assert hammers.contribution.gross_contribution == rand("971.96")
        assert (hammers.branch_code, hammers.asset_tag, hammers.status) == (None, None, None)

    def test_a_line_for_a_category_and_for_a_branch(self) -> None:
        categories = report_lines(figures(), GroupBy.CATEGORY)
        assert [(line.key, line.label, line.model_name) for line in categories] == [
            ("drilling", "Drilling", None),
            ("concrete", "Concrete", None),
        ]
        branches = report_lines(figures(), GroupBy.BRANCH)
        assert [(line.key, line.label, line.category_name) for line in branches] == [
            ("CBD", "Branch CBD", None),
            ("BLV", "Branch BLV", None),
        ]

    def test_a_line_with_no_serviceable_day_has_no_utilisation(self) -> None:
        drills = [line for line in report_lines(figures(), GroupBy.MODEL) if line.key == "drill"]
        assert drills[0].utilisation_percent is None

    def test_the_totals_cover_every_unit(self) -> None:
        totals = totals_of(figures())
        assert (totals.asset_count, totals.days_on_hire, totals.serviceable_days) == (5, 29, 108)
        assert totals.utilisation_percent == Decimal("26.85")
        assert totals.contribution.gross_contribution == rand("1321.95")


class TestThePages:
    """A page is a slice of the ranked lines, and the totals stay over every line."""

    def test_the_second_page_of_two_lines(self) -> None:
        lines = report_lines(figures(), GroupBy.ASSET)
        report = UtilisationReport(
            starts_on=SEPTEMBER.begins,
            ends_on=SEPTEMBER.ends,
            group_by=GroupBy.ASSET,
            lines=lines,
            totals=totals_of(figures()),
        )
        page = page_of(report, 2, 2)
        assert [line.key for line in page.items] == ["TSH-MX-0001", "TSH-DR-0002"]
        assert (page.page, page.page_size, page.total) == (2, 2, 5)
