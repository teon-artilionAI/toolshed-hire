"""The two rules about a booking nobody came to collect (BR-17, BR-18).

A confirmed reservation that is not collected becomes a no show. The move
itself belongs to the reservation states, which decide when it is due. What
lives here is what the move means for the customer and for the counter screen.

Three no shows inside a rolling twelve months put an account on hold (BR-18).
The three are counted from the reservations themselves, by their start dates,
and not from the running total on the profile. That total only ever goes up,
so it would keep counting a no show from two years ago against somebody who
has hired well ever since.

The window is the twelve months that end today. A no show whose hire started
on the same calendar day a year ago is just outside it. 29 February has no
such day in the year before, so 28 February stands in for it.

Only an account in good standing is put on hold. One already on hold stays as
it is, and a blacklisted one is never softened to a hold. Lifting a hold is
for an administrator and is not done here.

`no_show_refusal` is the rule staff are held to when they mark a booking by
hand, in the words the move would refuse with. The counter's diary reads it to
decide whether to offer the button, so the button and the route agree.
"""

from __future__ import annotations

from datetime import date
from typing import Final

from app.domain.enums import AccountStatus, ReservationStatus
from app.domain.states import state_for
from app.domain.states.base import MARKED_AS_NOT_COLLECTED, NO_SHOW_MOVE, refusal_sentence
from app.domain.states.guards import FIRST_DAY_NOT_COME_MESSAGE

# The no show that puts an account in good standing on hold (BR-18).
STRIKE_LIMIT: Final[int] = 3
# The length of the rolling window the strikes are counted in.
STRIKE_WINDOW_YEARS: Final[int] = 1
LEAP_DAY_MONTH: Final[int] = 2
LEAP_DAY: Final[int] = 29
DAY_BEFORE_LEAP_DAY: Final[int] = 28


def strike_window_opens_after(today: date) -> date:
    """Return the last day before the rolling twelve months that end today.

    A no show counts towards a hold when its hire started after this day.

    Args:
        today: The current business day, from the clock.

    """
    year = today.year - STRIKE_WINDOW_YEARS
    if (today.month, today.day) == (LEAP_DAY_MONTH, LEAP_DAY):
        return date(year, LEAP_DAY_MONTH, DAY_BEFORE_LEAP_DAY)
    return today.replace(year=year)


def standing_after_strikes(standing: AccountStatus, strikes_in_window: int) -> AccountStatus:
    """Return the standing of a customer once their no shows in the window are counted.

    Args:
        standing: The account status the customer has now.
        strikes_in_window: How many of their reservations that started inside
            the rolling twelve months were not collected, the newest included.

    Returns:
        ON_HOLD for an account in good standing that has reached the limit,
        and the standing it already had otherwise.

    """
    if standing is AccountStatus.ACTIVE and strikes_in_window >= STRIKE_LIMIT:
        return AccountStatus.ON_HOLD
    return standing


def no_show_refusal(status: ReservationStatus, start_date: date, today: date) -> str | None:
    """Return why staff cannot mark a reservation as not collected today, or None when they can.

    The two checks are the ones the move makes when staff ask for it, in the
    same order. A reservation that is not confirmed is refused first, then one
    whose hire has not started yet.

    Args:
        status: Where the reservation stands.
        start_date: The first day of its hire.
        today: The current business day, from the clock.

    """
    if not state_for(status).permits(NO_SHOW_MOVE):
        return refusal_sentence(status, MARKED_AS_NOT_COLLECTED)
    if today < start_date:
        return FIRST_DAY_NOT_COME_MESSAGE
    return None
