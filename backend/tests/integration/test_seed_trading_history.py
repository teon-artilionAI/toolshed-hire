"""The season of trading history the seed writes, read back from PostgreSQL.

Every money figure is worked out again from the stored rate snapshots with the
domain's own policies, so an amount written any other way shows up as a
mismatch. The rules about units and time are asked of the stored rows.
"""

from __future__ import annotations

import re
import statistics
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Final
from uuid import uuid4

import pytest
from sqlalchemy import Engine, func, table, text
from sqlmodel import Session, select

from app.application.clock import business_day
from app.application.reporting.fleet_figures import FleetFigures
from app.application.reporting.read_report import ReadUtilisationReport, ReportQuery
from app.application.reporting.report_models import GroupBy, UtilisationReport
from app.domain.enums import UserRole
from app.domain.identity import Actor
from app.domain.money import Money
from app.domain.period import BookingPeriod
from app.domain.policies import LineSnapshot, StandardLateFeePolicy, StandardPricingPolicy
from app.domain.vat import split_vat_inclusive
from app.infrastructure.branch_repository import SqlBranchRepository
from app.infrastructure.fleet_report import SqlFleetReport
from app.infrastructure.schema_ddl import TABLE_NAMES
from seed_data import PINNED_ASSETS
from seeding import SeedDataError, SeedTally, seed_database
from seeding.trading_history import KIND_PREFIX, load_trading_history
from seeding.trading_records import DAMAGE_RANGE, RENTAL_RANGE, RESERVATION_RANGE
from tests.support.clock import FixedClock
from tests.support.factories import TEST_PASSWORD
from tests.support.pg import truncate_schema_tables

pytestmark = pytest.mark.postgres

FEWEST_HIRES: Final[int] = 1200
MOST_HIRES: Final[int] = 1800
WALK_INS: Final[int] = 30
TRADE_WALK_INS: Final[int] = 10
# About one hire in twelve comes back late, one in forty damaged, and half of
# the damage is charged.
LATE_SHARE: Final[tuple[float, float]] = (1 / 16, 1 / 9)
DAMAGED_SHARE: Final[tuple[float, float]] = (1 / 60, 1 / 25)
CHARGEABLE_SHARE: Final[tuple[float, float]] = (0.3, 0.7)
SEPTEMBER: Final[tuple[date, date]] = (date(2026, 9, 1), date(2026, 10, 1))
REPORT_READ_AT: Final[datetime] = datetime(2026, 10, 2, 8, 0, tzinfo=UTC)
ADMIN: Final[Actor] = Actor(user_id=uuid4(), role=UserRole.ADMIN, branch_id=None)
WORKED_EXAMPLE: Final[frozenset[str]] = frozenset({"TSH-R-26-000123", "TSH-H-26-000098"})
REFERENCES: Final[dict[str, re.Pattern[str]]] = {
    "SELECT reference FROM reservation": re.compile(r"TSH-R-26-9\d{5}"),
    "SELECT reference FROM rental": re.compile(r"TSH-H-26-9\d{5}"),
    "SELECT reference FROM damage_report": re.compile(r"TSH-D-26-9\d{4}"),
}
# The reserved ranges, bound into every query under these names.
RANGE_NAMES: Final[list[str]] = "r_first r_last h_first h_last d_first d_last".split()
RANGES: Final[dict[str, str]] = dict(
    zip(RANGE_NAMES, (*RESERVATION_RANGE, *RENTAL_RANGE, *DAMAGE_RANGE), strict=True)
)
# Written as `:in_history` in a query, the condition of a rental of the history.
IN_HISTORY: Final[str] = "rn.reference BETWEEN :h_first AND :h_last"
# Pairs of rows that would put one unit in two places at once, on paper or in time.
OVERLAPS: Final[tuple[str, ...]] = (
    """SELECT count(*) FROM asset_allocation a JOIN asset_allocation b
         ON a.asset_id = b.asset_id AND a.id < b.id
        AND daterange(a.start_date, a.end_date) && daterange(b.start_date, b.end_date)""",
    """SELECT count(*) FROM rental_item a JOIN rental_item b
         ON a.asset_id = b.asset_id AND a.id < b.id
        AND tstzrange(a.checked_out_at, a.returned_at)
            && tstzrange(b.checked_out_at, b.returned_at)""",
    """SELECT count(*) FROM rental_item i JOIN damage_report d ON d.asset_id = i.asset_id
        AND tstzrange(i.checked_out_at, i.returned_at)
            && tstzrange(d.reported_at, d.resolved_at)""",
)


