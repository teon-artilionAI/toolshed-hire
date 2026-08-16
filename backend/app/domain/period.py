"""The hire period value object.

Every availability question in Toolshed Hire reduces to whether two periods
overlap, so the concept gets its own type rather than being two loose dates
passed around in a tuple. The semantics are half open, `[start, end)`, which is
BR-02: a unit returned on the twelfth frees the twelfth for a hire starting on
the twelfth. The same semantics are enforced a second time in the database by
the GiST exclusion constraint, which builds `daterange(start_date, end_date,
'[)')`. The two definitions must never drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

# The PostgreSQL bound specifier that matches this class. Written here so the
# migration and the domain object quote the same literal.
DATERANGE_BOUNDS = "[)"

MINIMUM_HIRE_DAYS = 1
MAXIMUM_HIRE_DAYS = 28


class InvalidBookingPeriod(ValueError):
    """Raised when a pair of dates cannot form a valid hire period."""


@dataclass(frozen=True, slots=True)
class BookingPeriod:
    """A half open hire period, inclusive of `start` and exclusive of `end`.

    Attributes:
        start: The first day of hire. The unit is unavailable on this day.
        end: The day the unit comes back. The unit is available again on it.

    """

    start: date
    end: date

    def __post_init__(self) -> None:
        """Validate the period at construction so no invalid instance exists.

        Raises:
            InvalidBookingPeriod: If either bound is not a date, if the period
                is empty or reversed, or if it exceeds the maximum hire length.

        """
        if not isinstance(self.start, date) or not isinstance(self.end, date):
            raise InvalidBookingPeriod(
                "Attempted to build a BookingPeriod from non date values. "
                f"Got start={self.start!r} ({type(self.start).__name__}) and "
                f"end={self.end!r} ({type(self.end).__name__}). Both must be datetime.date."
            )
        if self.end <= self.start:
            raise InvalidBookingPeriod(
                "A hire period is half open and must contain at least one day. "
                f"Attempted start={self.start.isoformat()} end={self.end.isoformat()}, "
                "which requires end to be strictly after start."
            )
        if self.days > MAXIMUM_HIRE_DAYS:
            raise InvalidBookingPeriod(
                f"A hire period may not exceed {MAXIMUM_HIRE_DAYS} days. "
                f"Attempted start={self.start.isoformat()} end={self.end.isoformat()}, "
                f"which is {self.days} days."
            )

    @property
    def days(self) -> int:
        """Return the number of chargeable days in the period."""
        return (self.end - self.start).days

    @property
    def last_day(self) -> date:
        """Return the final day the unit is actually out.

        The end bound is exclusive, so the last day held is the day before it.
        """
        return self.end - timedelta(days=1)

    def overlaps(self, other: BookingPeriod) -> bool:
        """Return True when the two periods share at least one day.

        Half open comparison, so a period ending on the twelfth does not
        overlap a period starting on the twelfth.

        Args:
            other: The period to compare against.

        Returns:
            True if the two periods intersect, False if they merely touch.

        Raises:
            InvalidBookingPeriod: If `other` is not a BookingPeriod.

        """
        if not isinstance(other, BookingPeriod):
            raise InvalidBookingPeriod(
                "Attempted to compare a BookingPeriod with "
                f"{other!r} ({type(other).__name__}). Expected a BookingPeriod."
            )
        return self.start < other.end and other.start < self.end

    def contains(self, day: date) -> bool:
        """Return True when the given day falls inside the half open period.

        Args:
            day: The calendar day to test.

        Raises:
            InvalidBookingPeriod: If `day` is not a date.

        """
        if not isinstance(day, date):
            raise InvalidBookingPeriod(
                f"Attempted to test containment of {day!r} ({type(day).__name__}). "
                "Expected a datetime.date."
            )
        return self.start <= day < self.end

    def as_postgres_daterange(self) -> str:
        """Return the literal PostgreSQL daterange this period represents.

        Useful in diagnostics and in the message attached to a conflict, so the
        reader sees exactly the range the database was asked to reserve.
        """
        return f"[{self.start.isoformat()},{self.end.isoformat()})"

    def __str__(self) -> str:
        """Return a human readable half open period."""
        return self.as_postgres_daterange()
