"""The system clock, the one place the application reads the time from.

`SystemClock` implements the clock port of the application layer. The instant
comes from the operating system in UTC. The business day is that instant seen
from `Africa/Johannesburg`, so a booking made at half past midnight in Cape
Town belongs to the new day even though UTC is still on the old one.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime

from app.application.clock import BUSINESS_TIME_ZONE, business_day

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Return the current instant from the operating system, in UTC."""
    return datetime.now(UTC)


class SystemClock:
    """The real clock. Instants are in UTC and days are business days."""

    def __init__(self, instant_source: Callable[[], datetime] = _utc_now) -> None:
        """Create the clock.

        Args:
            instant_source: Where the current instant is read from. The
                operating system by default. A test passes its own to prove
                how an instant becomes a business day.

        """
        self._instant_source = instant_source
        logger.debug("clock.system_clock_created", extra={"business_zone": BUSINESS_TIME_ZONE})

    def now(self) -> datetime:
        """Return the current instant as a time zone aware datetime in UTC."""
        return self._instant_source().astimezone(UTC)

    def today(self) -> date:
        """Return the current business day in `Africa/Johannesburg`."""
        return business_day(self.now())
