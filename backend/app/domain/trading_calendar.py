"""The days and hours a branch trades, and the refusal of a hire on a closed day.

The design has the three branches trading six days a week, 07:00 to 17:00 from
Monday to Friday and 07:00 to 13:00 on a Saturday, closed on a Sunday and on
every public holiday. A branch may also close on a day of its own, a stocktake
or a day the government declares, which the owner records as a closure day.

A hire is collected on its first day and brought back on its last, so both must
be days the collection branch is open. The hire period itself still counts
every calendar day in between, Sundays and holidays included, because the
equipment is out on those days too (Task 1, section 1.1).

`BranchCalendar` answers every question about one branch from three sources:
its weekly hours, the public holidays of `public_holidays`, and its closure
days. Everything that asks whether a branch is open, the booking, the hold, the
no show sweep, the diary and the dashboards, asks this one object, so the
answers cannot disagree.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from types import MappingProxyType
from typing import Final

from app.domain.errors import ValidationFailure
from app.domain.period import BookingPeriod
from app.domain.public_holidays import holiday_on

# date.isoweekday() numbers Monday 1 and Sunday 7.
MONDAY: Final[int] = 1
SATURDAY: Final[int] = 6
SUNDAY: Final[int] = 7
ISO_WEEKDAYS: Final[range] = range(MONDAY, SUNDAY + 1)
WEEKDAY_NAMES: Final[dict[int, str]] = {
    1: "Monday",
    2: "Tuesday",
    3: "Wednesday",
    4: "Thursday",
    5: "Friday",
    6: "Saturday",
    7: "Sunday",
}

# The hours the design gives every branch (Task 1, assumption 9).
STANDARD_OPENS_AT: Final[time] = time(7, 0)
STANDARD_CLOSES_AT: Final[time] = time(17, 0)
STANDARD_SATURDAY_CLOSES_AT: Final[time] = time(13, 0)

# A branch that never opens in a year has nothing to offer, so the search for
# the next open day stops there instead of running for ever.
LONGEST_CLOSURE_DAYS: Final[int] = 366

# The rule a refusal names in the log. Task 1 gives closed days no number of
# their own, so the rule is named by what it is.
CLOSED_DAY_RULE: Final[str] = "trading-calendar"

CLOSED_DAY_REASON_WEEKLY: Final[str] = "is closed on {weekday}s"


@dataclass(frozen=True, slots=True)
class OpeningHours:
    """When a counter is open on one day, on a clock in Cape Town.

    Attributes:
        opens: When the counter opens.
        closes: When it closes. A hire can no longer start once it has passed.

    Raises:
        ValueError: If the counter would close before it opens.

    """

    opens: time
    closes: time

    def __post_init__(self) -> None:
        """Refuse hours that close before they open."""
        if self.closes <= self.opens:
            raise ValueError(
                f"Attempted to set opening hours of {self.opens.isoformat()} to "
                f"{self.closes.isoformat()}. A counter has to close after it opens."
            )


@dataclass(frozen=True, slots=True)
class ClosedDay:
    """Why a branch is closed on a day, for a message or a screen.

    Attributes:
        day: The calendar day.
        reason: A short phrase that completes "The branch ..." or names the
            day, such as "Christmas Day" or "is closed on Sundays".
        kind: weekly, public_holiday or closure.

    """

    day: date
    reason: str
    kind: str


WEEKLY_CLOSURE: Final[str] = "weekly"
PUBLIC_HOLIDAY_CLOSURE: Final[str] = "public_holiday"
OWNER_CLOSURE: Final[str] = "closure"


def _frozen_week(hours: Mapping[int, OpeningHours]) -> Mapping[int, OpeningHours]:
    unknown = sorted(set(hours) - set(ISO_WEEKDAYS))
    if unknown:
        raise ValueError(
            f"Attempted to build a trading week with weekdays {unknown}. Weekdays are "
            f"numbered {MONDAY} for Monday to {SUNDAY} for Sunday."
        )
    return MappingProxyType(dict(hours))


@dataclass(frozen=True, slots=True)
class BranchCalendar:
    """The days and hours one branch trades.

    Attributes:
        weekly: Opening hours by ISO weekday, Monday 1 to Sunday 7. A weekday
            that is missing is a day the branch never opens.
        closures: The closure days the owner has set for this branch or for
            every branch, with the reason given. A public holiday need not be
            in it, because the calendar works those out itself.

    """

    weekly: Mapping[int, OpeningHours]
    closures: Mapping[date, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate the week and keep both mappings read only."""
        object.__setattr__(self, "weekly", _frozen_week(self.weekly))
        object.__setattr__(self, "closures", MappingProxyType(dict(self.closures)))

    @classmethod
    def standard(cls, closures: Mapping[date, str] | None = None) -> BranchCalendar:
        """Return the week the design gives every branch, with any closure days.

        Monday to Friday 07:00 to 17:00, Saturday 07:00 to 13:00, closed on a
        Sunday.
        """
        weekday = OpeningHours(STANDARD_OPENS_AT, STANDARD_CLOSES_AT)
        week = {day: weekday for day in range(MONDAY, SATURDAY)}
        week[SATURDAY] = OpeningHours(STANDARD_OPENS_AT, STANDARD_SATURDAY_CLOSES_AT)
        return cls(weekly=week, closures=closures or {})

    def closed_day(self, day: date) -> ClosedDay | None:
        """Return why the branch is closed on a day, or None when it is open.

        A closure day is reported before a public holiday, and both before the
        weekly pattern, so the most particular reason is the one given.
        """
        reason = self.closures.get(day)
        if reason is not None:
            return ClosedDay(day=day, reason=reason, kind=OWNER_CLOSURE)
        holiday = holiday_on(day)
        if holiday is not None:
            return ClosedDay(day=day, reason=holiday, kind=PUBLIC_HOLIDAY_CLOSURE)
        if day.isoweekday() not in self.weekly:
            weekday = WEEKDAY_NAMES[day.isoweekday()]
            return ClosedDay(
                day=day,
                reason=CLOSED_DAY_REASON_WEEKLY.format(weekday=weekday),
                kind=WEEKLY_CLOSURE,
            )
        return None

    def hours_on(self, day: date) -> OpeningHours | None:
        """Return the opening hours on a day, or None when the branch is closed."""
        if self.closed_day(day) is not None:
            return None
        return self.weekly[day.isoweekday()]

    def is_open(self, day: date) -> bool:
        """Return True when the branch trades on the day."""
        return self.hours_on(day) is not None

    def next_open_day(self, day: date) -> date | None:
        """Return the first day on or after `day` that the branch trades.

        Returns:
            The day, or None when the branch does not open at all within
            LONGEST_CLOSURE_DAYS, which only a branch with no weekly hours does.

        """
        for offset in range(LONGEST_CLOSURE_DAYS):
            candidate = day + timedelta(days=offset)
            if self.is_open(candidate):
                return candidate
        return None

    def closed_days_between(self, first: date, last: date) -> list[ClosedDay]:
        """Return every closed day from `first` to `last`, both included, in date order."""
        found: list[ClosedDay] = []
        for offset in range((last - first).days + 1):
            closed = self.closed_day(first + timedelta(days=offset))
            if closed is not None:
                found.append(closed)
        return found


