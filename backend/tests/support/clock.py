"""A clock that stands still.

A rule about dates can only be proved if the test decides what day it is. The
fixed clock is handed to a use case in place of the system clock, so a test can
put a booking on the far side of midnight, or ninety one days ahead, without
waiting for either.

It works out the business day with the application's own rule, so a test that
moves the instant across midnight in Cape Town sees the day change exactly
where the running system would.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Final

from app.application.clock import business_day

# A Monday morning in Cape Town, one week before the worked example hire of the
# ninth to the twelfth of March 2026, so that hire is inside the booking window.
DEFAULT_INSTANT: Final[datetime] = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)


@dataclass
class FixedClock:
    """A clock that returns the instant it was given until a test moves it."""

    instant: datetime = DEFAULT_INSTANT

    def now(self) -> datetime:
        """Return the fixed instant."""
        return self.instant

    def today(self) -> date:
        """Return the business day the fixed instant falls on."""
        return business_day(self.instant)

    def advance(self, step: timedelta) -> None:
        """Move the clock forward by `step`."""
        self.instant = self.instant + step


__all__ = ["DEFAULT_INSTANT", "FixedClock"]