@pytest.fixture(scope="module")
def history(postgres_engine: Engine) -> Iterator[SeedTally]:
    """Empty the database, seed it with its trading history once and yield what was written."""
    truncate_schema_tables(postgres_engine)
    with Session(postgres_engine) as session:
        tally = seed_database(session, TEST_PASSWORD)
        load_trading_history(session, tally)
        session.commit()
    try:
        yield tally
    finally:
        truncate_schema_tables(postgres_engine)


@pytest.fixture
def db(postgres_engine: Engine, history: SeedTally) -> Iterator[Session]:
    """Yield a fresh session on the seeded database."""
    with Session(postgres_engine) as session:
        yield session


def rows(db: Session, sql: str) -> list[tuple[object, ...]]:
    """Return every row of a query, with the reserved reference ranges bound."""
    statement = text(sql.replace(":in_history", IN_HISTORY))
    result = db.execute(statement, RANGES)
    return [tuple(row) for row in result] if result.returns_rows else []


def count(db: Session, sql: str) -> int:
    """Return the one count a query returns, with the reserved reference ranges bound."""
    return int(str(rows(db, sql)[0][0]))


def trading_counts(counts: dict[str, int]) -> dict[str, int]:
    """Return only the counts the trading history recorded."""
    return {kind: value for kind, value in counts.items() if kind.startswith(KIND_PREFIX)}


def table_counts(engine: Engine) -> dict[str, int]:
    """Return the number of rows in every table of the schema."""
    with Session(engine) as session:
        return {
            name: int(session.exec(select(func.count()).select_from(table(name))).one())
            for name in TABLE_NAMES
        }


def report_of(db: Session, group_by: GroupBy) -> UtilisationReport:
    """Return every line of the report of September, as an administrator reads it."""
    fleet = SqlFleetReport(db)
    figures = FleetFigures(fleet, FixedClock(REPORT_READ_AT))
    reads = ReadUtilisationReport(figures, fleet, SqlBranchRepository(db), lambda: None)
    begins, ends = SEPTEMBER
    return reads.everything(ReportQuery(ADMIN, starts_on=begins, ends_on=ends, group_by=group_by))


class TestTheSeasonIsWrittenOnce:
    """The history is written whole the first time and found whole every time after."""

    def test_the_first_run_writes_a_season_and_a_second_writes_nothing(
        self, postgres_engine: Engine, history: SeedTally
    ) -> None:
        created = trading_counts(history.created)
        assert FEWEST_HIRES <= created["trading_reservation"] <= MOST_HIRES
        assert created["trading_rental"] == created["trading_reservation"]
        assert created["trading_customer_profile"] == WALK_INS
        before = table_counts(postgres_engine)
        with Session(postgres_engine) as session:
            second = seed_database(session, TEST_PASSWORD)
            load_trading_history(session, second)
            session.commit()
        assert second.changed_nothing, f"The second run created {second.created}."
        assert trading_counts(second.found) == created
        assert table_counts(postgres_engine) == before

    def test_a_season_only_partly_there_is_refused(self, db: Session) -> None:
        rows(db, "UPDATE rental SET reference = 'TSH-H-26-000999' WHERE reference = :h_first")
        with pytest.raises(SeedDataError, match="part of the trading history"):
            load_trading_history(db, SeedTally())
        db.rollback()


class TestNoUnitIsOnTwoHiresAtOnce:
    """Every unit is out once at a time, at its own branch, after it was bought."""

    def test_no_allocations_hires_or_repairs_of_one_unit_overlap(self, db: Session) -> None:
        assert [count(db, sql) for sql in OVERLAPS] == [0, 0, 0]

    def test_every_hire_is_in_the_season_at_the_units_branch_after_it_was_bought(
        self, db: Session
    ) -> None:
        assert not count(db, """
            SELECT count(*) FROM asset_allocation a
              JOIN reservation_line l ON l.id = a.reservation_line_id
              JOIN rental rn ON rn.reservation_id = l.reservation_id
              JOIN reservation r ON r.id = rn.reservation_id JOIN asset s ON s.id = a.asset_id
             WHERE :in_history AND (r.branch_id <> s.branch_id OR a.start_date < s.acquired_on
                OR r.start_date < DATE '2026-06-01'
                OR rn.returned_at >= TIMESTAMPTZ '2026-10-01 00:00:00+02'
                OR a.release_reason IS DISTINCT FROM 'RETURNED')
        """)