def day_in_words(day: date) -> str:
    """Return a day as a customer reads it, for example "Sunday 18 October"."""
    return f"{WEEKDAY_NAMES[day.isoweekday()]} {day.day} {day.strftime('%B')}"


def closed_day_message(closed: ClosedDay, next_open: date | None, *, collecting: bool) -> str:
    """Return the sentence that refuses a hire on a closed day.

    Args:
        closed: The day and why it is closed.
        next_open: The first day after it that the branch trades, if any.
        collecting: True for the first day of the hire, False for the return.

    """
    action = "collect" if collecting else "bring equipment back"
    when = day_in_words(closed.day)
    if closed.kind == WEEKLY_CLOSURE:
        opening = f"The branch {closed.reason}, so you cannot {action} on {when}."
    elif closed.kind == PUBLIC_HOLIDAY_CLOSURE:
        opening = (
            f"{when} is {closed.reason} and the branch is closed, so you cannot {action} then."
        )
    else:
        opening = f"The branch is closed on {when} ({closed.reason}), so you cannot {action} then."
    if next_open is None:
        return f"{opening} Choose another branch."
    return f"{opening} The next day it is open is {day_in_words(next_open)}."


def ensure_open_on(calendar: BranchCalendar, day: date, *, collecting: bool) -> None:
    """Refuse a hire that starts or ends on a day the branch is closed.

    Args:
        calendar: The calendar of the collection branch.
        day: The first day of the hire, or the day it comes back.
        collecting: True for the first day, False for the return day.

    Raises:
        ValidationFailure: If the branch is closed on the day. The message says
            why and names the next open day. The detail carries the day, the
            kind of closure and the next open day for the log.

    """
    closed = calendar.closed_day(day)
    if closed is None:
        return
    next_open = calendar.next_open_day(day)
    raise ValidationFailure(
        closed_day_message(closed, next_open, collecting=collecting),
        {
            "day": day.isoformat(),
            "closure": closed.kind,
            "next_open_day": next_open.isoformat() if next_open else None,
        },
        rule=CLOSED_DAY_RULE,
    )


# The names of the two days of a hire, as a refusal reports which one it was.
COLLECTION_DAY: Final[str] = "collection"
RETURN_DAY: Final[str] = "return"


def closed_hire_day(period: BookingPeriod, calendar: BranchCalendar) -> str | None:
    """Return which day of a hire falls on a closed day, collection first, or None."""
    if not calendar.is_open(period.start):
        return COLLECTION_DAY
    if not calendar.is_open(period.end):
        return RETURN_DAY
    return None


def ensure_hire_days_open(period: BookingPeriod, calendar: BranchCalendar) -> None:
    """Refuse a hire whose collection day or return day the branch is closed on.

    The days in between are not checked. The equipment is out on them, and the
    hire counts every one of them (Task 1, section 1.1).

    Raises:
        ValidationFailure: For the collection day first, then the return day.
            The detail names which of the two it was.

    """
    for day, collecting, which in (
        (period.start, True, COLLECTION_DAY),
        (period.end, False, RETURN_DAY),
    ):
        try:
            ensure_open_on(calendar, day, collecting=collecting)
        except ValidationFailure as failure:
            raise ValidationFailure(
                failure.message, {**failure.detail, "hire_day": which}, rule=failure.rule
            ) from failure
