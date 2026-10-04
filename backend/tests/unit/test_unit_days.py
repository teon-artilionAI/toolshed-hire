"""The serviceable days and the days on hire of one unit, with no database.

The period is September 2026 and today is the twentieth unless a test says
otherwise. Each test builds what is known about one unit and reads the two
counts the report divides.
"""

from __future__ import annotations

from datetime import date
from typing import Final

from app.domain.enums import AssetStatus
from app.domain.report_days import DaySpan
from app.domain.unit_days import (
    Spell,
    StatusChange,
    StatusRecord,
    UnitService,
    UnitUse,
    in_fleet,
    in_service,
    on_hire,
    out_of_service,
    unit_days,
)

SEPTEMBER: Final[DaySpan] = DaySpan(date(2026, 9, 1), date(2026, 10, 1))
TODAY: Final[date] = date(2026, 9, 20)
LONG_AGO: Final[date] = date(2025, 1, 10)
AVAILABLE: Final[AssetStatus] = AssetStatus.AVAILABLE
QUARANTINED: Final[AssetStatus] = AssetStatus.QUARANTINED
UNDER_REPAIR: Final[AssetStatus] = AssetStatus.UNDER_REPAIR
ON_HIRE: Final[AssetStatus] = AssetStatus.ON_HIRE


def day(number: int) -> date:
    """Return a day of September 2026."""
    return date(2026, 9, number)


def nothing_recorded(now: AssetStatus = AVAILABLE) -> StatusRecord:
    """Return the record of a unit whose status was never recorded as changing."""
    return StatusRecord(held_on_entry=None, changes=(), held_on_exit=None, held_now=now)


def unit(
    *,
    acquired_on: date = LONG_AGO,
    retired_on: date | None = None,
    statuses: StatusRecord | None = None,
    damage: tuple[Spell, ...] = (),
    losses: tuple[Spell, ...] = (),
) -> UnitService:
    """Return what is known about a unit, in service all month unless a test says otherwise."""
    return UnitService(
        acquired_on=acquired_on,
        retired_on=retired_on,
        statuses=statuses or nothing_recorded(),
        damage=damage,
        losses=losses,
    )


def serviceable(service: UnitService) -> int:
    """Return the serviceable days of a unit in September."""
    return unit_days(service, UnitUse(), SEPTEMBER, TODAY).serviceable_days


class TestTheFleetWindow:
    """A unit counts from the day it was acquired up to the day it was retired."""

    def test_a_unit_owned_all_month_is_in_the_fleet_every_day(self) -> None:
        assert in_fleet(unit(), SEPTEMBER) == SEPTEMBER
        assert serviceable(unit()) == 30

    def test_a_unit_acquired_in_the_month_counts_from_that_day(self) -> None:
        assert serviceable(unit(acquired_on=day(15))) == 16

    def test_a_unit_retired_in_the_month_counts_up_to_that_day(self) -> None:
        assert serviceable(unit(retired_on=day(11))) == 10

    def test_a_unit_acquired_after_the_month_is_not_in_it(self) -> None:
        assert in_fleet(unit(acquired_on=date(2026, 10, 2)), SEPTEMBER) is None
        assert serviceable(unit(acquired_on=date(2026, 10, 2))) == 0


class TestDamageAndLoss:
    """A report and a loss each take days out, and a day both name is taken out once."""

    def test_a_resolved_report_runs_from_the_day_reported_to_the_day_resolved(self) -> None:
        assert serviceable(unit(damage=(Spell(day(5), day(12)),))) == 23

    def test_an_open_report_runs_to_the_end_of_the_period(self) -> None:
        assert serviceable(unit(damage=(Spell(day(25)),))) == 24

    def test_a_report_from_before_the_period_counts_only_its_days_inside(self) -> None:
        assert serviceable(unit(damage=(Spell(date(2026, 8, 20), day(4)),))) == 27

    def test_two_reports_of_the_same_days_take_them_out_once(self) -> None:
        reports = (Spell(day(5), day(12)), Spell(day(8), day(14)))
        assert out_of_service(unit(damage=reports), SEPTEMBER) == (DaySpan(day(5), day(14)),)

    def test_a_loss_runs_until_the_next_recorded_change(self) -> None:
        assert serviceable(unit(losses=(Spell(day(10), day(18)),))) == 22

    def test_a_loss_with_no_change_after_it_runs_to_the_end_of_the_period(self) -> None:
        assert serviceable(unit(losses=(Spell(day(10)),))) == 9

    def test_days_out_of_service_after_retirement_are_not_counted_twice(self) -> None:
        service = unit(retired_on=day(11), damage=(Spell(day(5)),))
        assert out_of_service(service, SEPTEMBER) == (DaySpan(day(5), day(11)),)
        assert serviceable(service) == 4


