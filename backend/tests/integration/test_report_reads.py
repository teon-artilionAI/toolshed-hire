"""The report's reads stand on their indexes and do not grow with the fleet, on PostgreSQL.

Each statement the report and the admin dashboard issue is counted with the
fleet of the worked dataset and again with twenty more units each hired, and
the count does not move. Then each condition the report reads a period by is
explained with sequential scans switched off, which shows whether it matches
the index revision 0007 built for it. On a database this small the planner
would otherwise read every table from end to end. Every value in an explained
statement is bound, except the action of an audit event, which the report
writes as the literal the partial index is filtered on.
"""

from __future__ import annotations

from datetime import date, time
from typing import Final

import pytest
from sqlalchemy import Engine, text
from sqlmodel import Session

from app.application.reporting.evidence import ReportScope
from app.domain.enums import ConditionGrade, ReleaseReason, ReservationStatus, UserRole
from app.domain.period import BookingPeriod
from app.infrastructure.admin_dashboard import SqlAdminDashboard
from app.infrastructure.fleet_report import SqlFleetReport
from app.infrastructure.schema_ddl import (
    AUDIT_STATUS_CHANGE_INDEX,
    CHARGE_RAISED_INDEX,
    DAMAGE_REPORT_RESOLVED_INDEX,
    RENTAL_ITEM_LOST_INDEX,
    RENTAL_ITEM_RETURNED_INDEX,
)
from tests.support.factories import Factory
from tests.support.report_dataset import (
    NOW,
    OCTOBER_FIRST,
    SEPTEMBER_FIRST,
    build_report_dataset,
)
from tests.support.report_pg import FleetBuilder, Line, cape_town
from tests.support.statements import recorded_statements

pytestmark = pytest.mark.postgres

REPORT_STATEMENTS: Final[int] = 3
DASHBOARD_STATEMENTS: Final[int] = 2
MORE_UNITS: Final[int] = 20
EXPLAIN_PREFIX: Final[str] = "EXPLAIN "
MIDNIGHT: Final[time] = time(0, 0)
ONE_LOSS: Final[str] = (
    "UPDATE rental_item SET condition_in = NULL WHERE id = "
    "(SELECT id FROM rental_item WHERE returned_at IS NOT NULL ORDER BY id LIMIT 1)"
)
SCOPE: Final[ReportScope] = ReportScope(
    starts_on=SEPTEMBER_FIRST,
    ends_on=OCTOBER_FIRST,
    starts_at=cape_town(SEPTEMBER_FIRST, MIDNIGHT),
    ends_at=cape_town(OCTOBER_FIRST, MIDNIGHT),
    now=NOW,
)
CHARGES_OF_A_PERIOD: Final[str] = (
    "SELECT id FROM charge WHERE raised_at >= :starts AND raised_at < :ends"
)
HIRES_TOUCHING_A_PERIOD: Final[str] = (
    "SELECT id FROM rental_item WHERE returned_at IS NULL OR returned_at >= :starts"
)
LOSSES_BEFORE_ITS_END: Final[str] = (
    "SELECT id FROM rental_item WHERE returned_at IS NOT NULL AND condition_in IS NULL "
    "AND returned_at < :ends"
)
REPORTS_TOUCHING_A_PERIOD: Final[str] = (
    "SELECT id FROM damage_report WHERE resolved_at IS NULL OR resolved_at >= :starts"
)
LAST_CHANGE_BEFORE_A_PERIOD: Final[str] = (
    "SELECT after_state FROM audit_event WHERE action = 'asset.status_changed' "
    "AND entity_id = :unit AND occurred_at < :starts ORDER BY occurred_at DESC LIMIT 1"
)


