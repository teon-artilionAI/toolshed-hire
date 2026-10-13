"""The owner's reads of the closure days and of what a closure strands.

Nothing here writes. The live closures in a span are one statement through
`ix_closure_day_live_day`, which holds only the live closures, joined to the
branch for its code. A year holds a handful of them.

A closure strands two things. A held or confirmed booking collected or brought
back that day, and a hire still out whose equipment is due back that day. Both
are read as the two halves of one union, joined to the customer for the name
and number and to the branch for its code, so the read is two statements, the
count and the list, however many there are.

The hires due back stand on `ix_rental_open_due_back`, which holds only the
hires still out. At one branch the start of a booking stands on
`ix_reservation_branch_start`. No index leads with the last day of a booking,
so the end is filtered from the rows of the branch, or of every branch when
none is named. The table holds a few thousand bookings a year, so that stays
cheap. A closure for every branch on a far larger book would want an index on
the end date, which is a migration of its own and not part of this read.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Final
from uuid import UUID

from sqlalchemy import ColumnElement, RowMapping, SelectBase, String, func, literal, union_all
from sqlalchemy import select as select_columns
from sqlmodel import Session, col, or_, select

from app.application.trading.closure_models import (
    HIRE_DUE_BACK,
    StrandedBooking,
    StrandedBookings,
)
from app.domain import closure_day as domain
from app.domain.enums import RentalStatus, ReservationStatus
from app.domain.trading_calendar import COLLECTION_DAY, RETURN_DAY
from app.infrastructure.closure_days import closure_of
from app.infrastructure.models import (
    Branch,
    ClosureDay,
    CustomerProfile,
    Rental,
    Reservation,
)
from app.infrastructure.query_log import logged_query

logger = logging.getLogger(__name__)

# The bookings that still mean a customer will come to the counter.
STRANDABLE_STATUSES: Final[tuple[ReservationStatus, ...]] = (
    ReservationStatus.HELD,
    ReservationStatus.CONFIRMED,
)
# The hires whose equipment is still out with the customer.
OUT_ON_HIRE_STATUSES: Final[tuple[RentalStatus, ...]] = (
    RentalStatus.OPEN,
    RentalStatus.PARTIALLY_RETURNED,
    RentalStatus.OVERDUE,
)
STRANDED_SUBQUERY: Final[str] = "stranded"
# The columns both halves of the union share, and which half a row came from.
REFERENCE: Final[str] = "reference"
BRANCH_CODE: Final[str] = "branch_code"
CUSTOMER_NAME: Final[str] = "customer_name"
CUSTOMER_PHONE: Final[str] = "customer_phone"
START_DATE: Final[str] = "start_date"
END_DATE: Final[str] = "end_date"
SOURCE: Final[str] = "source"
BOOKING_SOURCE: Final[str] = "booking"
HIRE_SOURCE: Final[str] = "hire"


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
        """Return the bookings and the hires out that a closure of the day strands, by start.

        Two statements however many there are, the count and the list, each
        over the two halves of one union.
        """
        stranded = union_all(
            _bookings_starting_or_ending(branch_id, day), _hires_due_back(branch_id, day)
        ).subquery(STRANDED_SUBQUERY)
        listed = (
            select_columns(stranded)
            .order_by(stranded.c.start_date, stranded.c.reference)
            .limit(limit)
        )
        counted = select_columns(func.count()).select_from(stranded)
        filters = {
            "branch_id": str(branch_id) if branch_id else None,
            "day": day.isoformat(),
            "limit": limit,
        }
        with logged_query(logger, "trading.stranded_bookings", filters) as outcome:
            total = int(self._session.execute(counted).scalar_one())
            rows = list(self._session.execute(listed).mappings().all())
            outcome.row_count = len(rows)
        return StrandedBookings(items=tuple(_stranded_of(row, day) for row in rows), total=total)


def _bookings_starting_or_ending(branch_id: UUID | None, day: date) -> SelectBase:
    """Return the held and confirmed bookings collected or brought back on a day."""
    conditions: list[ColumnElement[bool]] = [
        col(Reservation.status).in_(STRANDABLE_STATUSES),
        or_(col(Reservation.start_date) == day, col(Reservation.end_date) == day),
    ]
    if branch_id is not None:
        conditions.append(col(Reservation.branch_id) == branch_id)
    return (
        select_columns(
            col(Reservation.reference).label(REFERENCE),
            col(Branch.code).label(BRANCH_CODE),
            col(CustomerProfile.display_name).label(CUSTOMER_NAME),
            col(CustomerProfile.contact_phone).label(CUSTOMER_PHONE),
            col(Reservation.start_date).label(START_DATE),
            col(Reservation.end_date).label(END_DATE),
            literal(BOOKING_SOURCE, String).label(SOURCE),
        )
        .select_from(Reservation)
        .join(CustomerProfile, col(CustomerProfile.id) == col(Reservation.customer_profile_id))
        .join(Branch, col(Branch.id) == col(Reservation.branch_id))
        .where(*conditions)
    )


def _hires_due_back(branch_id: UUID | None, day: date) -> SelectBase:
    """Return the hires still out whose equipment is due back on a day.

    `returned_at IS NULL` is what every hire still out has, and it is the
    predicate of `ix_rental_open_due_back`, so the planner reads the day off
    that index.
    """
    conditions: list[ColumnElement[bool]] = [
        col(Rental.status).in_(OUT_ON_HIRE_STATUSES),
        col(Rental.returned_at).is_(None),
        col(Rental.due_back_on) == day,
    ]
    if branch_id is not None:
        conditions.append(col(Rental.branch_id) == branch_id)
    return (
        select_columns(
            col(Rental.reference).label(REFERENCE),
            col(Branch.code).label(BRANCH_CODE),
            col(CustomerProfile.display_name).label(CUSTOMER_NAME),
            col(CustomerProfile.contact_phone).label(CUSTOMER_PHONE),
            col(Reservation.start_date).label(START_DATE),
            col(Rental.due_back_on).label(END_DATE),
            literal(HIRE_SOURCE, String).label(SOURCE),
        )
        .select_from(Rental)
        .join(Reservation, col(Reservation.id) == col(Rental.reservation_id))
        .join(CustomerProfile, col(CustomerProfile.id) == col(Reservation.customer_profile_id))
        .join(Branch, col(Branch.id) == col(Rental.branch_id))
        .where(*conditions)
    )


def _stranded_of(row: RowMapping, day: date) -> StrandedBooking:
    """Return one row of the union as the booking or the hire it stands for."""
    start: date = row[START_DATE]
    if row[SOURCE] == HIRE_SOURCE:
        hire_day = HIRE_DUE_BACK
    else:
        hire_day = COLLECTION_DAY if start == day else RETURN_DAY
    return StrandedBooking(
        reference=row[REFERENCE],
        branch_code=row[BRANCH_CODE],
        customer_name=row[CUSTOMER_NAME],
        customer_phone=row[CUSTOMER_PHONE],
        start=start,
        end=row[END_DATE],
        hire_day=hire_day,
    )