class TestTheRecordedChanges:
    """The recorded changes of status say when a unit was out of service."""

    def test_a_quarantine_and_a_repair_take_out_the_days_until_it_was_back(self) -> None:
        record = StatusRecord(
            held_on_entry=None,
            changes=(
                StatusChange(day(5), AVAILABLE, QUARANTINED),
                StatusChange(day(8), QUARANTINED, UNDER_REPAIR),
                StatusChange(day(12), UNDER_REPAIR, AVAILABLE),
            ),
            held_on_exit=None,
            held_now=AVAILABLE,
        )
        assert serviceable(unit(statuses=record)) == 23

    def test_a_quarantine_at_return_counts_before_its_report_was_filed(self) -> None:
        record = StatusRecord(
            held_on_entry=AVAILABLE,
            changes=(
                StatusChange(day(9), ON_HIRE, QUARANTINED),
                StatusChange(day(14), UNDER_REPAIR, AVAILABLE),
            ),
            held_on_exit=None,
            held_now=AVAILABLE,
        )
        service = unit(statuses=record, damage=(Spell(day(10), day(14)),))
        assert out_of_service(service, SEPTEMBER) == (DaySpan(day(9), day(14)),)

    def test_the_last_change_before_the_period_says_how_it_began(self) -> None:
        record = StatusRecord(
            held_on_entry=UNDER_REPAIR,
            changes=(StatusChange(day(4), UNDER_REPAIR, AVAILABLE),),
            held_on_exit=None,
            held_now=AVAILABLE,
        )
        assert serviceable(unit(statuses=record)) == 27

    def test_the_first_change_in_the_period_says_what_it_was_before(self) -> None:
        record = StatusRecord(
            held_on_entry=None,
            changes=(StatusChange(day(6), QUARANTINED, AVAILABLE),),
            held_on_exit=None,
            held_now=AVAILABLE,
        )
        assert serviceable(unit(statuses=record)) == 25

    def test_the_first_change_after_the_period_says_what_it_was_during_it(self) -> None:
        record = StatusRecord(
            held_on_entry=None, changes=(), held_on_exit=QUARANTINED, held_now=AVAILABLE
        )
        assert serviceable(unit(statuses=record)) == 0

    def test_a_unit_never_recorded_as_changing_holds_its_present_status(self) -> None:
        assert serviceable(unit(statuses=nothing_recorded(AssetStatus.INTAKE))) == 0
        assert serviceable(unit(statuses=nothing_recorded(QUARANTINED))) == 0
        assert serviceable(unit(statuses=nothing_recorded(UNDER_REPAIR))) == 0

    def test_retirement_and_loss_are_never_stretched_back_from_the_present_status(self) -> None:
        assert serviceable(unit(statuses=nothing_recorded(AssetStatus.RETIRED))) == 30
        assert serviceable(unit(statuses=nothing_recorded(AssetStatus.LOST))) == 30

    def test_a_change_and_its_undoing_on_one_day_take_no_day_out(self) -> None:
        record = StatusRecord(
            held_on_entry=AVAILABLE,
            changes=(
                StatusChange(day(9), AVAILABLE, QUARANTINED),
                StatusChange(day(9), QUARANTINED, AVAILABLE),
            ),
            held_on_exit=None,
            held_now=AVAILABLE,
        )
        assert serviceable(unit(statuses=record)) == 30


class TestDaysOnHire:
    """A unit is on hire from the day it went out up to the day it came back."""

    def test_a_hire_counts_the_days_it_was_out(self) -> None:
        assert on_hire(UnitUse(hires=(Spell(day(2), day(9)),)), TODAY) == (DaySpan(day(2), day(9)),)

    def test_a_unit_still_out_is_on_hire_today(self) -> None:
        assert on_hire(UnitUse(hires=(Spell(day(18)),)), TODAY) == (DaySpan(day(18), day(21)),)

    def test_a_unit_back_the_day_it_went_out_counts_that_day(self) -> None:
        assert on_hire(UnitUse(hires=(Spell(day(5), day(5)),)), TODAY) == (DaySpan(day(5), day(6)),)

    def test_a_late_hire_and_the_booking_after_it_are_not_counted_twice(self) -> None:
        use = UnitUse(hires=(Spell(day(2), day(12)),), bookings=(DaySpan(day(10), day(15)),))
        assert unit_days(unit(), use, SEPTEMBER, TODAY).days_on_hire == 13

    def test_a_hire_from_before_the_period_counts_only_its_days_inside(self) -> None:
        use = UnitUse(hires=(Spell(date(2026, 8, 27), day(4)),))
        assert unit_days(unit(), use, SEPTEMBER, TODAY).days_on_hire == 3

    def test_a_booked_day_out_of_service_is_not_counted(self) -> None:
        service = unit(damage=(Spell(day(10)),))
        use = UnitUse(bookings=(DaySpan(day(8), day(12)),))
        figures = unit_days(service, use, SEPTEMBER, TODAY)
        assert (figures.days_on_hire, figures.serviceable_days) == (2, 9)

    def test_in_service_is_the_fleet_less_the_days_out(self) -> None:
        service = unit(acquired_on=day(15), damage=(Spell(day(20), day(22)),))
        assert in_service(service, SEPTEMBER) == (
            DaySpan(day(15), day(20)),
            DaySpan(day(22), date(2026, 10, 1)),
        )
