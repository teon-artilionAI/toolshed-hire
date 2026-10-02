"""The clock port, and the rule for which day it is.

Nothing in the domain or the application layer asks the operating system for
the time. A use case is given a clock, so a test can hold the time still and
prove a rule about a date without waiting for that date.

Toolshed Hire trades in Cape Town. A business day, a closing time and the
question of whether a hire starts in the past are all worked out in
`Africa/Johannesburg`, whatever zone the server happens to run in. Instants are
still stored and compared in UTC.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from app.domain.business_time import BUSINESS_TIME_ZONE, in_business_time

__all__ = ["BUSINESS_TIME_ZONE", "Clock", "business_day"]


class Clock(Protocol):
    """Where a use case gets the current instant and the current business day."""

    def now(self) -> datetime:
        """Return the current instant as a time zone aware datetime in UTC."""
        ...

    def today(self) -> date:
        """Return the current business day in `Africa/Johannesburg`."""
        ...


def business_day(instant: datetime) -> date:
    """Return the business day an instant falls on.

    Args:
        instant: A time zone aware datetime in any zone.

    Returns:
        The calendar date of that instant in `Africa/Johannesburg`.

    Raises:
        ValueError: If the datetime carries no time zone, because the day it
            falls on then depends on a guess.

    """
    if instant.tzinfo is None:
        raise ValueError(
            f"Attempted to work out the business day of {instant.isoformat()}, which has no "
            "time zone. Pass a time zone aware datetime."
        )
    return in_business_time(instant).date()
