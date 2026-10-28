"""A day the owner closes a branch, or every branch, beyond its week and the holidays.

The branches trade the week the trading calendar gives them and close on the
public holidays the Act names. Anything else is the owner's to decide, a
stocktake at one branch or a day the government declares for all of them, and
each such day is a closure day with a reason a customer reads.

A closure is added for today or a later day, and at most a year ahead, which is
as far as anybody plans a stocktake and further than any hire can be booked.
One branch has at most one live closure on a day, and a closure for every
branch already covers each of them, so a second one is refused rather than
stored twice. A closure is never deleted (BR-51). It is cancelled, and the row
keeps who added it and who took it away.

Closing a day does not touch the bookings that start or end on it. The owner
is shown them first and rings each customer, because only a person can agree
another day with them.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Final
from uuid import UUID

from app.domain.customer_account import REFUSED_FIELD
from app.domain.errors import StateTransitionError, ValidationFailure
from app.domain.trading_calendar import CLOSED_DAY_RULE, day_in_words

# The width of `closure_day.reason`, which revision 0013 created.
CLOSURE_REASON_MIN_LENGTH: Final[int] = 1
CLOSURE_REASON_MAX_LENGTH: Final[int] = 120
# How far ahead a day can be closed, counted from today.
FURTHEST_CLOSURE_DAYS: Final[int] = 366

REASON_FIELD: Final[str] = "reason"
DAY_FIELD: Final[str] = "day"
# The two states a closure is in, as a refusal and the audit log name them.
LIVE_STATE: Final[str] = "live"
CANCELLED_STATE: Final[str] = "cancelled"

REASON_LENGTH_MESSAGE: Final[str] = (
    f"Give a reason of {CLOSURE_REASON_MIN_LENGTH} to {CLOSURE_REASON_MAX_LENGTH} characters. "
    "Customers read it."
)
PAST_DAY_MESSAGE: Final[str] = (
    "Choose today or a later day. A day that has passed cannot be closed."
)
FAR_DAY_MESSAGE: Final[str] = f"Choose a day at most {FURTHEST_CLOSURE_DAYS} days from today."
ALREADY_CANCELLED_MESSAGE: Final[str] = "This closure was cancelled already."


@dataclass(frozen=True, slots=True)
class ClosureDay:
    """One day the owner closed a branch, or every branch.

    Attributes:
        id: The key of the closure.
        branch_id: The branch it closes, or None for every branch.
        branch_code: The code of that branch, or None for every branch.
        day: The day it closes.
        reason: Why, as a customer reads it.
        created_at: When it was added.
        cancelled_at: When it was cancelled, or None while it is live.

    """

    id: UUID
    branch_id: UUID | None
    branch_code: str | None
    day: date
    reason: str
    created_at: datetime
    cancelled_at: datetime | None = None

    @property
    def is_live(self) -> bool:
        """Return True while the closure has not been cancelled."""
        return self.cancelled_at is None

    def cancelled(self, at: datetime) -> ClosureDay:
        """Return the closure as it is once cancelled at an instant.

        Raises:
            StateTransitionError: If it was cancelled already. A cancellation
                is never stamped twice, so the first one keeps its actor.

        """
        if not self.is_live:
            raise StateTransitionError(
                ALREADY_CANCELLED_MESSAGE,
                from_status=CANCELLED_STATE,
                to_status=CANCELLED_STATE,
                rule=CLOSED_DAY_RULE,
            )
        return replace(self, cancelled_at=at)


def written_closure_reason(reason: str) -> str:
    """Return the reason as it is kept, trimmed of surrounding space, or refuse it.

    Raises:
        ValidationFailure: If it is empty or longer than the column once
            trimmed. The detail names the field.

    """
    written = reason.strip()
    if not CLOSURE_REASON_MIN_LENGTH <= len(written) <= CLOSURE_REASON_MAX_LENGTH:
        raise ValidationFailure(
            REASON_LENGTH_MESSAGE,
            {REFUSED_FIELD: REASON_FIELD, "length": len(written)},
            rule=CLOSED_DAY_RULE,
        )
    return written


def ensure_day_may_close(day: date, today: date) -> None:
    """Refuse a day that has passed or that is more than a year ahead.

    Args:
        day: The day the owner wants closed.
        today: The business day in Cape Town.

    Raises:
        ValidationFailure: Naming `day`, with how far ahead it was for the log.

    """
    days_ahead = (day - today).days
    if days_ahead < 0:
        message = PAST_DAY_MESSAGE
    elif days_ahead > FURTHEST_CLOSURE_DAYS:
        message = FAR_DAY_MESSAGE
    else:
        return
    raise ValidationFailure(
        message, {REFUSED_FIELD: DAY_FIELD, "days_ahead": days_ahead}, rule=CLOSED_DAY_RULE
    )


def day_with_year(day: date) -> str:
    """Return a day as the owner reads it, for example "Tuesday 20 October 2026"."""
    return f"{day_in_words(day)} {day.year}"


def already_closed(day: date, existing: ClosureDay | None) -> str:
    """Return the sentence that refuses a second live closure of the same day.

    Args:
        day: The day asked for.
        existing: The live closure found on that day, when it could be read.
            A closure lost to the unique index in a race is refused without it.

    """
    when = day_with_year(day)
    if existing is None:
        return f"This branch is already closed on {when}. Cancel that closure first."
    who = "Every branch is" if existing.branch_code is None else f"{existing.branch_code} is"
    return f"{who} already closed on {when} ({existing.reason}). Cancel that closure first."


def duplicate_closure(day: date, existing: ClosureDay | None) -> StateTransitionError:
    """Return the refusal of a closure on a day that is closed already.

    It is returned and not raised, so the caller can chain it to the race it
    lost when the unique index refused the row.
    """
    return StateTransitionError(
        already_closed(day, existing),
        from_status=LIVE_STATE,
        to_status=LIVE_STATE,
        rule=CLOSED_DAY_RULE,
    )
