"""The report and the admin dashboard as use cases, against fakes of their ports (FR-24, US-33).

These pin what the two add to the figures, which is who may ask, every
refusal of the report's parameters and the parameter it names, the sweep
before anything is read, the scope the query object is asked with and the
month so far on the dashboard. The clock stands still on Sunday the
twentieth of September 2026 at ten in the morning in Cape Town.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Final
from uuid import uuid4

import pytest

from app.application.refusal import refused_parameter_of
from app.application.reporting.dashboard import ReadAdminDashboard
from app.application.reporting.evidence import FleetEvidence
from app.application.reporting.fleet_figures import FleetFigures
from app.application.reporting.read_report import (
    END_NOT_AFTER_START_MESSAGE,
    PERIOD_TOO_LONG_MESSAGE,
    ReadUtilisationReport,
    ReportQuery,
)
from app.application.reporting.report_models import AttentionCounts, GroupBy
from app.domain.enums import UserRole
from app.domain.errors import AuthorisationFailure, ValidationFailure
from app.domain.identity import Actor, Branch
from tests.support.clock import FixedClock
from tests.support.factories import CLOSES_AT
from tests.support.report_fakes import (
    READ,
    SWEEP,
    FakeBranches,
    FakeDashboardCounts,
    FakeFleetReport,
    a_hire,
    a_position,
    a_unit,
)

NOW: Final[datetime] = datetime(2026, 9, 20, 8, 0, tzinfo=UTC)
FIRST: Final[date] = date(2026, 9, 1)
AFTER_SEPTEMBER: Final[date] = date(2026, 10, 1)
CBD: Final[Branch] = Branch(id=uuid4(), code="CBD", name="Cape Town CBD", closes_at=CLOSES_AT)
ADMIN: Final[Actor] = Actor(user_id=uuid4(), role=UserRole.ADMIN, branch_id=None)
COUNTER: Final[Actor] = Actor(user_id=uuid4(), role=UserRole.COUNTER_STAFF, branch_id=CBD.id)
HAMMER = a_unit("TSH-HM-0001", hire_revenue="518.00")


@dataclass
class Desk:
    """The report and the dashboard wired to fakes, with a record of what ran in what order."""

    fleet: FakeFleetReport = field(default_factory=FakeFleetReport)
    counts: FakeDashboardCounts = field(default_factory=FakeDashboardCounts)
    clock: FixedClock = field(default_factory=lambda: FixedClock(NOW))

    def sweep(self) -> Callable[[], object]:
        """Return a sweep that writes down that it ran."""
        return lambda: self.fleet.calls.append(SWEEP)

    def report(self) -> ReadUtilisationReport:
        """Return the report over the fakes."""
        return ReadUtilisationReport(
            FleetFigures(self.fleet, self.clock), self.fleet, FakeBranches((CBD,)), self.sweep()
        )

    def dashboard(self) -> ReadAdminDashboard:
        """Return the dashboard over the fakes."""
        return ReadAdminDashboard(
            self.counts, FleetFigures(self.fleet, self.clock), self.clock, self.sweep()
        )


def september(**changes: object) -> ReportQuery:
    """Return the question for September by an administrator, with any member changed."""
    return replace(ReportQuery(actor=ADMIN, starts_on=FIRST, ends_on=AFTER_SEPTEMBER), **changes)


def refusal_of(desk: Desk, query: ReportQuery) -> tuple[str | None, str]:
    """Return the parameter a refusal named and its sentence."""
    with pytest.raises(ValidationFailure) as refused:
        desk.report().page(query)
    return refused_parameter_of(refused.value), refused.value.message


class TestTheReport:
    """One page, the totals, the scope it was read with and the sweep before it."""

    def test_the_sweep_runs_before_the_fleet_is_read(self) -> None:
        desk = Desk()
        desk.report().page(september())
        assert desk.fleet.calls == [SWEEP, READ]

    def test_the_period_is_read_from_midnight_to_midnight_in_cape_town(self) -> None:
        desk = Desk()
        desk.report().page(september(branch_code="CBD", category_slug="drilling"))
        scope = desk.fleet.scopes[0]
        assert (scope.starts_at, scope.ends_at) == (
            datetime(2026, 8, 31, 22, 0, tzinfo=UTC),
            datetime(2026, 9, 30, 22, 0, tzinfo=UTC),
        )
        assert (scope.branch_id, scope.category_slug, scope.now) == (CBD.id, "drilling", NOW)

    def test_a_page_carries_the_lines_and_the_totals_over_every_line(self) -> None:
        desk = Desk()
        desk.fleet.evidence_to_answer = FleetEvidence(
            units=(HAMMER, a_unit("TSH-HM-0002")),
            dated=(a_hire(HAMMER, date(2026, 9, 2), date(2026, 9, 9)),),
            shared_hire=(),
        )
        page = desk.report().page(september(page=2, page_size=1, group_by=GroupBy.ASSET))
        assert [line.key for line in page.items] == ["TSH-HM-0002"]
        assert page.total == 2
        assert page.report.totals.days_on_hire == 7
        assert page.report.totals.utilisation_percent == Decimal("11.67")

    def test_the_csv_is_every_line(self) -> None:
        desk = Desk()
        desk.fleet.evidence_to_answer = FleetEvidence(
            units=(HAMMER, a_unit("TSH-HM-0002")), dated=(), shared_hire=()
        )
        report = desk.report().everything(september(page=2, page_size=1))
        assert [line.key for line in report.lines] == ["TSH-HM-0001", "TSH-HM-0002"]


class TestTheRefusals:
    """Each refusal names the parameter it refused, and nobody but an administrator gets in."""

    def test_counter_staff_are_refused(self) -> None:
        with pytest.raises(AuthorisationFailure):
            Desk().report().page(september(actor=COUNTER))
        with pytest.raises(AuthorisationFailure):
            Desk().report().everything(september(actor=COUNTER))

    def test_a_period_that_ends_where_it_starts_names_the_end(self) -> None:
        assert refusal_of(Desk(), september(ends_on=FIRST)) == ("to", END_NOT_AFTER_START_MESSAGE)

    def test_a_period_longer_than_a_leap_year_names_the_end(self) -> None:
        query = september(ends_on=date(2027, 9, 3))
        assert refusal_of(Desk(), query) == ("to", PERIOD_TOO_LONG_MESSAGE)

    def test_a_period_of_exactly_366_days_is_answered(self) -> None:
        Desk().report().page(september(ends_on=date(2027, 9, 2)))

    def test_a_page_and_a_page_size_out_of_range_are_named(self) -> None:
        assert refusal_of(Desk(), september(page=0))[0] == "page"
        assert refusal_of(Desk(), september(page_size=101))[0] == "pageSize"

    def test_an_unknown_branch_and_an_unknown_category_are_named(self) -> None:
        assert refusal_of(Desk(), september(branch_code="XYZ"))[0] == "branchCode"
        assert refusal_of(Desk(), september(category_slug="pumps"))[0] == "categorySlug"

    def test_a_refused_question_never_reaches_the_sweep(self) -> None:
        desk = Desk()
        refusal_of(desk, september(category_slug="pumps"))
        assert desk.fleet.calls == []


class TestTheDashboard:
    """Every branch, the totals, the month so far and what waits."""

    def test_the_branches_are_added_up(self) -> None:
        desk = Desk()
        desk.counts.positions = (
            a_position("CBD", collections_due=2, on_hire=14, available=120),
            a_position("BLV", collections_due=3, overdue=1, under_repair=1, available=230),
        )
        dashboard = desk.dashboard().read(ADMIN)
        totals = dashboard.totals
        assert (totals.collections_due, totals.overdue, totals.on_hire) == (5, 1, 14)
        assert (totals.under_repair, totals.available) == (1, 350)
        assert desk.counts.days_asked == [date(2026, 9, 20)]

    def test_the_month_so_far_runs_from_the_first_to_the_end_of_today(self) -> None:
        desk = Desk()
        desk.fleet.evidence_to_answer = FleetEvidence(
            units=(HAMMER,),
            dated=(a_hire(HAMMER, date(2026, 9, 2), date(2026, 9, 9)),),
            shared_hire=(),
        )
        month = desk.dashboard().read(ADMIN).month_to_date
        assert (month.starts_on, month.ends_on) == (FIRST, date(2026, 9, 21))
        assert month.utilisation_percent == Decimal("35.00")
        assert month.gross_contribution == Decimal("518.00")

    def test_what_waits_is_passed_on(self) -> None:
        desk = Desk()
        desk.counts.attention = AttentionCounts(
            open_damage_reports=3, customers_on_hold=1, failed_notifications=2
        )
        assert desk.dashboard().read(ADMIN).attention == desk.counts.attention

    def test_the_sweep_runs_first_and_counter_staff_are_refused(self) -> None:
        desk = Desk()
        desk.dashboard().read(ADMIN)
        assert desk.fleet.calls == [SWEEP, READ]
        with pytest.raises(AuthorisationFailure):
            desk.dashboard().read(COUNTER)