def more_hired_units(session: Session, factory: Factory) -> None:
    """Commit twenty more units at a branch of their own, each hired once in September."""
    branch = factory.branch(name="Somerset West")
    model = factory.product_model(name="Plate Compactor")
    build = FleetBuilder(
        factory, factory.user(role=UserRole.ADMIN), factory.customer_profile(branch=branch)
    )
    period = BookingPeriod(date(2026, 9, 7), date(2026, 9, 10))
    for number in range(MORE_UNITS):
        unit = build.unit(f"TSH-PC-{number:04d}", model, branch, acquired_on=date(2025, 1, 1))
        booking = build.booking(
            branch,
            period,
            [Line(model, [unit])],
            status=ReservationStatus.RETURNED,
            released=ReleaseReason.RETURNED,
        )
        build.rental(
            booking, out=period.start, returns={unit.id: (cape_town(period.end), ConditionGrade.A)}
        )
    session.commit()


def counted(engine: Engine, session: Session) -> tuple[int, int]:
    """Return how many statements the report and the dashboard each sent."""
    with recorded_statements(engine) as report:
        SqlFleetReport(session).evidence(SCOPE)
    with recorded_statements(engine) as dashboard:
        counts = SqlAdminDashboard(session)
        counts.branch_positions(NOW.date())
        counts.attention_counts()
    return len(report), len(dashboard)


def plan_of(session: Session, statement: str, **params: object) -> str:
    """Return the plan of a statement with sequential scans switched off, to see the choice."""
    session.execute(text("SET LOCAL enable_seqscan = off"))
    plan = session.execute(text(EXPLAIN_PREFIX + statement), params).all()
    return "\n".join(str(row[0]) for row in plan)


class TestTheStatementsDoNotGrowWithTheFleet:
    """Three statements for the report and two for the dashboard, however many units."""

    def test_the_count_is_the_same_with_twenty_more_units(
        self, postgres_engine: Engine, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        build_report_dataset(postgres_session, postgres_factory)
        before = counted(postgres_engine, postgres_session)
        more_hired_units(postgres_session, postgres_factory)
        after = counted(postgres_engine, postgres_session)
        assert before == after == (REPORT_STATEMENTS, DASHBOARD_STATEMENTS)
        assert len(SqlFleetReport(postgres_session).evidence(SCOPE).units) == 7 + MORE_UNITS


class TestEachConditionStandsOnItsIndex:
    """The planner can answer each condition of a period from the index written for it."""

    def test_the_charges_of_a_period_are_found_by_when_they_were_raised(
        self, postgres_session: Session
    ) -> None:
        plan = plan_of(
            postgres_session, CHARGES_OF_A_PERIOD, starts=SCOPE.starts_at, ends=SCOPE.ends_at
        )
        assert CHARGE_RAISED_INDEX in plan, plan

    def test_the_hires_out_or_back_since_the_start_are_found_by_their_return(
        self, postgres_session: Session
    ) -> None:
        plan = plan_of(postgres_session, HIRES_TOUCHING_A_PERIOD, starts=SCOPE.starts_at)
        assert RENTAL_ITEM_RETURNED_INDEX in plan, plan

    def test_the_losses_are_found_in_an_index_that_holds_nothing_else(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        more_hired_units(postgres_session, postgres_factory)
        postgres_session.execute(text(ONE_LOSS))
        postgres_session.execute(text("ANALYZE rental_item"))
        plan = plan_of(postgres_session, LOSSES_BEFORE_ITS_END, ends=SCOPE.ends_at)
        assert RENTAL_ITEM_LOST_INDEX in plan, plan

    def test_the_reports_open_or_resolved_since_the_start_are_found_by_their_resolution(
        self, postgres_session: Session
    ) -> None:
        plan = plan_of(postgres_session, REPORTS_TOUCHING_A_PERIOD, starts=SCOPE.starts_at)
        assert DAMAGE_REPORT_RESOLVED_INDEX in plan, plan

    def test_the_last_change_of_a_unit_before_the_period_is_one_entry_of_its_index(
        self, postgres_session: Session, postgres_factory: Factory
    ) -> None:
        unit = postgres_factory.asset(
            product_model=postgres_factory.product_model(), branch=postgres_factory.branch()
        )
        postgres_session.commit()
        plan = plan_of(
            postgres_session, LAST_CHANGE_BEFORE_A_PERIOD, unit=unit.id, starts=SCOPE.starts_at
        )
        assert AUDIT_STATUS_CHANGE_INDEX in plan, plan
