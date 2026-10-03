"""The counter's dashboard and diary, run against fakes of their ports (FR-16, BR-43).

The rows are built by hand, so these pin what `ReadCounterOverview` adds, which
is the branch each caller reads, the sweep before the read, the overdue
figures, the days of the diary and its no show button. The clock stands still
on Monday the second of March 2026.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Final
from uuid import UUID, uuid4

import pytest

from app.application.hire.overview import (
    BRANCH_REQUIRED_MESSAGE,
    DASHBOARD_LIST_LIMIT,
    OWN_BRANCH_ONLY_MESSAGE,
    DashboardQuery,
    DiaryQuery,
    ReadCounterOverview,
)
from app.application.hire.overview_models import (
    BookedLine,
    CollectionEntry,
    DashboardCounts,
    DashboardRows,
    DiaryRows,
    HiredUnit,
    ReturnEntry,
)
from app.application.refusal import refused_parameter_of
from app.domain.enums import RentalStatus, ReservationStatus, UserRole
from app.domain.errors import AuthorisationFailure, BranchScopeError, ValidationFailure
from app.domain.identity import Actor, Branch
from tests.support.clock import FixedClock

TODAY: Final[date] = date(2026, 3, 2)
ONE_DAY: Final[timedelta] = timedelta(days=1)
CBD: Final[Branch] = Branch(id=uuid4(), code="CBD", name="Cape Town CBD")
BLV: Final[Branch] = Branch(id=uuid4(), code="BLV", name="Bellville")
LATE_FEE: Final[Decimal] = Decimal("120.00")
HAMMER: Final[str] = "Bosch GBH 2-26"
MIXER: Final[str] = "Concrete Mixer 140L"
SWEEP: Final[str] = "sweep"
READ: Final[str] = "read"
COUNTS: Final[DashboardCounts] = DashboardCounts(
    collections_due=1, returns_due=1, overdue=2, on_hire=14, quarantined=2
)


def a_collection(
    start_date: date = TODAY, status: ReservationStatus = ReservationStatus.CONFIRMED
) -> CollectionEntry:
    """Return a booking of two hammers and a mixer, starting on a day."""
    return CollectionEntry(
        reservation_id=uuid4(),
        reference="TSH-R-26-000124",
        status=status,
        customer_name="Nomsa Dlamini",
        customer_phone="082 441 7719",
        start_date=start_date,
        end_date=start_date + 3 * ONE_DAY,
        lines=(BookedLine(model_name=HAMMER, quantity=2), BookedLine(model_name=MIXER, quantity=1)),
    )


def a_rental(due_back_on: date, *units_out: bool) -> ReturnEntry:
    """Return a hire due back on a day, with one hammer for each unit named, out or back."""
    return ReturnEntry(
        rental_id=uuid4(),
        reference="TSH-H-26-000099",
        status=RentalStatus.OPEN,
        customer_name="Nomsa Dlamini",
        customer_phone="082 441 7719",
        due_back_on=due_back_on,
        units=tuple(
            HiredUnit(model_name=HAMMER, late_fee_per_day=LATE_FEE, is_out=is_out)
            for is_out in units_out
        ),
    )


@dataclass
class FakeOverview:
    """A query object that answers with prepared rows and notes what it was asked."""

    calls: list[str]
    dashboard_rows: DashboardRows = field(
        default_factory=lambda: DashboardRows(
            counts=COUNTS, collections_due=(), returns_due=(), overdue=()
        )
    )
    diary_rows: DiaryRows = field(default_factory=lambda: DiaryRows(collections=(), returns=()))
    asked: list[tuple[UUID, date, date | int]] = field(default_factory=list)

    def dashboard(self, branch_id: UUID, today: date, list_limit: int) -> DashboardRows:
        """Note the question and answer with the prepared rows."""
        self.calls.append(READ)
        self.asked.append((branch_id, today, list_limit))
        return self.dashboard_rows

    def diary(self, branch_id: UUID, first_day: date, last_day: date) -> DiaryRows:
        """Note the question and answer with the prepared rows."""
        self.calls.append(READ)
        self.asked.append((branch_id, first_day, last_day))
        return self.diary_rows


class FakeBranches:
    """The two branches, CBD and Bellville, of which only these two trade."""

    def get(self, branch_id: UUID) -> Branch | None:
        """Return the branch with this key."""
        return {CBD.id: CBD, BLV.id: BLV}.get(branch_id)

    def find_active_by_code(self, code: str) -> Branch | None:
        """Return the trading branch with this code."""
        return {CBD.code: CBD, BLV.code: BLV}.get(code)


def service(overview: FakeOverview) -> ReadCounterOverview:
    """Return the service over the fakes, with a sweep that notes when it ran."""
    return ReadCounterOverview(
        overview, FakeBranches(), FixedClock(), lambda: overview.calls.append(SWEEP)
    )


def assistant(branch: Branch | None = CBD) -> Actor:
    """Return counter staff of a branch, or of none."""
    return Actor(
        user_id=uuid4(),
        role=UserRole.COUNTER_STAFF,
        branch_id=branch.id if branch is not None else None,
    )


ADMINISTRATOR: Final[Actor] = Actor(user_id=uuid4(), role=UserRole.ADMIN)
CUSTOMER: Final[Actor] = Actor(user_id=uuid4(), role=UserRole.CUSTOMER)


class TestWhichBranchIsRead:
    """Counter staff read their own branch. An administrator names one."""

    @pytest.mark.parametrize("branch_code", [None, "CBD"], ids=["left out", "named"])
    def test_counter_staff_read_their_own_branch(self, branch_code: str | None) -> None:
        overview = FakeOverview(calls=[])
        shown = service(overview).dashboard(DashboardQuery(assistant(), branch_code))
        assert shown.branch == CBD
        assert overview.asked == [(CBD.id, TODAY, DASHBOARD_LIST_LIMIT)]

    def test_counter_staff_who_name_another_branch_are_refused_before_the_sweep(self) -> None:
        overview = FakeOverview(calls=[])
        with pytest.raises(BranchScopeError) as refused:
            service(overview).dashboard(DashboardQuery(assistant(), "BLV"))
        assert refused.value.message == OWN_BRANCH_ONLY_MESSAGE
        assert overview.calls == []

    def test_counter_staff_with_no_branch_are_refused(self) -> None:
        with pytest.raises(BranchScopeError):
            service(FakeOverview(calls=[])).diary(DiaryQuery(assistant(None)))

    def test_an_administrator_reads_the_branch_named(self) -> None:
        shown = service(FakeOverview(calls=[])).dashboard(DashboardQuery(ADMINISTRATOR, "BLV"))
        assert shown.branch == BLV

    def test_an_administrator_who_names_no_branch_is_refused_by_name(self) -> None:
        with pytest.raises(ValidationFailure) as refused:
            service(FakeOverview(calls=[])).dashboard(DashboardQuery(ADMINISTRATOR))
        assert refused_parameter_of(refused.value) == "branchCode"
        assert refused.value.message == BRANCH_REQUIRED_MESSAGE

    def test_an_administrator_who_names_a_branch_that_does_not_trade_is_refused(self) -> None:
        with pytest.raises(ValidationFailure) as refused:
            service(FakeOverview(calls=[])).diary(DiaryQuery(ADMINISTRATOR, "XYZ"))
        assert refused_parameter_of(refused.value) == "branchCode"

    def test_a_customer_is_refused(self) -> None:
        with pytest.raises(AuthorisationFailure):
            service(FakeOverview(calls=[])).dashboard(DashboardQuery(CUSTOMER, "CBD"))


class TestTheDashboard:
    """The sweep first, then the rows, with the overdue figures worked out here."""

    def test_the_sweep_runs_before_the_read_and_the_counts_come_through(self) -> None:
        overview = FakeOverview(calls=[])
        shown = service(overview).dashboard(DashboardQuery(assistant()))
        assert overview.calls == [SWEEP, READ]
        assert (shown.counts, shown.business_day) == (COUNTS, TODAY)

    def test_an_overdue_hire_says_how_late_it_is_and_what_its_units_out_have_run_up(
        self,
    ) -> None:
        overdue = a_rental(TODAY - 2 * ONE_DAY, True, False)
        overview = FakeOverview(
            calls=[],
            dashboard_rows=DashboardRows(
                counts=COUNTS, collections_due=(), returns_due=(), overdue=(overdue,)
            ),
        )
        (entry,) = service(overview).dashboard(DashboardQuery(assistant())).overdue
        assert (entry.rental, entry.days_overdue) == (overdue, 2)
        assert entry.late_fee_accrued == Decimal("240.00")

    def test_the_late_fee_stops_at_fourteen_days(self) -> None:
        overdue = a_rental(TODAY - 20 * ONE_DAY, True, True)
        overview = FakeOverview(
            calls=[],
            dashboard_rows=DashboardRows(
                counts=COUNTS, collections_due=(), returns_due=(), overdue=(overdue,)
            ),
        )
        (entry,) = service(overview).dashboard(DashboardQuery(assistant())).overdue
        assert entry.days_overdue == 20
        assert entry.late_fee_accrued == Decimal("3360.00")


class TestTheDiary:
    """One entry per day, the rows split by their date, and the no show button."""

    def test_it_shows_today_when_no_day_is_named(self) -> None:
        overview = FakeOverview(calls=[])
        diary = service(overview).diary(DiaryQuery(assistant()))
        assert [day.business_day for day in diary.days] == [TODAY]
        assert overview.asked == [(CBD.id, TODAY, TODAY)]
        assert overview.calls == [SWEEP, READ]

    def test_seven_days_from_a_day_in_the_past_are_seven_entries(self) -> None:
        first = date(2025, 12, 29)
        overview = FakeOverview(calls=[])
        diary = service(overview).diary(DiaryQuery(assistant(), first_day=first, days=7))
        assert [day.business_day for day in diary.days] == [
            first + offset * ONE_DAY for offset in range(7)
        ]
        assert overview.asked == [(CBD.id, first, date(2026, 1, 4))]

    @pytest.mark.parametrize("days", [0, 8, -1])
    def test_a_run_outside_one_to_seven_days_is_refused_by_name(self, days: int) -> None:
        overview = FakeOverview(calls=[])
        with pytest.raises(ValidationFailure) as refused:
            service(overview).diary(DiaryQuery(assistant(), days=days))
        assert refused_parameter_of(refused.value) == "days"
        assert overview.calls == []

    def test_a_run_that_would_end_past_the_last_date_there_is_is_refused_by_name(self) -> None:
        with pytest.raises(ValidationFailure) as refused:
            service(FakeOverview(calls=[])).diary(
                DiaryQuery(assistant(), first_day=date.max - ONE_DAY, days=3)
            )
        assert refused_parameter_of(refused.value) == "from"

    def test_each_row_lands_on_its_own_day(self) -> None:
        today, tomorrow = a_collection(TODAY), a_collection(TODAY + ONE_DAY)
        returning = a_rental(TODAY + ONE_DAY, True)
        overview = FakeOverview(
            calls=[], diary_rows=DiaryRows(collections=(today, tomorrow), returns=(returning,))
        )
        first, second = service(overview).diary(DiaryQuery(assistant(), days=2)).days
        assert [collection.entry for collection in first.collections] == [today]
        assert (first.returns, second.returns) == ((), (returning,))
        assert [collection.entry for collection in second.collections] == [tomorrow]

    @pytest.mark.parametrize(
        ("start_date", "status", "offered"),
        [
            (TODAY, ReservationStatus.CONFIRMED, True),
            (TODAY - ONE_DAY, ReservationStatus.CONFIRMED, True),
            (TODAY + ONE_DAY, ReservationStatus.CONFIRMED, False),
            (TODAY, ReservationStatus.COLLECTED, False),
            (TODAY, ReservationStatus.NO_SHOW, False),
            (TODAY, ReservationStatus.RETURNED, False),
        ],
        ids=["today", "yesterday", "tomorrow", "collected", "no show", "returned"],
    )
    def test_a_collection_offers_the_no_show_button_by_the_rule_of_the_route(
        self, start_date: date, status: ReservationStatus, offered: bool
    ) -> None:
        entry = a_collection(start_date, status)
        overview = FakeOverview(calls=[], diary_rows=DiaryRows(collections=(entry,), returns=()))
        diary = service(overview).diary(DiaryQuery(ADMINISTRATOR, "CBD", first_day=start_date))
        (collection,) = diary.days[0].collections
        assert collection.can_mark_no_show is offered


class TestWhatABookingHoldsInAFewWords:
    """The counts and the summary are read off the lines and the units."""

    def test_a_collection_counts_its_units_and_names_its_models_in_line_order(self) -> None:
        entry = a_collection()
        assert entry.unit_count == 3
        assert entry.summary == f"2 x {HAMMER}, 1 x {MIXER}"

    def test_a_return_counts_what_is_out_and_groups_its_units_by_model(self) -> None:
        rental = a_rental(TODAY, True, False, True)
        assert (rental.items_out, rental.item_count) == (2, 3)
        assert rental.summary == f"3 x {HAMMER}"
        assert rental.fees_per_day_of_units_out() == (LATE_FEE, LATE_FEE)
