"""What the reads and the writes of the closure days hand back (B9.5).

The owner's list holds two kinds of closed day. A public holiday closes every
branch and is listed once, with no branch and no key, because nothing can
cancel it. A closure day names its branch, or none when it closes every
branch, and carries its key so it can be cancelled. The days a branch never
opens, its Sundays, are not listed. The owner knows them, and a year of them
would drown the days that matter.

A stranded booking is one a new closure would leave starting or ending on a
day the branch does not trade. It names the customer and their number,
because the owner rings each of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID


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
    """A held or confirmed booking that starts or ends on a day about to close.

    Attributes:
        reference: The booking reference, for example TSH-R-26-000124.
        branch_code: The collection branch.
        customer_name: The name on the customer's profile.
        customer_phone: The number to ring.
        start: The day the hire is collected.
        end: The day it comes back.
        hire_day: `collection` when it starts that day, `return` when it ends.

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
