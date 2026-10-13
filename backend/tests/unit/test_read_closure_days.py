"""The owner's reads of the closed days and of the bookings a closure strands.

The list runs from today for a year unless asked otherwise, lists each public
holiday once for every branch and each live closure with its branch and key,
in the order of the days. A span that runs backwards or is longer than a year
is refused naming `to`. The impact read is narrowed to a branch or not, and an
unknown branch is refused by name. They run against the in memory doubles of
tests/support/memory_closures.py, on the still clock's Monday 2 March 2026.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.application.refusal import refused_parameter_of
from app.application.trading.closure_models import StrandedBooking
from app.application.trading.closure_reads import (
    LONGEST_SPAN_DAYS,
    MAXIMUM_STRANDED_LISTED,
    ClosedDaysRequest,
    ClosureImpactRequest,
    ReadClosureDays,
)
from app.domain.errors import ValidationFailure
from app.domain.public_holidays import public_holidays
from tests.support.catalogue_terms import ADMINISTRATOR
from tests.support.clock import FixedClock
from tests.support.memory_closures import (
    ClosureStore,
    MemoryClosureBranches,
    MemoryClosureReads,
)

TODAY = date(2026, 3, 2)
STOCKTAKE_DAY = date(2026, 3, 20)
HUMAN_RIGHTS_DAY = date(2026, 3, 21)


@pytest.fixture
def store() -> ClosureStore:
    """Return a store with two trading branches, CBD and BEL."""
    built = ClosureStore()
    built.branch("CBD")
    built.branch("BEL")
    return built


@pytest.fixture
def reads(store: ClosureStore) -> MemoryClosureReads:
    """Return the read side over the store."""
    return MemoryClosureReads(store)


def reader(store: ClosureStore, reads: MemoryClosureReads) -> ReadClosureDays:
    """Return the read on the still clock."""
    return ReadClosureDays(reads, MemoryClosureBranches(store), FixedClock())


def booking(reference: str, start: date, end: date, hire_day: str) -> StrandedBooking:
    """Return a booking a closure would strand."""
    return StrandedBooking(
        reference=reference,
        branch_code="CBD",
        customer_name="Nomsa Dlamini",
        customer_phone="082 441 7719",
        start=start,
        end=end,
        hire_day=hire_day,
    )


class TestTheClosedDays:
    """Holidays once, closures with their branch, by day."""

    def test_a_year_from_today_holds_the_holidays_and_the_live_closures_by_day(
        self, store: ClosureStore, reads: MemoryClosureReads
    ) -> None:
        own = store.keep(branch_code="CBD", day=STOCKTAKE_DAY)
        every = store.keep(branch_code=None, day=STOCKTAKE_DAY, reason="Election day")
        store.keep(branch_code="BEL", day=TODAY - timedelta(days=1))

        entries = reader(store, reads).closed_days(ClosedDaysRequest(actor=ADMINISTRATOR))

        first_three = [(e.day, e.branch_code, e.kind, e.closure_id) for e in entries[:3]]
        assert first_three == [
            (STOCKTAKE_DAY, None, "closure", every.id),
            (STOCKTAKE_DAY, "CBD", "closure", own.id),
            (HUMAN_RIGHTS_DAY, None, "public_holiday", None),
        ]
        last = TODAY + timedelta(days=LONGEST_SPAN_DAYS - 1)
        holidays = [
            day for year in (2026, 2027) for day in public_holidays(year) if TODAY <= day <= last
        ]
        assert len(entries) == len(holidays) + 2
        assert [e.day for e in entries] == sorted(e.day for e in entries)
        assert entries[-1].day <= last

    def test_a_holiday_and_a_closure_on_one_day_list_the_holiday_first(
        self, store: ClosureStore, reads: MemoryClosureReads
    ) -> None:
        store.keep(branch_code="BEL", day=HUMAN_RIGHTS_DAY)

        entries = reader(store, reads).closed_days(
            ClosedDaysRequest(
                actor=ADMINISTRATOR, from_day=HUMAN_RIGHTS_DAY, to_day=HUMAN_RIGHTS_DAY
            )
        )

        assert [(e.kind, e.reason) for e in entries] == [
            ("public_holiday", "Human Rights Day"),
            ("closure", "Stocktake"),
        ]

    def test_a_cancelled_closure_is_not_listed(
        self, store: ClosureStore, reads: MemoryClosureReads
    ) -> None:
        kept = store.keep(branch_code="CBD", day=STOCKTAKE_DAY)
        store.committed.closures[kept.id] = kept.cancelled(FixedClock().now())

        entries = reader(store, reads).closed_days(
            ClosedDaysRequest(actor=ADMINISTRATOR, from_day=STOCKTAKE_DAY, to_day=STOCKTAKE_DAY)
        )

        assert entries == ()

    def test_a_year_exactly_may_be_asked_for(
        self, store: ClosureStore, reads: MemoryClosureReads
    ) -> None:
        to_day = TODAY + timedelta(days=LONGEST_SPAN_DAYS - 1)

        entries = reader(store, reads).closed_days(
            ClosedDaysRequest(actor=ADMINISTRATOR, from_day=TODAY, to_day=to_day)
        )

        assert entries

    @pytest.mark.parametrize(
        "to_day",
        [TODAY - timedelta(days=1), TODAY + timedelta(days=LONGEST_SPAN_DAYS)],
        ids=["backwards", "longer-than-a-year"],
    )
    def test_a_span_out_of_bounds_is_refused_naming_to(
        self, store: ClosureStore, reads: MemoryClosureReads, to_day: date
    ) -> None:
        with pytest.raises(ValidationFailure) as refusal:
            reader(store, reads).closed_days(
                ClosedDaysRequest(actor=ADMINISTRATOR, from_day=TODAY, to_day=to_day)
            )

        assert refused_parameter_of(refusal.value) == "to"


class TestTheImpact:
    """The bookings that start or end on the day, at a branch or at any."""

    def test_the_bookings_on_the_day_at_the_branch_are_listed_up_to_the_bound(
        self, store: ClosureStore, reads: MemoryClosureReads
    ) -> None:
        cbd, bel = store.branches["CBD"], store.branches["BEL"]
        starts = booking("TSH-R-26-000124", STOCKTAKE_DAY, date(2026, 3, 23), "collection")
        ends = booking("TSH-R-26-000125", date(2026, 3, 16), STOCKTAKE_DAY, "return")
        elsewhere = booking("TSH-R-26-000126", STOCKTAKE_DAY, date(2026, 3, 24), "collection")
        store.bookings.extend([(cbd.id, starts), (cbd.id, ends), (bel.id, elsewhere)])
        read = reader(store, reads)

        at_cbd = read.impact(
            ClosureImpactRequest(actor=ADMINISTRATOR, branch_code="CBD", day=STOCKTAKE_DAY)
        )
        anywhere = read.impact(
            ClosureImpactRequest(actor=ADMINISTRATOR, branch_code=None, day=STOCKTAKE_DAY)
        )

        assert (at_cbd.items, at_cbd.total) == ((starts, ends), 2)
        assert anywhere.total == 3
        assert reads.limits_asked == [MAXIMUM_STRANDED_LISTED, MAXIMUM_STRANDED_LISTED]

    def test_an_unknown_branch_is_refused_naming_it(
        self, store: ClosureStore, reads: MemoryClosureReads
    ) -> None:
        with pytest.raises(ValidationFailure) as refusal:
            reader(store, reads).impact(
                ClosureImpactRequest(actor=ADMINISTRATOR, branch_code="NOPE", day=STOCKTAKE_DAY)
            )

        assert refused_parameter_of(refusal.value) == "branchCode"
        assert reads.limits_asked == []
