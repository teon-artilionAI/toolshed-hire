"""The SQL repository of the booking module, for reservations and their lines.

It maps the domain aggregate to the SQLModel table classes. The reservation row
is written before its lines, because a line carries a foreign key to it.

The reference number comes from a PostgreSQL sequence created in the migration.
Deriving it from a row count would produce a duplicate under exactly the
concurrency the allocation path exists to survive.

`find_summary` is where ownership is enforced (BR-42). A restricted scope
becomes a join to the customer profile and a condition on its account, in the
same statement that looks the reservation up. A reservation that belongs to
somebody else is therefore never read, so nothing can be said about it.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import text
from sqlmodel import Session, col, select

from app.application.booking.read_models import ReservationSummary
from app.application.ownership import OwnerScope
from app.domain import booking as domain
from app.infrastructure.models import CustomerProfile, Reservation, ReservationLine
from app.infrastructure.schema_ddl import REFERENCE_SEQUENCE

logger = logging.getLogger(__name__)


class SqlReservationRepository:
    """Writes reservations through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to the session of its unit of work."""
        self._session = session

    def add(self, reservation: domain.Reservation) -> None:
        """Write a new reservation and its lines inside the current transaction."""
        logger.debug(
            "booking.reservation_insert_started",
            extra={"reference": reservation.reference, "line_count": len(reservation.lines)},
        )
        self._session.add(_reservation_row(reservation))
        self._session.flush()
        self._session.add_all([_line_row(line) for line in reservation.lines])
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

    def find_summary(self, reservation_id: UUID, scope: OwnerScope) -> ReservationSummary | None:
        """Return one reservation, if it exists and the scope lets the reader see it."""
        statement = select(Reservation).where(col(Reservation.id) == reservation_id)
        if scope.customer_user_id is not None:
            statement = statement.join(
                CustomerProfile, col(CustomerProfile.id) == col(Reservation.customer_profile_id)
            ).where(col(CustomerProfile.user_account_id) == scope.customer_user_id)
        row = self._session.exec(statement).first()
        logger.debug(
            "booking.reservation_lookup_finished",
            extra={
                "reservation_id": str(reservation_id),
                "restricted_to_owner": scope.is_restricted,
                "found": row is not None,
            },
        )
        if row is None:
            return None
        return ReservationSummary(
            id=row.id,
            reference=row.reference,
            status=row.status,
            branch_id=row.branch_id,
            start_date=row.start_date,
            end_date=row.end_date,
        )


def _reservation_row(reservation: domain.Reservation) -> Reservation:
    """Return the table row for a reservation aggregate root."""
    return Reservation(
        id=reservation.id,
        reference=reservation.reference,
        customer_profile_id=reservation.customer_profile_id,
        branch_id=reservation.branch_id,
        status=reservation.status,
        start_date=reservation.period.start,
        end_date=reservation.period.end,
        subtotal_ex_vat=reservation.subtotal_ex_vat,
        vat_amount=reservation.vat_amount,
        deposit_total=reservation.deposit_total,
        estimated_total_inc_vat=reservation.estimated_total_inc_vat,
        hold_expires_at=reservation.hold_expires_at,
        created_by_user_id=reservation.created_by_user_id,
    )


def _line_row(line: domain.ReservationLine) -> ReservationLine:
    """Return the table row for one reservation line."""
    return ReservationLine(
        id=line.id,
        reservation_id=line.reservation_id,
        product_model_id=line.product_model_id,
        quantity=line.quantity,
        line_position=line.line_position,
        daily_rate_snapshot=line.daily_rate_snapshot,
        weekly_rate_snapshot=line.weekly_rate_snapshot,
        deposit_snapshot=line.deposit_snapshot,
        late_fee_per_day_snapshot=line.late_fee_per_day_snapshot,
        replacement_value_snapshot=line.replacement_value_snapshot,
        line_subtotal_ex_vat=line.line_subtotal_ex_vat,
    )