class TestTheMoneyIsTheDomains:
    """Every amount is the answer the domain's policies and settlement give."""

    def test_every_rental_is_settled_and_its_deposit_adds_up(self, db: Session) -> None:
        rentals = rows(db, """
            SELECT rn.status, rn.deposit_held, rn.deposit_refunded, rn.deposit_withheld,
                   rn.balance_due, rn.settled_at,
                   sum(c.amount_inc_vat) FILTER (WHERE c.charge_type = 'DEPOSIT_HOLD'),
                   sum(c.amount_inc_vat) FILTER (WHERE c.charge_type = 'DEPOSIT_RELEASE'),
                   sum(c.amount_inc_vat)
                       FILTER (WHERE c.charge_type IN ('LATE_FEE', 'DAMAGE_RECOVERY')),
                   count(*) FILTER (WHERE c.status <> 'SETTLED' OR c.payment_reference IS NULL)
              FROM rental rn JOIN charge c ON c.rental_id = rn.id
             WHERE :in_history GROUP BY rn.id
        """)
        assert len(rentals) >= FEWEST_HIRES
        for status, held, back, kept, balance, settled_at, hold, release, owed, open_ in rentals:
            assert status == "SETTLED" and settled_at is not None and balance == 0 and open_ == 0
            assert held == back + kept == hold
            assert (release or 0) == -back
            assert kept == min(held, owed or 0)

    def test_every_hire_charge_is_the_pricing_policy_answer_for_its_lines(
        self, db: Session
    ) -> None:
        policy = StandardPricingPolicy()
        expected: dict[object, tuple[Money, Money]] = {}
        for rental, daily, weekly, deposit, units, discount, subtotal, begins, ends in rows(db, """
            SELECT rn.id, l.daily_rate_snapshot, l.weekly_rate_snapshot, l.deposit_snapshot,
                   l.quantity, l.discount_percent, l.line_subtotal_ex_vat, r.start_date, r.end_date
              FROM rental rn JOIN reservation r ON r.id = rn.reservation_id
              JOIN reservation_line l ON l.reservation_id = r.id WHERE :in_history
        """):
            rates = (Money.create(daily), Money.create(weekly), Money.create(deposit))
            quote = policy.quote(LineSnapshot(*rates, units), BookingPeriod(begins, ends), discount)
            assert quote.amount_ex_vat.amount == subtotal
            before_vat, vat = expected.get(rental, (Money.zero(), Money.zero()))
            expected[rental] = (before_vat.add(quote.amount_ex_vat), vat.add(quote.vat_amount))
        charged = rows(db, """
            SELECT rn.id, c.amount_ex_vat, c.vat_amount FROM charge c
              JOIN rental rn ON rn.id = c.rental_id WHERE c.charge_type = 'HIRE' AND :in_history
        """)
        assert {rental: (ex, vat) for rental, ex, vat in charged} == {
            rental: (ex.amount, vat.amount) for rental, (ex, vat) in expected.items()
        }

    def test_every_late_fee_is_the_late_fee_policy_answer(self, db: Session) -> None:
        policy = StandardLateFeePolicy()
        fees = rows(db, """
            SELECT c.amount_ex_vat, c.vat_amount, c.amount_inc_vat, l.late_fee_per_day_snapshot,
                   rn.due_back_on, i.returned_at, i.days_late
              FROM charge c JOIN rental rn ON rn.id = c.rental_id
              JOIN rental_item i ON i.id = c.rental_item_id
              JOIN asset_allocation a ON a.id = i.asset_allocation_id
              JOIN reservation_line l ON l.id = a.reservation_line_id
             WHERE c.charge_type = 'LATE_FEE' AND :in_history
        """)
        for before_vat, vat, with_vat, per_day, due, returned_at, days_late in fees:
            back_on, per_day_fee = business_day(returned_at), Money.create(per_day)
            fee = policy.late_fee(due_back_on=due, returned_on=back_on, fee_per_day=per_day_fee)
            split = split_vat_inclusive(fee.amount)
            assert (with_vat, before_vat, vat) == (
                fee.amount.amount, split.amount_ex_vat.amount, split.vat_amount.amount
            )
            assert days_late == fee.days_late and 1 <= days_late <= 3
        hires = count(db, "SELECT count(*) FROM rental rn WHERE :in_history")
        late = count(db, """
            SELECT count(*) FROM rental_item i JOIN rental rn ON rn.id = i.rental_id
             WHERE i.days_late > 0 AND :in_history
        """)
        assert late == len(fees) and LATE_SHARE[0] * hires < late < LATE_SHARE[1] * hires

    def test_damage_is_resolved_and_recovered_under_the_replacement_value(
        self, db: Session
    ) -> None:
        reports = rows(db, """
            SELECT d.status, d.actual_repair_cost, d.chargeable_to_customer, i.flagged_for_damage,
                   l.replacement_value_snapshot, count(c.id), max(c.amount_inc_vat)
              FROM damage_report d JOIN rental_item i ON i.id = d.rental_item_id
              JOIN asset_allocation a ON a.id = i.asset_allocation_id
              JOIN reservation_line l ON l.id = a.reservation_line_id
              LEFT JOIN charge c ON c.damage_report_id = d.id
             WHERE d.reference BETWEEN :d_first AND :d_last GROUP BY d.id, i.id, l.id
        """)
        hires = count(db, "SELECT count(*) FROM rental rn WHERE :in_history")
        assert DAMAGED_SHARE[0] * hires < len(reports) < DAMAGED_SHARE[1] * hires
        for status, cost, chargeable, flagged, value, recoveries, recovered in reports:
            assert status == "RESOLVED" and cost is not None and flagged
            assert recoveries == (1 if chargeable else 0)
            assert not chargeable or Decimal(0) < recovered < value
        chargeable_share = sum(bool(report[2]) for report in reports) / len(reports)
        assert CHARGEABLE_SHARE[0] < chargeable_share < CHARGEABLE_SHARE[1]


