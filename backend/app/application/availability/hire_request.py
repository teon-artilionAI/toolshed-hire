"""What may be asked about a hire, which a search and a quote agree on.

A visitor names a period and a quantity before there is a booking, when they
search availability and when they ask what a hire will cost. Both questions
are held to the limits a booking is held to, so an answer is never given for a
hire that could not then be booked.

The period is built as a `BookingPeriod`, which gives BR-02, the half open
bounds, and BR-03, the limit of twenty eight days.
`ensure_within_booking_window` gives BR-04 and BR-05, no start in the past and
none more than ninety days ahead.

Every refusal names the parameter that caused it, so the screen can put the
sentence beside the right input. The sentence is shown as it is written, so it
is plain and says what to do. The rule and the values that were tried travel
in the failure for the log.
"""

from __future__ import annotations

from datetime import date
from typing import Final

from app.application.availability.allocation import MAXIMUM_QUANTITY, MINIMUM_QUANTITY
from app.application.catalogue.read_models import ModelDetail
from app.application.refusal import refused
from app.domain.errors import DetailValue, ValidationFailure
from app.domain.period import (
    PERIOD_BOUNDS_RULE,
    BookingPeriod,
    InvalidBookingPeriod,
    ensure_within_booking_window,
)

# The names of the parameters a hire is asked about with, as a refusal reports them.
FROM_PARAMETER: Final[str] = "from"
TO_PARAMETER: Final[str] = "to"
QUANTITY_PARAMETER: Final[str] = "quantity"

QUANTITY_OUT_OF_RANGE_MESSAGE: Final[str] = (
    f"You can hire between {MINIMUM_QUANTITY} and {MAXIMUM_QUANTITY} of one tool at a time."
)
SINGLE_DAY: Final[int] = 1


def requested_period(start: date, end: date, today: date) -> BookingPeriod:
    """Build the period a visitor asked about, refusing one a booking would refuse.

    Args:
        start: The first day of the hire.
        end: The day the equipment comes back, which is free again.
        today: The current business day, from the clock.

    Raises:
        ValidationFailure: Naming `to` when the dates cannot form a hire
            period, and `from` when the hire starts in the past or beyond the
            booking horizon.

    """
    attempted: dict[str, DetailValue] = {"from": start.isoformat(), "to": end.isoformat()}
    try:
        period = BookingPeriod(start, end)
    except InvalidBookingPeriod as error:
        raise refused(
            TO_PARAMETER,
            str(error),
            {**attempted, "hire_days": (end - start).days},
            rule=error.rule,
        ) from error
    try:
        ensure_within_booking_window(period, today)
    except ValidationFailure as failure:
        raise refused(
            FROM_PARAMETER, failure.message, {**attempted, **failure.detail}, rule=failure.rule
        ) from failure
    return period


def ensure_quantity_in_range(quantity: int) -> None:
    """Refuse a quantity a reservation line could not carry.

    Raises:
        ValidationFailure: Naming `quantity`.

    """
    if not MINIMUM_QUANTITY <= quantity <= MAXIMUM_QUANTITY:
        raise refused(
            QUANTITY_PARAMETER,
            QUANTITY_OUT_OF_RANGE_MESSAGE,
            {"minimum": MINIMUM_QUANTITY, "maximum": MAXIMUM_QUANTITY, "received": quantity},
        )


def ensure_within_hire_limits(model: ModelDetail, period: BookingPeriod) -> None:
    """Refuse a period shorter or longer than the model may be hired for.

    Raises:
        ValidationFailure: Naming `to`, because the return day is the bound a
            visitor moves to make the hire longer or shorter.

    """
    detail: dict[str, DetailValue] = {
        "sku": model.sku,
        "hire_days": period.days,
        "min_hire_days": model.min_hire_days,
        "max_hire_days": model.max_hire_days,
    }
    if period.days > model.max_hire_days:
        raise refused(
            TO_PARAMETER,
            f"This tool can be hired for at most {_days_in_words(model.max_hire_days)}.",
            detail,
            rule=PERIOD_BOUNDS_RULE,
        )
    if period.days < model.min_hire_days:
        raise refused(
            TO_PARAMETER,
            f"This tool has to be hired for at least {_days_in_words(model.min_hire_days)}.",
            detail,
            rule=PERIOD_BOUNDS_RULE,
        )


def _days_in_words(days: int) -> str:
    """Return a number of days as a visitor reads it, "1 day" or "5 days"."""
    return f"{days} day" if days == SINGLE_DAY else f"{days} days"
