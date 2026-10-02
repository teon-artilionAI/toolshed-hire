"""The time zone the business keeps, and an instant seen from it.

Toolshed Hire trades in Cape Town. A rule that names a time of day, such as
the late cancellation cutoff of 17:00 (BR-16), means that time on a clock in
`Africa/Johannesburg`, whatever zone the server runs in. Instants are still
stored and compared in UTC. This module is the one place that turns one into
the other, so a rule in the domain never asks the operating system which zone
it is in.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Final
from zoneinfo import ZoneInfo

BUSINESS_TIME_ZONE: Final[str] = "Africa/Johannesburg"


def in_business_time(instant: datetime) -> datetime:
    """Return an instant as a clock in the business time zone shows it.

    Args:
        instant: A time zone aware datetime in any zone.

    Raises:
        ValueError: If the datetime carries no time zone, because the time it
            shows in Cape Town then depends on a guess.

    """
    if instant.tzinfo is None:
        raise ValueError(
            f"Attempted to read {instant.isoformat()} in business time, and it has no time "
            "zone. Pass a time zone aware datetime."
        )
    return instant.astimezone(ZoneInfo(BUSINESS_TIME_ZONE))


def business_instant(day: date, wall_time: time) -> datetime:
    """Return the instant a clock in the business time zone shows a time on a day.

    Args:
        day: The calendar day in Cape Town.
        wall_time: The time of day on that clock, with no zone of its own.

    """
    return datetime.combine(day, wall_time, tzinfo=ZoneInfo(BUSINESS_TIME_ZONE))
