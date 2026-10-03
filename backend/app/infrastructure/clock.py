"""The system clock, the one place the application reads the time from.

`SystemClock` implements the clock port of the application layer. The instant
comes from the operating system in UTC. The business day is that instant seen
from `Africa/Johannesburg`, so a booking made at half past midnight in Cape
Town belongs to the new day even though UTC is still on the old one.

`StartedAtBusinessTimeClock` is the clock of a test process that sets
`TEST_BUSINESS_TIME`. It reads today's real date in Cape Town when it is built,
starts at the chosen time of day on it, and from then on runs in real time, so
a browser test can book for today and check out whatever time CI happens to
run. The settings refuse to start any environment but test with it, and
`clock_for` is the one place that chooses between the two.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, time

from app.application.clock import BUSINESS_TIME_ZONE, Clock, business_day
from app.domain.business_time import business_instant

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


class StartedAtBusinessTimeClock:
    """A test clock that starts at a time of day on today's real date and runs in real time."""

    def __init__(
        self, business_time: time, instant_source: Callable[[], datetime] = _utc_now
    ) -> None:
        """Start the clock at a time of day in Cape Town on the real date of this moment.

        Args:
            business_time: The time of day the clock starts at, on a clock in
                Cape Town.
            instant_source: Where the real instant is read from. The operating
                system by default.

        """
        started = instant_source().astimezone(UTC)
        self._offset = business_instant(business_day(started), business_time) - started
        self._instant_source = instant_source
        logger.warning(
            "clock.test_business_time_in_use",
            extra={
                "business_time": business_time.isoformat(),
                "business_day": business_day(started).isoformat(),
                "offset_seconds": int(self._offset.total_seconds()),
            },
        )

    def now(self) -> datetime:
        """Return the real instant moved to the chosen time of day, in UTC."""
        return (self._instant_source() + self._offset).astimezone(UTC)

    def today(self) -> date:
        """Return the business day of the moved instant in `Africa/Johannesburg`."""
        return business_day(self.now())


def clock_for(test_business_time: time | None) -> Clock:
    """Return the clock the API uses, the real one unless a test clock was configured.

    Args:
        test_business_time: The setting `TEST_BUSINESS_TIME`, which the
            settings only allow in the test environment.

    """
    if test_business_time is None:
        return SystemClock()
    return StartedAtBusinessTimeClock(test_business_time)
