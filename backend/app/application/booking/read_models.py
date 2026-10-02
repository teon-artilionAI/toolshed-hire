"""What a read of the booking module hands back.

A read returns a small frozen dataclass and never a table row, the same way
the catalogue reads do. A summary carries what identifies a booking and where
it stands. It gains a field when a screen first needs one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.domain.enums import ReservationStatus


@dataclass(frozen=True, slots=True)
class ReservationSummary:
    """One reservation, as its owner or a member of staff may see it.

    Attributes:
        id: The reservation key.
        reference: The reference a customer quotes, for example TSH-R-26-000124.
        status: Where the booking stands.
        branch_id: The collection branch.
        start_date: The first day of the hire.
        end_date: The day the equipment comes back, which is not charged.

    """

    id: UUID
    reference: str
    status: ReservationStatus
    branch_id: UUID
    start_date: date
    end_date: date
