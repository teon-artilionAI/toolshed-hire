"""The times of day a hire of the season was booked, collected, returned and repaired.

Nothing here touches a database. Every instant is drawn from the seeded
generator inside the hours a counter or a customer would plausibly act, on the
fixed offset South Africa keeps all year, which is what the worked example
uses too.

A walk in books at the counter and collects a few minutes later. Anybody else
booked on an earlier day, at the counter while it was open or online at any
reasonable hour, and collects in the morning of the first day. The unit comes
back during trading hours, and a damaged one is reported within the hour and
resolved by the workshop during a working day.

A unit can go out again on the day it came back, but only once it is back and
has been checked over, so no unit is ever on two hires at the same moment. One
that came back late in the afternoon waits for the next day.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from random import Random
from typing import Final

from seeding.trading_demand import LONGEST_LEAD_DAYS, SAME_DAY_CHANCE, is_open
from seeding.worked_example import SOUTH_AFRICA_STANDARD_TIME

MINUTES_IN_AN_HOUR: Final[int] = 60
ONE_DAY: Final[timedelta] = timedelta(days=1)
# Minutes after midnight, on a clock in Cape Town.
COUNTER_FIRST_MINUTE: Final[int] = 7 * MINUTES_IN_AN_HOUR + 5
COUNTER_LAST_MINUTE: Final[int] = 16 * MINUTES_IN_AN_HOUR + 40
SAME_DAY_LAST_MINUTE: Final[int] = 11 * MINUTES_IN_AN_HOUR + 30
ONLINE_FIRST_MINUTE: Final[int] = 6 * MINUTES_IN_AN_HOUR
ONLINE_LAST_MINUTE: Final[int] = 21 * MINUTES_IN_AN_HOUR + 30
COLLECTION_LAST_MINUTE: Final[int] = 10 * MINUTES_IN_AN_HOUR + 40
RETURN_FIRST_MINUTE: Final[int] = 7 * MINUTES_IN_AN_HOUR + 30
RETURN_LAST_MINUTE: Final[int] = 16 * MINUTES_IN_AN_HOUR + 30
WORKSHOP_FIRST_MINUTE: Final[int] = 9 * MINUTES_IN_AN_HOUR
WORKSHOP_LAST_MINUTE: Final[int] = 15 * MINUTES_IN_AN_HOUR + 30
# Gaps in minutes between one step of a hire and the next.
CONFIRM_AFTER_MINUTES: Final[tuple[int, int]] = (1, 9)
HAND_OVER_AFTER_MINUTES: Final[tuple[int, int]] = (4, 20)
REPORT_AFTER_MINUTES: Final[tuple[int, int]] = (15, 80)
# A unit that came back is checked over before it goes out again, and the
# customer who wants it may wait a little longer than that.
TURNAROUND: Final[timedelta] = timedelta(minutes=20)
WAIT_AFTER_READY_MINUTES: Final[tuple[int, int]] = (0, 25)
# A unit back after this minute of a day does not go out again that day.
LATEST_READY_MINUTE: Final[int] = 15 * MINUTES_IN_AN_HOUR + 30


@dataclass(frozen=True, slots=True)
class BookingTimes:
    """When a hire was booked, confirmed and handed over.

    Attributes:
        booked_at: When the reservation was made and its units held.
        confirmed_at: When it was confirmed, inside the thirty minute hold.
        checked_out_at: When the units were handed over, on the first day.

    """

    booked_at: datetime
    confirmed_at: datetime
    checked_out_at: datetime


def at_minute(day: date, minute: int) -> datetime:
    """Return the instant a clock in Cape Town shows a number of minutes after midnight."""
    clock = time(minute // MINUTES_IN_AN_HOUR, minute % MINUTES_IN_AN_HOUR)
    return datetime.combine(day, clock, tzinfo=SOUTH_AFRICA_STANDARD_TIME)


def can_go_out_on(day: date, back_at: datetime | None) -> bool:
    """Return True unless a unit came back on the day too late to go out again before closing."""
    if back_at is None:
        return True
    local = back_at.astimezone(SOUTH_AFRICA_STANDARD_TIME)
    if local.date() != day:
        return True
    return local.hour * MINUTES_IN_AN_HOUR + local.minute <= LATEST_READY_MINUTE


def ready_at(day: date, back_ats: Iterable[datetime | None]) -> datetime | None:
    """Return when the last of some units that came back on a day is ready to go out, or None."""
    same_day = [
        back_at
        for back_at in back_ats
        if back_at is not None and back_at.astimezone(SOUTH_AFRICA_STANDARD_TIME).date() == day
    ]
    return max(same_day) + TURNAROUND if same_day else None


def booking_times(
    rng: Random, start: date, *, online: bool, ready: datetime | None = None
) -> BookingTimes:
    """Draw when a hire starting on a day was booked, confirmed and collected.

    Args:
        rng: The seeded generator every choice of the history is drawn from.
        start: The first day of the hire.
        online: True when the customer booked through their own login.
        ready: When the units are ready to go out, when one of them came back
            that same day, or None. Nothing is handed over before it, and a
            walk in who books and collects in one visit arrives after it.

    """
    times = _drawn(rng, start, online=online)
    if ready is None or times.checked_out_at > ready:
        return times
    shift = ready - times.checked_out_at + _minutes(rng, WAIT_AFTER_READY_MINUTES)
    if times.booked_at.date() == start:
        return BookingTimes(
            booked_at=times.booked_at + shift,
            confirmed_at=times.confirmed_at + shift,
            checked_out_at=times.checked_out_at + shift,
        )
    return replace(times, checked_out_at=times.checked_out_at + shift)


def _drawn(rng: Random, start: date, *, online: bool) -> BookingTimes:
    """Draw the booking, the confirmation and the collection with no unit to wait for."""
    if not online and rng.random() < SAME_DAY_CHANCE:
        booked_at = at_minute(start, rng.randint(COUNTER_FIRST_MINUTE, SAME_DAY_LAST_MINUTE))
        confirmed_at = booked_at + _minutes(rng, CONFIRM_AFTER_MINUTES)
        return BookingTimes(
            booked_at=booked_at,
            confirmed_at=confirmed_at,
            checked_out_at=confirmed_at + _minutes(rng, HAND_OVER_AFTER_MINUTES),
        )
    booked_on = start - ONE_DAY * rng.randint(1, LONGEST_LEAD_DAYS)
    if online:
        minute = rng.randint(ONLINE_FIRST_MINUTE, ONLINE_LAST_MINUTE)
    else:
        while not is_open(booked_on):
            booked_on -= ONE_DAY
        minute = rng.randint(COUNTER_FIRST_MINUTE, COUNTER_LAST_MINUTE)
    booked_at = at_minute(booked_on, minute)
    return BookingTimes(
        booked_at=booked_at,
        confirmed_at=booked_at + _minutes(rng, CONFIRM_AFTER_MINUTES),
        checked_out_at=at_minute(
            start, rng.randint(COUNTER_FIRST_MINUTE, COLLECTION_LAST_MINUTE)
        ),
    )


def return_time(rng: Random, returned_on: date) -> datetime:
    """Draw when during trading hours the units came back on a day."""
    return at_minute(returned_on, rng.randint(RETURN_FIRST_MINUTE, RETURN_LAST_MINUTE))


def report_time(rng: Random, returned_at: datetime) -> datetime:
    """Draw when the counter filed the damage report, within the hour or so after the return."""
    return returned_at + _minutes(rng, REPORT_AFTER_MINUTES)


def workshop_time(rng: Random, resolved_on: date) -> datetime:
    """Draw when during a working day the workshop resolved a report."""
    return at_minute(resolved_on, rng.randint(WORKSHOP_FIRST_MINUTE, WORKSHOP_LAST_MINUTE))


def _minutes(rng: Random, bounds: tuple[int, int]) -> timedelta:
    """Return a gap of a whole number of minutes drawn between two bounds."""
    return timedelta(minutes=rng.randint(*bounds))
