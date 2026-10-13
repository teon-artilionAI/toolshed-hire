"""The owner's reads of the closed days, and of the bookings a closure would strand.

The list answers every day in a span on which some branch is closed for a
reason other than its week. It runs from today for a year unless the owner
asks for another span, and a span is at most a year long, so the answer stays
a few dozen rows. The public holidays are worked out by the domain and listed
once for every branch. The closure days are read in one statement.

The impact read answers the held and confirmed bookings that start or end on
a day at a branch, or at any branch, so the owner can ring each customer before
the day closes. Nothing is cancelled. It lists at most `MAXIMUM_STRANDED_LISTED`
of them and says how many there are, so a busy day cannot make the answer
unbounded.

An unknown branch code is refused by name, the way every other read refuses it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final
from uuid import UUID

from app.application.availability.search import UNKNOWN_BRANCH_MESSAGE
from app.application.clock import Clock
from app.application.identity.ports import BranchRepository
from app.application.refusal import refused
from app.application.trading.closure_models import ClosedDayEntry, StrandedBookings
from app.application.trading.closure_ports import ClosureDayQuery
from app.domain.closure_day import ClosureDay
from app.domain.errors import DetailValue
from app.domain.identity import Actor
from app.domain.public_holidays import EARLIEST_YEAR, LATEST_YEAR, public_holidays
from app.domain.trading_calendar import OWNER_CLOSURE, PUBLIC_HOLIDAY_CLOSURE

logger = logging.getLogger(__name__)

# A year of days, today included, which is as far as a closure can be added.
LONGEST_SPAN_DAYS: Final[int] = 366
# The bookings on one day at every branch are a few dozen. The bound keeps a
# day that is far busier from making the answer unbounded.
MAXIMUM_STRANDED_LISTED: Final[int] = 200
TO_PARAMETER: Final[str] = "to"
BRANCH_CODE_PARAMETER: Final[str] = "branchCode"
SPAN_REVERSED_MESSAGE: Final[str] = "The last day has to be on or after the first day."
SPAN_TOO_LONG_MESSAGE: Final[str] = (
    f"Ask for at most {LONGEST_SPAN_DAYS} days at a time. Choose an earlier last day."
)


@dataclass(frozen=True, slots=True)
class ClosedDaysRequest:
    """Which span of days the owner wants the closed days of.

    Attributes:
        actor: The owner reading.
        from_day: The first day, or None for today.
        to_day: The last day, which is included, or None for a year from the first.

    """

    actor: Actor
    from_day: date | None = None
    to_day: date | None = None


@dataclass(frozen=True, slots=True)
class ClosureImpactRequest:
    """Which day the owner is thinking of closing, and where.

    Attributes:
        actor: The owner reading.
        branch_code: The branch, in capitals, or None for every branch.
        day: The day.

    """

    actor: Actor
    branch_code: str | None
    day: date


class ReadClosureDays:
    """Return the closed days in a span, and the bookings a closure would strand."""

    def __init__(self, closures: ClosureDayQuery, branches: BranchRepository, clock: Clock) -> None:
        """Keep the read of the closures, the branches and the clock that says what today is."""
        self._closures = closures
        self._branches = branches
        self._clock = clock

    def closed_days(self, request: ClosedDaysRequest) -> tuple[ClosedDayEntry, ...]:
        """Return every public holiday and live closure in the span, by day.

        Raises:
            ValidationFailure: Naming `to`, when it is before the first day or
                the span is longer than a year.

        """
        first = request.from_day or self._clock.today()
        last = request.to_day or first + timedelta(days=LONGEST_SPAN_DAYS - 1)
        logger.info(
            "trading.closed_days_requested",
            extra={
                "actor_user_id": str(request.actor.user_id),
                "from": first.isoformat(),
                "to": last.isoformat(),
            },
        )
        _ensure_span(first, last)
        entries = [*_holidays_between(first, last)]
        entries.extend(_entry_of(closure) for closure in self._closures.live_between(first, last))
        entries.sort(key=_listing_order)
        logger.info(
            "trading.closed_days_read",
            extra={"from": first.isoformat(), "to": last.isoformat(), "row_count": len(entries)},
        )
        return tuple(entries)

    def impact(self, request: ClosureImpactRequest) -> StrandedBookings:
        """Return the held and confirmed bookings that start or end on the day.

        Raises:
            ValidationFailure: Naming `branchCode` when no trading branch has the code.

        """
        logger.info(
            "trading.closure_impact_requested",
            extra={
                "actor_user_id": str(request.actor.user_id),
                "branch_code": request.branch_code,
                "day": request.day.isoformat(),
            },
        )
        branch_id = self._branch_id_of(request.branch_code)
        found = self._closures.bookings_on(branch_id, request.day, MAXIMUM_STRANDED_LISTED)
        logger.info(
            "trading.closure_impact_read",
            extra={
                "branch_code": request.branch_code,
                "day": request.day.isoformat(),
                "listed": len(found.items),
                "total": found.total,
            },
        )
        return found

    def _branch_id_of(self, branch_code: str | None) -> UUID | None:
        """Return the key of the trading branch asked about, or None for every branch.

        Raises:
            ValidationFailure: Naming `branchCode` when no trading branch has the code.

        """
        if branch_code is None:
            return None
        branch = self._branches.find_active_by_code(branch_code)
        if branch is None:
            raise refused(BRANCH_CODE_PARAMETER, UNKNOWN_BRANCH_MESSAGE, {"branch": branch_code})
        return branch.id


def _ensure_span(first: date, last: date) -> None:
    """Refuse a span that runs backwards or is longer than a year.

    Raises:
        ValidationFailure: Naming `to`.

    """
    detail: dict[str, DetailValue] = {
        "from": first.isoformat(),
        "to": last.isoformat(),
    }
    if last < first:
        raise refused(TO_PARAMETER, SPAN_REVERSED_MESSAGE, detail)
    if (last - first).days + 1 > LONGEST_SPAN_DAYS:
        raise refused(TO_PARAMETER, SPAN_TOO_LONG_MESSAGE, detail)


def _holidays_between(first: date, last: date) -> list[ClosedDayEntry]:
    """Return the public holidays from `first` to `last`, both included.

    A year the holiday rules do not cover has none listed, because no branch
    trades then and the owner has nothing to plan.
    """
    found: list[ClosedDayEntry] = []
    for year in range(max(first.year, EARLIEST_YEAR), min(last.year, LATEST_YEAR) + 1):
        for day, name in public_holidays(year).items():
            if first <= day <= last:
                found.append(
                    ClosedDayEntry(
                        day=day,
                        branch_code=None,
                        reason=name,
                        kind=PUBLIC_HOLIDAY_CLOSURE,
                        closure_id=None,
                    )
                )
    return found


def _entry_of(closure: ClosureDay) -> ClosedDayEntry:
    """Return a live closure as the owner's list shows it."""
    return ClosedDayEntry(
        day=closure.day,
        branch_code=closure.branch_code,
        reason=closure.reason,
        kind=OWNER_CLOSURE,
        closure_id=closure.id,
    )


def _listing_order(entry: ClosedDayEntry) -> tuple[date, bool, bool, str]:
    """Order by day, a holiday first, then a closure of every branch, then by branch code."""
    return (
        entry.day,
        entry.kind != PUBLIC_HOLIDAY_CLOSURE,
        entry.branch_code is not None,
        entry.branch_code or "",
    )
