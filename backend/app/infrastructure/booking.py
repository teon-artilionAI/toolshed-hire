"""The SQL repository of the booking module, for reservations and their lines.

It maps the domain aggregate to the SQLModel table classes. The reservation row
is written before its lines, because a line carries a foreign key to it.

The reference number comes from a PostgreSQL sequence created in the migration.
Deriving it from a row count would produce a duplicate under exactly the
concurrency the allocation path exists to survive.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlmodel import Session

from app.domain import booking as domain
from app.infrastructure.models import Reservation, ReservationLine
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
