"""The public holidays of South Africa, worked out for any year.

The branches do not trade on a public holiday. The holidays are fixed by the
Public Holidays Act 36 of 1994, so they are worked out here from the Act rather
than typed in each year, and nothing needs updating when the year turns.

The Act names ten days by date and two by Easter, Good Friday and Family Day,
the Monday after Easter. Section 2(1) adds that whenever a public holiday falls
on a Sunday, the Monday after it is also a public holiday. Unit tests check the
2026 and 2027 answers against the list the government publishes.

A day the government declares on top of these, such as an election day, is not
in the Act. The owner adds it as a closure day instead, which the trading
calendar reads beside these.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta
from functools import lru_cache
from types import MappingProxyType
from typing import Final

# The holidays the Act fixes by date, as (month, day, name).
FIXED_HOLIDAYS: Final[tuple[tuple[int, int, str], ...]] = (
    (1, 1, "New Year's Day"),
    (3, 21, "Human Rights Day"),
    (4, 27, "Freedom Day"),
    (5, 1, "Workers' Day"),
    (6, 16, "Youth Day"),
    (8, 9, "National Women's Day"),
    (9, 24, "Heritage Day"),
    (12, 16, "Day of Reconciliation"),
    (12, 25, "Christmas Day"),
    (12, 26, "Day of Goodwill"),
)
GOOD_FRIDAY_NAME: Final[str] = "Good Friday"
FAMILY_DAY_NAME: Final[str] = "Family Day"
OBSERVED_SUFFIX: Final[str] = "observed"
# date.weekday() numbers Monday 0 and Sunday 6.
SUNDAY: Final[int] = 6
# The years the calendar is asked about. A year outside this is a mistake in
# the caller, not a question the business asks.
EARLIEST_YEAR: Final[int] = 1995
LATEST_YEAR: Final[int] = 2199


def easter_sunday(year: int) -> date:
    """Return Easter Sunday of a year in the Gregorian calendar.

    The anonymous Gregorian algorithm (Meeus, Jones and Butcher), which is
    exact for every Gregorian year.

    Args:
        year: The calendar year.

    """
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    el = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * el) // 451
    month, day = divmod(h + el - 7 * m + 114, 31)
    return date(year, month, day + 1)


@lru_cache(maxsize=64)
def public_holidays(year: int) -> Mapping[date, str]:
    """Return every public holiday of a year, with its name.

    The answer is cached and read only, so a caller cannot change it for the
    next one.

    Args:
        year: The calendar year.

    Raises:
        ValueError: If the year is outside EARLIEST_YEAR to LATEST_YEAR, which
            no question about a hire can need.

    """
    if not EARLIEST_YEAR <= year <= LATEST_YEAR:
        raise ValueError(
            f"Attempted to work out the public holidays of {year}. Only the years "
            f"{EARLIEST_YEAR} to {LATEST_YEAR} are supported."
        )
    easter = easter_sunday(year)
    named: dict[date, str] = {date(year, month, day): name for month, day, name in FIXED_HOLIDAYS}
    named[easter - timedelta(days=2)] = GOOD_FRIDAY_NAME
    named[easter + timedelta(days=1)] = FAMILY_DAY_NAME
    observed: dict[date, str] = {}
    for day, name in named.items():
        if day.weekday() == SUNDAY:
            monday = day + timedelta(days=1)
            if monday not in named:
                observed[monday] = f"{name} {OBSERVED_SUFFIX}"
    return MappingProxyType({**named, **observed})


def holiday_on(day: date) -> str | None:
    """Return the name of the public holiday on a day, or None when there is none."""
    return public_holidays(day.year).get(day)
