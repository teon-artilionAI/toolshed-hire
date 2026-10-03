"""The figures, the sentences and the shared guards of the reservation states.

A state checks its guards before it changes anything. The ones more than one
state needs are here, with the two durations the lifecycle turns on and every
sentence a refused move can say. A sentence is shown to a customer as it is
written, so each one says what happened in plain words and names no rule. The
rule travels beside it, for the log.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, Final
from uuid import UUID

from app.domain.business_time import business_instant
from app.domain.enums import ReservationStatus
from app.domain.errors import AllocationConflictError, AuthorisationFailure, StateTransitionError

if TYPE_CHECKING:
    from app.domain.availability import AssetAllocation
    from app.domain.booking import Reservation

# How long a hold lasts (BR-12).
HOLD_DURATION: Final[timedelta] = timedelta(minutes=30)
# A confirmed booking cancelled after this time on the day before collection
# counts as a late cancellation (BR-16).
LATE_CANCELLATION_CUTOFF: Final[time] = time(17, 0)
ONE_DAY: Final[timedelta] = timedelta(days=1)
# Midnight in Cape Town, when the first day of a hire begins.
START_OF_DAY: Final[time] = time.min

HOLD_EXPIRY_RULE: Final[str] = "BR-13"
FULL_ALLOCATION_RULE: Final[str] = "BR-08"
CANCELLATION_RULE: Final[str] = "BR-15"
VERIFIED_EMAIL_RULE: Final[str] = "BR-47"
COLLECTION_DAY_RULE: Final[str] = "BR-26"
NO_SHOW_RULE: Final[str] = "BR-17"

HOLD_RAN_OUT_MESSAGE: Final[str] = (
    "The hold on this reservation has run out, so it can no longer be confirmed. "
    "Please start a new reservation."
)
HOLD_STILL_RUNNING_MESSAGE: Final[str] = "The hold on this reservation has not run out yet."
NOT_EVERY_UNIT_HELD_MESSAGE: Final[str] = (
    "This reservation does not hold every tool it asks for, so it cannot go ahead."
)
EMAIL_NOT_VERIFIED_MESSAGE: Final[str] = (
    "Please verify your email address before you confirm this reservation. "
    "A counter assistant can also confirm it for you at the branch."
)
NOT_YOURS_TO_CANCEL_MESSAGE: Final[str] = (
    "Only the customer a reservation belongs to, or a member of staff, can cancel it."
)
DRAFT_HOLDS_UNITS_MESSAGE: Final[str] = (
    "This reservation is still a draft and already holds tools, so it cannot be cancelled "
    "as a draft."
)
ALREADY_ON_HIRE_MESSAGE: Final[str] = (
    "The equipment on this reservation is already out on hire, so it cannot be cancelled."
)
TOO_EARLY_TO_COLLECT_MESSAGE: Final[str] = (
    "This reservation cannot be collected before the first day of the hire."
)
BRANCH_STILL_OPEN_MESSAGE: Final[str] = (
    "The branch has not closed yet on the first day of this hire, so the reservation can "
    "still be collected."
)
FIRST_DAY_NOT_COME_MESSAGE: Final[str] = (
    "This reservation cannot be marked as not collected before the first day of the hire."
)
NO_LINES_MESSAGE: Final[str] = "Add at least one tool before you reserve."


def ensure_owner_or_staff(by_owner_or_staff: bool) -> None:
    """Refuse a cancellation by somebody who is neither the owner nor staff (BR-15).

    Raises:
        AuthorisationFailure: If the caller is neither.

    """
    if not by_owner_or_staff:
        raise AuthorisationFailure(NOT_YOURS_TO_CANCEL_MESSAGE, rule=CANCELLATION_RULE)


def branch_has_closed(now: datetime, branch_closed_at: datetime) -> bool:
    """Return True once the closing time of the first day has passed (BR-17).

    The branch is still open at the very instant it closes, so a booking is not
    a no show until the moment after.
    """
    return now > branch_closed_at


def ensure_no_show_is_due(
    reservation: Reservation, now: datetime, branch_closed_at: datetime | None
) -> None:
    """Refuse to call a confirmed booking a no show before it is one (BR-17).

    The sweep names the instant the collection branch closed on the first day
    of the hire, and the booking is a no show once that has passed. A member of
    staff at the counter names none. They can see that nobody came, so they may
    mark it from the start of the first day, by the clock in Cape Town.

    Raises:
        StateTransitionError: If the first day has not begun, for staff, or
            the branch has not closed yet, for the sweep.

    """
    if branch_closed_at is None:
        first_day_begins = business_instant(reservation.period.start, START_OF_DAY)
        if now >= first_day_begins:
            return
        message = FIRST_DAY_NOT_COME_MESSAGE
    elif branch_has_closed(now, branch_closed_at):
        return
    else:
        message = BRANCH_STILL_OPEN_MESSAGE
    raise StateTransitionError(
        message,
        from_status=reservation.status.value,
        to_status=ReservationStatus.NO_SHOW.value,
        rule=NO_SHOW_RULE,
    )


def mark_cancelled(reservation: Reservation, now: datetime, reason: str | None) -> None:
    """Record when and why a reservation was cancelled, and move it to CANCELLED."""
    reservation.cancelled_at = now
    reservation.cancellation_reason = reason
    reservation.status = ReservationStatus.CANCELLED


def ensure_every_unit_is_held(
    reservation: Reservation, taken: Mapping[UUID, Sequence[AssetAllocation]]
) -> None:
    """Refuse a hold in which a line is short, or was given a unit it should not hold.

    Every line has to be given exactly its quantity. Every allocation it was
    given has to be active, at the collection branch (BR-06) and for the
    period of the reservation. Nothing is attached to the reservation here, so
    a refusal leaves it as it was.

    Args:
        reservation: The draft being put on hold.
        taken: The allocations the allocator returned, by the line they are for.

    Raises:
        AllocationConflictError: If any of the three is not so.

    """
    period = reservation.period
    held_correctly = all(
        len(line.active_allocations()) + len(taken.get(line.id, ())) == line.quantity
        for line in reservation.lines
    ) and all(
        allocation.is_active()
        and allocation.branch_id == reservation.branch_id
        and allocation.period == period
        for allocations in taken.values()
        for allocation in allocations
    )
    if not held_correctly:
        raise AllocationConflictError(
            NOT_EVERY_UNIT_HELD_MESSAGE,
            branch_id=reservation.branch_id,
            period=period.as_postgres_daterange(),
        )
