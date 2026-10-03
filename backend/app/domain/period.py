"""The hire period value object.

Every availability question in Toolshed Hire reduces to whether two periods
overlap, so the concept gets its own type rather than being two loose dates
passed around in a tuple. The semantics are half open, `[start, end)`, which is
BR-02: a unit returned on the twelfth frees the twelfth for a hire starting on
the twelfth. The same semantics are enforced a second time in the database by
the GiST exclusion constraint, which builds `daterange(start_date, end_date,
'[)')`. The two definitions must never drift apart.

A refusal raised here can end up on a customer's screen, beside the date they
chose. So each message is a sentence that says what to do, and it names no
rule and repeats no value. The rule that refused travels beside the message,
in `rule`, and the layer that catches the refusal writes it to the log with
the dates that were attempted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.domain.business_time import business_instant, in_business_time
from app.domain.errors import ValidationFailure

# The PostgreSQL bound specifier that matches this class. Written here so the
# migration and the domain object quote the same literal.
DATERANGE_BOUNDS = "[)"

MINIMUM_HIRE_DAYS = 1
MAXIMUM_HIRE_DAYS = 28
# How far ahead a hire may start (BR-05).
MAXIMUM_DAYS_AHEAD = 90
# The week a weekly rate pays for, which `whole_weeks` counts in.
DAYS_IN_A_WEEK = 7

# The rules behind the refusals of this module, as the log names them.
PERIOD_BOUNDS_RULE = "BR-03"
NO_PAST_START_RULE = "BR-04"
BOOKING_HORIZON_RULE = "BR-05"

RETURN_NOT_AFTER_START_MESSAGE = "The return date has to be after the start date."
HIRE_TOO_LONG_MESSAGE = f"A hire can be at most {MAXIMUM_HIRE_DAYS} days."
START_IN_THE_PAST_MESSAGE = "The hire has to start today or later."
START_BEYOND_HORIZON_MESSAGE = f"A hire can start at most {MAXIMUM_DAYS_AHEAD} days from today."
BRANCH_CLOSED_FOR_TODAY_MESSAGE = (
    "The branch has closed for today. The earliest a hire can start is tomorrow."
)


class InvalidBookingPeriod(ValueError):
    """Raised when a pair of dates cannot form a valid hire period.

    Attributes:
        rule: The business rule that refused the dates, for the log. None when
            the refusal is a mistake in the calling code and not a rule.

    """

    def __init__(self, message: str, *, rule: str | None = None) -> None:
        """Keep the sentence and, beside it, the rule that refused."""
        super().__init__(message)
        self.rule = rule


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
                f"Got {self.start!r} ({type(self.start).__name__}) as the start and "
                f"{self.end!r} ({type(self.end).__name__}) as the end. "
                "Both must be datetime.date."
            )
        if self.end <= self.start:
            raise InvalidBookingPeriod(RETURN_NOT_AFTER_START_MESSAGE, rule=PERIOD_BOUNDS_RULE)
        if self.days > MAXIMUM_HIRE_DAYS:
            raise InvalidBookingPeriod(HIRE_TOO_LONG_MESSAGE, rule=PERIOD_BOUNDS_RULE)

    @property
    def days(self) -> int:
        """Return the number of chargeable days in the period."""
        return (self.end - self.start).days

    @property
    def whole_weeks(self) -> int:
        """Return how many complete weeks the period holds."""
        return self.days // DAYS_IN_A_WEEK

    @property
    def remainder_days(self) -> int:
        """Return the days left over once the complete weeks are taken out."""
        return self.days % DAYS_IN_A_WEEK

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


def ensure_within_booking_window(period: BookingPeriod, today: date) -> None:
    """Refuse a hire that starts in the past or beyond the booking horizon.

    Args:
        period: The hire period being booked.
        today: The current business day, from the clock.

    Raises:
        ValidationFailure: If the period starts before today (BR-04) or more
            than `MAXIMUM_DAYS_AHEAD` days after it (BR-05). The failure names
            its rule in `rule` and carries the dates in its detail, and the
            message holds neither.

    """
    if period.start < today:
        raise ValidationFailure(
            START_IN_THE_PAST_MESSAGE,
            {"start_date": period.start.isoformat(), "today": today.isoformat()},
            rule=NO_PAST_START_RULE,
        )
    days_ahead = (period.start - today).days
    if days_ahead > MAXIMUM_DAYS_AHEAD:
        raise ValidationFailure(
            START_BEYOND_HORIZON_MESSAGE,
            {"days_ahead": days_ahead, "maximum_days_ahead": MAXIMUM_DAYS_AHEAD},
            rule=BOOKING_HORIZON_RULE,
        )


def ensure_branch_open_for_start(period: BookingPeriod, *, now: datetime, closes_at: time) -> None:
    """Refuse a hire that starts today once its collection branch has closed for the day (BR-04).

    Today stops being a day a hire can start on the moment the branch closes,
    by the clock in Cape Town, because nobody can collect after that and the
    sweep would call the booking a no show (BR-17). The branch is still open
    at the very instant it closes, the same moment the sweep counts from, so
    the two rules meet without a gap and without an overlap.

    Args:
        period: The hire period being booked.
        now: The current instant, from the clock.
        closes_at: When the collection branch closes, on a clock in Cape Town.

    Raises:
        ValidationFailure: If the hire starts today and the branch has closed.
            The failure names its rule and carries the start date and the
            closing time in its detail, and the message holds neither.

    """
    today = in_business_time(now).date()
    if period.start != today or now <= business_instant(today, closes_at):
        return
    raise ValidationFailure(
        BRANCH_CLOSED_FOR_TODAY_MESSAGE,
        {"start_date": period.start.isoformat(), "closes_at": closes_at.isoformat()},
        rule=NO_PAST_START_RULE,
    )
