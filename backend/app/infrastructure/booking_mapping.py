"""The mapping between the reservation aggregate and its three tables.

A reservation is stored as one `reservation` row, a `reservation_line` row for
each line and an `asset_allocation` row for each unit a line holds or held.
The functions here turn the aggregate into rows for an insert, and turn rows
back into the aggregate for a use case that is going to change it.

Loading a set of reservations takes three statements however many there are,
one for the rows themselves, one for all of their lines and one for all of
their allocations. Nothing loops over the database.

A stored instant is handed to the domain with its time zone. PostgreSQL keeps
the zone. The in memory database of the fast tests drops it, and every instant
in this system is written in UTC, so one that arrives without a zone is given
UTC.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlmodel import Session, col, select

from app.domain import availability, booking
from app.domain.period import BookingPeriod
from app.infrastructure.models import AssetAllocation, Reservation, ReservationLine


def in_utc(instant: datetime | None) -> datetime | None:
    """Return a stored instant with its zone, giving UTC to one that lost it."""
    if instant is None or instant.tzinfo is not None:
        return instant
    return instant.replace(tzinfo=UTC)


def required_utc(instant: datetime | None, column: str) -> datetime:
    """Return a stored instant that is never null, with its zone.

    Raises:
        ValueError: If the instant is missing. The column is NOT NULL, so this
            means a row was read before the database had filled it in.

    """
    aware = in_utc(instant)
    if aware is None:
        raise ValueError(
            f"Attempted to read {column}, which is NOT NULL, and the row carries no value. "
            "Flush the row before reading it back."
        )
    return aware


def reservation_row(reservation: booking.Reservation) -> Reservation:
    """Return the table row for a reservation aggregate root."""
    return Reservation(
        id=reservation.id,
        reference=reservation.reference,
        customer_profile_id=reservation.customer_profile_id,
        branch_id=reservation.branch_id,
        status=reservation.status,
        start_date=reservation.period.start,
        end_date=reservation.period.end,
        subtotal_ex_vat=reservation.subtotal_ex_vat().amount,
        vat_amount=reservation.vat_amount,
        deposit_total=reservation.deposit_total,
        estimated_total_inc_vat=reservation.estimated_total_inc_vat,
        hold_expires_at=reservation.hold_expires_at,
        created_by_user_id=reservation.created_by_user_id,
        confirmed_at=reservation.confirmed_at,
        cancelled_at=reservation.cancelled_at,
        cancellation_reason=reservation.cancellation_reason,
        notes=reservation.notes,
    )


def line_row(line: booking.ReservationLine) -> ReservationLine:
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
        discount_percent=line.discount_percent,
        line_subtotal_ex_vat=line.line_subtotal_ex_vat,
    )


def aggregates_of(session: Session, rows: Sequence[Reservation]) -> list[booking.Reservation]:
    """Return the aggregate of each reservation row, with its lines and allocations.

    Args:
        session: The session the rows were read through.
        rows: The reservation rows, in the order the aggregates are wanted.

    """
    if not rows:
        return []
    line_rows = session.exec(
        select(ReservationLine)
        .where(col(ReservationLine.reservation_id).in_([row.id for row in rows]))
        .order_by(col(ReservationLine.reservation_id), col(ReservationLine.line_position))
    ).all()
    allocation_rows = session.exec(
        select(AssetAllocation)
        .where(col(AssetAllocation.reservation_line_id).in_([line.id for line in line_rows]))
        .order_by(col(AssetAllocation.allocated_at), col(AssetAllocation.id))
    ).all()

    allocations_by_line: dict[UUID, list[availability.AssetAllocation]] = defaultdict(list)
    for allocation_row in allocation_rows:
        allocations_by_line[allocation_row.reservation_line_id].append(
            _allocation_of(allocation_row)
        )
    lines_by_reservation: dict[UUID, list[booking.ReservationLine]] = defaultdict(list)
    for row in line_rows:
        lines_by_reservation[row.reservation_id].append(
            _line_of(row, allocations_by_line[row.id])
        )
    return [_reservation_of(row, lines_by_reservation[row.id]) for row in rows]


def _reservation_of(
    row: Reservation, lines: list[booking.ReservationLine]
) -> booking.Reservation:
    """Return the aggregate root for a reservation row and its lines."""
    return booking.Reservation(
        id=row.id,
        reference=row.reference,
        customer_profile_id=row.customer_profile_id,
        branch_id=row.branch_id,
        period=BookingPeriod(row.start_date, row.end_date),
        status=row.status,
        created_by_user_id=row.created_by_user_id,
        lines=lines,
        vat_amount=Decimal(row.vat_amount),
        deposit_total=Decimal(row.deposit_total),
        estimated_total_inc_vat=Decimal(row.estimated_total_inc_vat),
        hold_expires_at=in_utc(row.hold_expires_at),
        confirmed_at=in_utc(row.confirmed_at),
        cancelled_at=in_utc(row.cancelled_at),
        cancellation_reason=row.cancellation_reason,
        notes=row.notes,
    )


def _line_of(
    row: ReservationLine, allocations: list[availability.AssetAllocation]
) -> booking.ReservationLine:
    """Return the domain line for a line row and its allocations."""
    # Decimal() on each figure. The driver already returns Decimal for a
    # NUMERIC column, and wrapping keeps that true whatever it returns,
    # because money is never a float (BR-22).
    return booking.ReservationLine(
        id=row.id,
        reservation_id=row.reservation_id,
        product_model_id=row.product_model_id,
        quantity=row.quantity,
        line_position=row.line_position,
        daily_rate_snapshot=Decimal(row.daily_rate_snapshot),
        weekly_rate_snapshot=Decimal(row.weekly_rate_snapshot),
        deposit_snapshot=Decimal(row.deposit_snapshot),
        late_fee_per_day_snapshot=Decimal(row.late_fee_per_day_snapshot),
        replacement_value_snapshot=Decimal(row.replacement_value_snapshot),
        discount_percent=Decimal(row.discount_percent),
        line_subtotal_ex_vat=Decimal(row.line_subtotal_ex_vat),
        allocations=allocations,
    )


def _allocation_of(row: AssetAllocation) -> availability.AssetAllocation:
    """Return the domain allocation for an allocation row."""
    return availability.AssetAllocation(
        id=row.id,
        reservation_line_id=row.reservation_line_id,
        asset_id=row.asset_id,
        branch_id=row.branch_id,
        period=BookingPeriod(row.start_date, row.end_date),
        allocated_at=required_utc(row.allocated_at, "asset_allocation.allocated_at"),
        released_at=in_utc(row.released_at),
        release_reason=row.release_reason,
    )
