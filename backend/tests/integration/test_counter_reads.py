"""The counter's dashboard, diary and asset locator on PostgreSQL (FR-15, FR-16).

The rows are built with the factories, in `tests/support/counter_pg.py`, so
every status a read has to tell apart is there. These pin what each read finds
against real rows, and that each issues the same number of statements however
many rows it finds. The dashboard is six statements, the diary four and the
locator two. The sweep, the account and the branch that the two routes read
first are counted with them through the route, at the foot of the file.

That the planner can answer each statement from its index is in
tests/integration/test_counter_read_indexes.py. The business day is Monday the
second of March 2026.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from app.application.catalogue.locator import AssetSearch
from app.application.hire.overview_models import DashboardRows
from app.domain.enums import ReservationStatus
from app.infrastructure.asset_locator import SqlAssetLocator
from app.infrastructure.counter_overview import SqlCounterOverview
from tests.support.booking_api import BookingClient
from tests.support.counter_api import read_dashboard, read_diary
from tests.support.counter_pg import HAMMER, ONE_DAY, TODAY, Counter, build_counter
from tests.support.factories import Factory
from tests.support.statements import recorded_statements

pytestmark = pytest.mark.postgres

LIST_LIMIT: Final[int] = 50
DASHBOARD_STATEMENTS: Final[int] = 6
DIARY_STATEMENTS: Final[int] = 4
LOCATOR_STATEMENTS: Final[int] = 2
MORE_ROWS: Final[int] = 6


@pytest.fixture
def counter(postgres_session: Session, postgres_factory: Factory) -> Counter:
    """Return a committed branch with collections, returns, an overdue hire and a quarantine."""
    return build_counter(postgres_session, postgres_factory)


def dashboard_of(session: Session, counter: Counter) -> DashboardRows:
    """Read the dashboard of the counter's branch for today."""
    return SqlCounterOverview(session).dashboard(counter.branch_id, TODAY, LIST_LIMIT)


class TestTheDashboardAgainstRealRows:
    """Every list and every count, from rows in every state."""

    def test_the_counts_are_the_true_totals_at_the_branch(
        self, postgres_session: Session, counter: Counter
    ) -> None:
        counts = dashboard_of(postgres_session, counter).counts
        assert (counts.collections_due, counts.returns_due, counts.overdue) == (2, 1, 1)
        assert (counts.on_hire, counts.quarantined) == (2, 1)

    def test_the_lists_hold_what_is_due_and_nothing_else(
        self, postgres_session: Session, counter: Counter
    ) -> None:
        rows = dashboard_of(postgres_session, counter)
        assert [entry.start_date for entry in rows.collections_due] == [TODAY - ONE_DAY, TODAY]
        assert [entry.unit_count for entry in rows.collections_due] == [1, 2]
        (returning,) = rows.returns_due
        assert (returning.items_out, returning.item_count) == (1, 2)
        assert returning.summary == f"2 x {HAMMER}"
        (overdue,) = rows.overdue
        assert overdue.due_back_on == TODAY - 2 * ONE_DAY
        assert overdue.fees_per_day_of_units_out() == (Decimal("120.00"),)

    def test_each_list_is_capped_and_its_count_is_not(
        self, postgres_session: Session, counter: Counter
    ) -> None:
        for _ in range(LIST_LIMIT):
            counter.booked(TODAY, units=0)
        postgres_session.commit()
        rows = dashboard_of(postgres_session, counter)
        assert len(rows.collections_due) == LIST_LIMIT
        assert rows.counts.collections_due == LIST_LIMIT + 2


class TestTheDiaryAgainstRealRows:
    """The collections in four statuses and every hire due back, day by day."""

    def test_a_run_of_days_finds_its_collections_and_its_returns(
        self, postgres_session: Session, counter: Counter
    ) -> None:
        rows = SqlCounterOverview(postgres_session).diary(
            counter.branch_id, TODAY - 3 * ONE_DAY, TODAY + ONE_DAY
        )
        assert [entry.start_date for entry in rows.collections] == [
            TODAY - 3 * ONE_DAY,
            TODAY - ONE_DAY,
            TODAY,
            TODAY + ONE_DAY,
        ]
        assert {entry.status for entry in rows.collections} == {
            ReservationStatus.CONFIRMED,
            ReservationStatus.COLLECTED,
        }
        assert [rental.due_back_on for rental in rows.returns] == [
            TODAY - 2 * ONE_DAY,
            TODAY - ONE_DAY,
            TODAY,
        ]
        assert rows.returns[1].items_out == 0


class TestTheNumberOfStatements:
    """Each read issues the same statements however many rows it finds."""

    def test_the_dashboard_is_six_statements_with_few_rows_and_with_more(
        self, postgres_engine: Engine, postgres_session: Session, counter: Counter
    ) -> None:
        with recorded_statements(postgres_engine) as few:
            dashboard_of(postgres_session, counter)
        for _ in range(MORE_ROWS):
            counter.booked(TODAY, units=2)
            counter.hired(TODAY - ONE_DAY, units=2)
        postgres_session.commit()
        with recorded_statements(postgres_engine) as many:
            rows = dashboard_of(postgres_session, counter)
        assert len(rows.overdue) > 1
        assert len(few) == len(many) == DASHBOARD_STATEMENTS

    def test_the_diary_is_four_statements_with_few_rows_and_with_more(
        self, postgres_engine: Engine, postgres_session: Session, counter: Counter
    ) -> None:
        overview = SqlCounterOverview(postgres_session)
        with recorded_statements(postgres_engine) as few:
            overview.diary(counter.branch_id, TODAY, TODAY)
        for _ in range(MORE_ROWS):
            counter.booked(TODAY, units=2)
            counter.hired(TODAY, units=2)
        postgres_session.commit()
        with recorded_statements(postgres_engine) as many:
            overview.diary(counter.branch_id, TODAY - 6 * ONE_DAY, TODAY)
        assert len(few) == len(many) == DIARY_STATEMENTS

    def test_the_locator_is_two_statements_however_many_units_match(
        self, postgres_engine: Engine, postgres_session: Session, counter: Counter
    ) -> None:
        locator = SqlAssetLocator(postgres_session)
        with recorded_statements(postgres_engine) as statements:
            found = locator.search(AssetSearch(text="TSH-TS", page_size=50))
        assert found.total > 10
        assert len(statements) == LOCATOR_STATEMENTS

    def test_the_route_issues_the_same_statements_whatever_the_rows(
        self,
        booking: BookingClient,
        postgres_engine: Engine,
        postgres_session: Session,
        counter: Counter,
    ) -> None:
        """The sweep, the branch, the account and the read itself, counted together.

        The first read marks yesterday's booking as a no show, so it is made
        before anything is counted, and the sweep then finds nothing due.
        """
        read_dashboard(booking, counter.staff)
        with recorded_statements(postgres_engine) as few:
            read_dashboard(booking, counter.staff)
            read_diary(booking, counter.staff, days=7)
        for _ in range(MORE_ROWS):
            counter.booked(TODAY, units=2)
            counter.hired(TODAY, units=2)
        postgres_session.commit()
        with recorded_statements(postgres_engine) as many:
            read_dashboard(booking, counter.staff)
            read_diary(booking, counter.staff, days=7)
        assert len(few) == len(many)
