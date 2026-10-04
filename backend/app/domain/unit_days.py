"""The days a unit was in service and the days it was on hire, within one period of the report.

The two day counts of the utilisation report are built here from what is known
about one unit, and nowhere else. Every day is a business day in Cape Town and
every span is half open, so the arithmetic is `app.domain.report_days`.

**Serviceable days.** A unit is in the fleet from the day it was acquired up
to the day it was retired, when it has been. Within that it is out of service
on every day any of these says so, and a day two of them name is counted once.

1. A damage report runs from the day it was reported up to the day it was
   resolved, or on to the end of the period while it is still open.
2. A lost unit is out from the day its loss was recorded up to the day of the
   next change of its status that was recorded, or on to the end of the period.
3. The recorded changes of status. After a change the unit holds the status
   that change gave it. Before its first change it holds the status that
   change moved it from. A unit whose status has never been recorded as
   changing holds the status it has now since it was acquired, when that is
   INTAKE, QUARANTINED or UNDER_REPAIR. Retirement and loss carry dates of
   their own, so a present status of RETIRED or LOST is never stretched back
   that way. A day held in INTAKE, QUARANTINED, UNDER_REPAIR, LOST or RETIRED
   is out of service.

**Days on hire.** A unit is on hire from the day it went out up to the day it
came back, or up to tomorrow while it is still out, and always for at least
the day it went out, because a started day is a hired day. A booking that holds
the unit and has not been collected counts its own days. The spans are joined,
so a unit that ran late into a booking already made for it is not counted
twice, and only a day the unit was in service counts, so utilisation never
passes a hundred percent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final

from app.domain.enums import AssetStatus
from app.domain.report_days import (
    DaySpan,
    clipped,
    days_in,
    merged,
    overlap,
    span_or_none,
    without,
)

# The statuses in which a unit cannot be hired, so its days leave the denominator.
OUT_OF_SERVICE: Final[frozenset[AssetStatus]] = frozenset(
    {
        AssetStatus.INTAKE,
        AssetStatus.QUARANTINED,
        AssetStatus.UNDER_REPAIR,
        AssetStatus.LOST,
        AssetStatus.RETIRED,
    }
)
# The statuses a unit with no recorded change is taken to have held since it was acquired.
HELD_SINCE_ACQUIRED: Final[frozenset[AssetStatus]] = frozenset(
    {AssetStatus.INTAKE, AssetStatus.QUARANTINED, AssetStatus.UNDER_REPAIR}
)
ONE_DAY: Final[timedelta] = timedelta(days=1)


@dataclass(frozen=True, slots=True)
class StatusChange:
    """One recorded change of a unit's status.

    Attributes:
        on: The business day it was recorded on.
        moved_from: The status the unit left.
        moved_to: The status the unit took.

    """

    on: date
    moved_from: AssetStatus
    moved_to: AssetStatus


@dataclass(frozen=True, slots=True)
class StatusRecord:
    """What the recorded changes of status say about a unit around one period.

    Attributes:
        held_on_entry: The status the last change before the period gave the
            unit, or None when no change was recorded before it.
        changes: The changes recorded within the period, oldest first.
        held_on_exit: The status the first change after the period moved the
            unit from, or None when none was recorded after it.
        held_now: The status the unit has now.

    """

    held_on_entry: AssetStatus | None
    changes: tuple[StatusChange, ...]
    held_on_exit: AssetStatus | None
    held_now: AssetStatus


@dataclass(frozen=True, slots=True)
class Spell:
    """A run of days that may still be going on.

    Attributes:
        begins: The first day.
        ends: The first day after it, or None while it has not ended.

    """

    begins: date
    ends: date | None = None


@dataclass(frozen=True, slots=True)
class UnitService:
    """Everything known about whether a unit could be hired.

    Attributes:
        acquired_on: The day it joined the fleet.
        retired_on: The day it left the fleet, or None.
        statuses: Its recorded changes of status around the period.
        damage: Each damage report, from the day it was reported to the day
            it was resolved, or open.
        losses: Each recorded loss, from its day to the day of the next
            recorded change of status, or open.

    """

    acquired_on: date
    retired_on: date | None
    statuses: StatusRecord
    damage: tuple[Spell, ...] = ()
    losses: tuple[Spell, ...] = ()


@dataclass(frozen=True, slots=True)
class UnitUse:
    """Everything known about when a unit was out or booked.

    Attributes:
        hires: Each time it went out, from the day it went out to the day it
            came back, or open while it is still out.
        bookings: Each booking that holds it and has not been collected.

    """

    hires: tuple[Spell, ...] = ()
    bookings: tuple[DaySpan, ...] = ()


@dataclass(frozen=True, slots=True)
class UnitDays:
    """The two day counts of one unit for one period.

    Attributes:
        days_on_hire: The days it was on hire or booked, on days it was in service.
        serviceable_days: The days it was in the fleet and in service.

    """

    days_on_hire: int
    serviceable_days: int


def in_fleet(service: UnitService, period: DaySpan) -> DaySpan | None:
    """Return the days of the period the unit was in the fleet, or None when it was not."""
    leaves = service.retired_on if service.retired_on is not None else period.ends
    held = span_or_none(service.acquired_on, leaves)
    return held.clipped_to(period) if held is not None else None


def out_of_service(service: UnitService, period: DaySpan) -> tuple[DaySpan, ...]:
    """Return the days of the period the unit was in the fleet and out of service, as a union."""
    spells = [*service.damage, *service.losses]
    spans: list[DaySpan | None] = [
        span_or_none(spell.begins, spell.ends if spell.ends is not None else period.ends)
        for spell in spells
    ]
    spans.extend(_recorded_out_of_service(service.statuses, period))
    return clipped(spans, in_fleet(service, period))


def in_service(service: UnitService, period: DaySpan) -> tuple[DaySpan, ...]:
    """Return the days of the period the unit was in the fleet and could be hired."""
    return without([in_fleet(service, period)], out_of_service(service, period))


def on_hire(use: UnitUse, today: date) -> tuple[DaySpan, ...]:
    """Return every day the unit was out on hire or booked, as a union.

    Args:
        use: When it went out, came back and is booked.
        today: The current business day. A unit still out is on hire today.

    """
    spans: list[DaySpan | None] = list(use.bookings)
    for hire in use.hires:
        back = hire.ends if hire.ends is not None else today + ONE_DAY
        first_after = back if back > hire.begins else hire.begins + ONE_DAY
        spans.append(DaySpan(hire.begins, first_after))
    return merged(spans)


def unit_days(service: UnitService, use: UnitUse, period: DaySpan, today: date) -> UnitDays:
    """Return the days on hire and the serviceable days of one unit for one period."""
    serviceable = in_service(service, period)
    return UnitDays(
        days_on_hire=days_in(overlap(on_hire(use, today), serviceable)),
        serviceable_days=days_in(serviceable),
    )


def _status_entering(record: StatusRecord) -> AssetStatus | None:
    """Return the status the unit held as the period began, or None when nothing says.

    The last change before the period says it best. Failing that, the first
    change within the period, and then the first after it, say what the unit
    was moved from. A unit with no recorded change holds its present status
    when that is one it can only have held since it was acquired.
    """
    if record.held_on_entry is not None:
        return record.held_on_entry
    if record.changes:
        return record.changes[0].moved_from
    if record.held_on_exit is not None:
        return record.held_on_exit
    return record.held_now if record.held_now in HELD_SINCE_ACQUIRED else None


def _recorded_out_of_service(record: StatusRecord, period: DaySpan) -> list[DaySpan | None]:
    """Return the spans of the period the recorded changes say the unit was out of service."""
    spans: list[DaySpan | None] = []
    status = _status_entering(record)
    begins = period.begins
    for change in sorted(record.changes, key=lambda change: change.on):
        if status in OUT_OF_SERVICE:
            spans.append(span_or_none(begins, change.on))
        status = change.moved_to
        begins = change.on
    if status in OUT_OF_SERVICE:
        spans.append(span_or_none(begins, period.ends))
    return spans