class TestNothingIsOutOfStepWithToday:
    """The fleet, the bookings and the logs read as they did before the history."""

    def test_every_unit_is_where_the_seed_left_it_and_nothing_was_audited(
        self, db: Session
    ) -> None:
        off_the_shelf = {unit.asset_tag for unit in PINNED_ASSETS if unit.status != "AVAILABLE"}
        found = rows(db, "SELECT asset_tag FROM asset WHERE status <> 'AVAILABLE'")
        assert {tag for (tag,) in found} == off_the_shelf
        assert not count(db, "SELECT count(*) FROM asset_allocation WHERE released_at IS NULL")
        assert not count(db, "SELECT count(*) FROM damage_report WHERE status <> 'RESOLVED'")
        assert not count(db, "SELECT count(*) FROM audit_event")

    def test_the_references_and_the_walk_ins_sit_in_their_reserved_ranges(
        self, db: Session
    ) -> None:
        for sql, pattern in REFERENCES.items():
            history = {str(reference) for (reference,) in rows(db, sql)} - WORKED_EXAMPLE
            assert history and all(pattern.fullmatch(reference) for reference in history), sql
        walk_ins = rows(db, "SELECT customer_type, company_name, contact_phone"
                            " FROM customer_profile WHERE user_account_id IS NULL")
        assert len(walk_ins) == WALK_INS
        assert all(re.fullmatch(r"021 555 02\d\d", str(phone)) for *_, phone in walk_ins)
        trade = [company for kind, company, _phone in walk_ins if kind == "TRADE"]
        assert len(trade) == TRADE_WALK_INS and all(trade)
        by_accounts = count(db, """
            SELECT count(*) FROM reservation r
              JOIN customer_profile p ON p.id = r.customer_profile_id
             WHERE p.user_account_id IS NOT NULL AND r.reference BETWEEN :r_first AND :r_last
        """)
        assert 0 < by_accounts < FEWEST_HIRES / 10


class TestTheSeptemberReport:
    """The report of September has something to say at every branch and for every model."""

    def test_every_branch_shows_utilisation_and_gross_contribution(self, db: Session) -> None:
        lines = {line.key: line for line in report_of(db, GroupBy.BRANCH).lines}
        assert set(lines) == {"CBD", "BLV", "SMW"}
        for line in lines.values():
            assert line.utilisation_percent is not None and line.utilisation_percent > 0
            assert line.contribution.gross_contribution.amount > 0

    def test_the_models_spread_from_steady_demand_to_hardly_moving(self, db: Session) -> None:
        lines = report_of(db, GroupBy.MODEL).lines
        percents = [line.utilisation_percent or Decimal(0) for line in lines]
        assert sum(percent >= 40 for percent in percents) >= 5
        assert sum(percent < 5 for percent in percents) >= 5
        assert 10 <= statistics.median(percents) <= 30
