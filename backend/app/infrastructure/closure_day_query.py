"""The owner's reads of the closure days and of the bookings a closure strands.

Nothing here writes. The live closures in a span are one statement through
`ix_closure_day_live_day`, which holds only the live closures, joined to the
branch for its code. A year holds a handful of them.

The bookings that start or end on a day are two statements, the count and the
list, joined to the customer for the name and number and to the branch for its
code. At one branch the start stands on `ix_reservation_branch_start`. No index
leads with the last day of a hire, so the end is filtered from the rows of the
branch, or of every branch when none is named. The table holds a few thousand
bookings a year, so that stays cheap. A closure for every branch on a far
larger book would want an index on the end date, which is a migration of its
own and not part of this read.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Final
from uuid import UUID

from sqlalchemy import ColumnElement, func
from sqlmodel import Session, col, or_, select

from app.application.trading.closure_models import StrandedBooking, StrandedBookings
from app.domain import closure_day as domain
from app.domain.enums import ReservationStatus
from app.domain.trading_calendar import COLLECTION_DAY, RETURN_DAY
from app.infrastructure.closure_days import closure_of
from app.infrastructure.models import Branch, ClosureDay, CustomerProfile, Reservation
from app.infrastructure.query_log import logged_query

logger = logging.getLogger(__name__)

# The bookings that still mean a customer will come to the counter.
STRANDABLE_STATUSES: Final[tuple[ReservationStatus, ...]] = (
    ReservationStatus.HELD,
    ReservationStatus.CONFIRMED,
)


class SqlClosureDayQuery:
    """Reads the closure days and the bookings on a day through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the reads to the session of the request."""
        self._session = session

    def live_between(self, first: date, last: date) -> list[domain.ClosureDay]:
        """Return every live closure from `first` to `last`, both included, by day."""
        statement = (
            select(ClosureDay, col(Branch.code))
            .outerjoin(Branch, col(Branch.id) == col(ClosureDay.branch_id))
            .where(
                col(ClosureDay.cancelled_at).is_(None),
                col(ClosureDay.day) >= first,
                col(ClosureDay.day) <= last,
            )
            .order_by(col(ClosureDay.day), col(Branch.code))
        )
        filters = {"from": first.isoformat(), "to": last.isoformat()}
        with logged_query(logger, "trading.live_closures", filters) as outcome:
            rows = self._session.exec(statement).all()
            outcome.row_count = len(rows)
        return [closure_of(row, code) for row, code in rows]

    def bookings_on(self, branch_id: UUID | None, day: date, limit: int) -> StrandedBookings:
        """Return the held and confirmed bookings that start or end on a day, by start."""
        conditions = _stranded_on(branch_id, day)
        statement = (
            select(
                Reservation,
                col(Branch.code),
                col(CustomerProfile.display_name),
                col(CustomerProfile.contact_phone),
            )
            .join(CustomerProfile, col(CustomerProfile.id) == col(Reservation.customer_profile_id))
            .join(Branch, col(Branch.id) == col(Reservation.branch_id))
            .where(*conditions)
            .order_by(col(Reservation.start_date), col(Reservation.reference))
            .limit(limit)
        )
        filters = {
            "branch_id": str(branch_id) if branch_id else None,
            "day": day.isoformat(),
            "limit": limit,
        }
        with logged_query(logger, "trading.stranded_bookings", filters) as outcome:
            total = self._session.exec(
                select(func.count()).select_from(Reservation).where(*conditions)
            ).one()
            rows = self._session.exec(statement).all()
            outcome.row_count = len(rows)
        items = tuple(
            StrandedBooking(
                reference=booking.reference,
                branch_code=code,
                customer_name=name,
                customer_phone=phone,
                start=booking.start_date,
                end=booking.end_date,
                hire_day=COLLECTION_DAY if booking.start_date == day else RETURN_DAY,
            )
            for booking, code, name, phone in rows
        )
        return StrandedBookings(items=items, total=int(total))


def _stranded_on(branch_id: UUID | None, day: date) -> list[ColumnElement[bool]]:
    """Return the conditions of a held or confirmed booking that starts or ends on a day."""
    conditions: list[ColumnElement[bool]] = [
        col(Reservation.status).in_(STRANDABLE_STATUSES),
        or_(col(Reservation.start_date) == day, col(Reservation.end_date) == day),
    ]
    if branch_id is not None:
        conditions.append(col(Reservation.branch_id) == branch_id)
    return conditions
