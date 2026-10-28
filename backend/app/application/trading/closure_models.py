"""What the reads and the writes of the closure days hand back.

The owner's list holds two kinds of closed day. A public holiday closes every
branch and is listed once, with no branch and no key, because nothing can
cancel it. A closure day names its branch, or none when it closes every
branch, and carries its key so it can be cancelled. The days a branch never
opens, its Sundays, are not listed. The owner knows them, and a year of them
would drown the days that matter.

A stranded booking is one a new closure would leave starting or ending on a
day the branch does not trade, or a hire still out whose equipment would be
due back on it. It names the customer and their number, because the owner
rings each of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final
from uuid import UUID

# What a hire still out is to the owner's list. A booking is a `collection` or
# a `return`, as the trading calendar names the two days of a hire.
HIRE_DUE_BACK: Final[str] = "due_back"


@dataclass(frozen=True, slots=True)
class ClosedDayEntry:
    """One day the owner's list shows as closed.

    Attributes:
        day: The calendar day.
        branch_code: The branch it closes, or None for every branch.
        reason: Why, as a customer reads it.
        kind: `public_holiday` or `closure`, as the trading calendar names them.
        closure_id: The key of a closure day, or None for a public holiday.

    """

    day: date
    branch_code: str | None
    reason: str
    kind: str
    closure_id: UUID | None


@dataclass(frozen=True, slots=True)
class StrandedBooking:
    """A booking or a hire out that falls on a day about to close.

    A held or confirmed booking that starts or ends that day, or a hire still
    out whose equipment is due back that day.

    Attributes:
        reference: The booking reference, for example TSH-R-26-000124, or the
            hire's, for example TSH-H-26-000098.
        branch_code: The collection branch.
        customer_name: The name on the customer's profile.
        customer_phone: The number to ring.
        start: The day the hire is collected, or was.
        end: The day it comes back, or is due back.
        hire_day: `collection` when a booking starts that day, `return` when
            it ends that day, and `due_back` for a hire out due back that day.

    """

    reference: str
    branch_code: str
    customer_name: str
    customer_phone: str
    start: date
    end: date
    hire_day: str


@dataclass(frozen=True, slots=True)
class StrandedBookings:
    """The bookings a closure would strand, up to a limit, and how many there are."""

    items: tuple[StrandedBooking, ...]
    total: int
