"""The SQL repository of the booking module, for reservations and their lines.

It maps the domain aggregate to the SQLModel table classes and back. The
reservation row is written before its lines, because a line carries a foreign
key to it.

The reference number comes from a PostgreSQL sequence created in the migration.
Deriving it from a row count would produce a duplicate under exactly the
concurrency the allocation path exists to survive.

A reservation that is going to change is read with `SELECT ... FOR UPDATE`, so
two requests acting on one booking take turns. Ownership is enforced in that
same statement (BR-42). A restricted scope becomes a join to the customer
profile and a condition on its account, so a reservation that belongs to
somebody else is never read and nothing can be said about it.

The lock here waits. It does not skip. Skipping a locked row is right for
candidate units, where any free unit will do, and the asset repository is the
one place that does it. A reservation is a particular row, so the second
request waits for the first and then reads what it left.

`lock_due_holds` and `lock_due_no_shows` are the two queries of the lazy sweep
(BR-13, BR-17). The status condition of each is written as the literal its
partial index is filtered on, `ix_reservation_hold_expiry` for the holds and
`ix_reservation_confirmed_start` for the no shows, so the planner can use that
index whatever plan it caches, and a sweep only ever reads rows that could be
due. The no show query joins the three branches for their closing time and
locks the reservations alone.

`count_no_shows_since` counts the strikes of one customer through
`ix_reservation_customer_start` (BR-18).

The reads that return read models are in `app.infrastructure.booking_query`.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Final
from uuid import UUID

from sqlalchemy import func, literal_column, or_, text
from sqlmodel import Session, col, select

from app.application.booking.ports import DueNoShow
from app.application.booking.read_models import (
    ReservationDetail,
    ReservationKey,
    ReservationPage,
    ReservationSearch,
)
from app.application.ownership import OwnerScope
from app.domain import booking as domain
from app.domain.business_time import in_business_time
from app.domain.enums import ReservationStatus
from app.infrastructure.booking_mapping import aggregates_of, line_row, reservation_row
from app.infrastructure.booking_query import SqlReservationReads, key_condition
from app.infrastructure.models import AssetAllocation, Branch, CustomerProfile, Reservation
from app.infrastructure.schema_ddl import REFERENCE_SEQUENCE

logger = logging.getLogger(__name__)

# The statuses the partial indexes behind the sweep are filtered on, written
# into the statement as literals. A bound parameter here would stop a cached
# plan from using those indexes.
HELD_STATUS_LITERAL: Final[str] = f"'{ReservationStatus.HELD.value}'"
CONFIRMED_STATUS_LITERAL: Final[str] = f"'{ReservationStatus.CONFIRMED.value}'"


class SqlReservationRepository:
    """Reads and writes reservations through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to the session of its unit of work."""
        self._session = session
        self._reads = SqlReservationReads(session)

    def add(self, reservation: domain.Reservation) -> None:
        """Write a new reservation and its lines inside the current transaction."""
        logger.debug(
            "booking.reservation_insert_started",
            extra={"reference": reservation.reference, "line_count": len(reservation.lines)},
        )
        self._session.add(reservation_row(reservation))
        self._session.flush()
        self._session.add_all([line_row(line) for line in reservation.lines])
        self._session.flush()
        logger.debug(
            "booking.reservation_insert_finished",
            extra={"reference": reservation.reference, "reservation_id": str(reservation.id)},
        )

    def next_reference(self, year: int) -> str:
        """Return the next reservation reference, for example TSH-R-26-000124."""
        logger.debug("booking.reference_draw_started", extra={"sequence": REFERENCE_SEQUENCE})
        next_value = self._session.execute(
            text(f"SELECT nextval('{REFERENCE_SEQUENCE}')")
        ).scalar_one()
        reference = domain.format_reference(year, int(next_value))
        logger.debug("booking.reference_draw_finished", extra={"reference": reference})
        return reference

    def find_for_update(
        self, key: ReservationKey, scope: OwnerScope
    ) -> domain.Reservation | None:
        """Return one reservation with its lines and allocations, locked for a change."""
        statement = select(Reservation).where(key_condition(key))
        if scope.customer_user_id is not None:
            statement = statement.join(
                CustomerProfile, col(CustomerProfile.id) == col(Reservation.customer_profile_id)
            ).where(col(CustomerProfile.user_account_id) == scope.customer_user_id)
        # populate_existing, so a row this session already holds is read again
        # under the lock and not answered from memory.
        statement = statement.with_for_update(of=Reservation).execution_options(
            populate_existing=True
        )
        row = self._session.exec(statement).first()
        logger.debug(
            "booking.reservation_locked",
            extra={
                "reservation": str(key),
                "restricted_to_owner": scope.is_restricted,
                "found": row is not None,
            },
        )
        if row is None:
            return None
        return aggregates_of(self._session, [row])[0]

    def save(self, reservation: domain.Reservation) -> None:
        """Write the status, the dates of its moves and the releases of a reservation.

        Raises:
            LookupError: If the reservation was never stored. A move can only
                be saved for a reservation that was read through this session.

        """
        row = self._session.get(Reservation, reservation.id)
        if row is None:
            raise LookupError(
                f"Attempted to save reservation {reservation.reference}, which is not in "
                "the database. Add it before saving a change to it."
            )
        row.status = reservation.status
        row.hold_expires_at = reservation.hold_expires_at
        row.confirmed_at = reservation.confirmed_at
        row.cancelled_at = reservation.cancelled_at
        row.cancellation_reason = reservation.cancellation_reason
        self._session.add(row)
        released_count = self._write_releases(reservation)
        self._session.flush()
        logger.debug(
            "booking.reservation_saved",
            extra={
                "reference": reservation.reference,
                "status": reservation.status.value,
                "released_count": released_count,
            },
        )

    def lock_due_holds(self, now: datetime, limit: int) -> list[domain.Reservation]:
        """Lock and return up to `limit` held reservations whose hold has run out."""
        statement = (
            select(Reservation)
            .where(
                col(Reservation.status) == literal_column(HELD_STATUS_LITERAL),
                col(Reservation.hold_expires_at) < now,
            )
            .order_by(col(Reservation.hold_expires_at), col(Reservation.id))
            .limit(limit)
            .with_for_update(of=Reservation)
            .execution_options(populate_existing=True)
        )
        rows = self._session.exec(statement).all()
        logger.debug(
            "booking.due_holds_locked", extra={"due_count": len(rows), "limit": limit}
        )
        return aggregates_of(self._session, rows)

    def lock_due_no_shows(self, now: datetime, limit: int) -> list[DueNoShow]:
        """Lock and return up to `limit` confirmed reservations whose branch has closed on day one.

        A first day before today is always past its closing time. A first day
        of today is past it once the clock in Cape Town is later than the time
        the branch closes. The range on the first day is stated on its own as
        well, so the partial index can bound the scan.
        """
        local = in_business_time(now)
        today, time_of_day = local.date(), local.time()
        statement = (
            select(Reservation, col(Branch.closes_at))
            .join(Branch, col(Branch.id) == col(Reservation.branch_id))
            .where(
                col(Reservation.status) == literal_column(CONFIRMED_STATUS_LITERAL),
                col(Reservation.start_date) <= today,
                or_(col(Reservation.start_date) < today, col(Branch.closes_at) < time_of_day),
            )
            .order_by(col(Reservation.start_date), col(Reservation.id))
            .limit(limit)
            .with_for_update(of=Reservation)
            .execution_options(populate_existing=True)
        )
        rows = self._session.exec(statement).all()
        logger.debug(
            "booking.due_no_shows_locked", extra={"due_count": len(rows), "limit": limit}
        )
        aggregates = aggregates_of(self._session, [row for row, _closes_at in rows])
        return [
            DueNoShow(reservation=reservation, branch_closes_at=closes_at)
            for reservation, (_row, closes_at) in zip(aggregates, rows, strict=True)
        ]

    def count_no_shows_since(self, customer_profile_id: UUID, started_after: date) -> int:
        """Return how many of a customer's reservations that started after a day were no shows."""
        statement = (
            select(func.count())
            .select_from(Reservation)
            .where(
                col(Reservation.customer_profile_id) == customer_profile_id,
                col(Reservation.start_date) > started_after,
                col(Reservation.status) == ReservationStatus.NO_SHOW,
            )
        )
        counted = self._session.exec(statement).one()
        logger.debug(
            "booking.no_shows_counted",
            extra={
                "customer_profile_id": str(customer_profile_id),
                "started_after": started_after.isoformat(),
                "no_show_count": counted,
            },
        )
        return counted

    def find_detail(self, key: ReservationKey, scope: OwnerScope) -> ReservationDetail | None:
        """Return one reservation as a read model, if the scope lets the caller see it."""
        return self._reads.find_detail(key, scope)

    def search(self, search: ReservationSearch, scope: OwnerScope) -> ReservationPage:
        """Return one page of the reservations the scope lets the caller see, newest first."""
        return self._reads.search(search, scope)

    def _write_releases(self, reservation: domain.Reservation) -> int:
        """Write the release of every allocation the aggregate let go, and count them.

        Only a row that is still active is touched, so a release that was
        already written keeps the time and the reason it was given.
        """
        released = {
            allocation.id: allocation
            for line in reservation.lines
            for allocation in line.allocations
            if not allocation.is_active()
        }
        if not released:
            return 0
        rows = self._session.exec(
            select(AssetAllocation).where(
                col(AssetAllocation.id).in_(list(released)),
                col(AssetAllocation.released_at).is_(None),
            )
        ).all()
        for row in rows:
            allocation = released[row.id]
            row.released_at = allocation.released_at
            row.release_reason = allocation.release_reason
            self._session.add(row)
        return len(rows)
