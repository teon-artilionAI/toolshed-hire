"""The reservation use case that the skeleton endpoint exercises.

It creates a reservation and one line, allocates specific assets to that line
and commits, all in one transaction. Either the whole booking exists or none of
it does, which is BR-09 stated as code rather than as a comment.

The reference number comes from a PostgreSQL sequence created in the migration.
Deriving it from a row count would produce a duplicate under exactly the
concurrency this skeleton exists to prove correct.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Final
from uuid import UUID

from sqlalchemy import text
from sqlmodel import Session

from app.application.allocate import AllocatedAsset, AllocationCommand, allocate_assets
from app.domain.enums import ReservationStatus
from app.domain.errors import NotFound, ValidationFailure
from app.domain.period import BookingPeriod
from app.infrastructure.models import Branch, ProductModel, Reservation, ReservationLine
from app.infrastructure.schema_ddl import REFERENCE_SEQUENCE

logger = logging.getLogger(__name__)

REFERENCE_PREFIX: Final[str] = "TSH-R"
FIRST_LINE_POSITION: Final[int] = 1
MAXIMUM_DAYS_AHEAD: Final[int] = 90


@dataclass(frozen=True, slots=True)
class ReservationCommand:
    """A request to book `quantity` units of one product model at one branch."""

    customer_user_id: UUID
    created_by_user_id: UUID
    branch_id: UUID
    product_model_id: UUID
    period: BookingPeriod
    quantity: int


@dataclass(frozen=True, slots=True)
class ReservationResult:
    """The committed booking, flattened for the API layer."""

    reservation_id: UUID
    reference: str
    reservation_line_id: UUID
    status: ReservationStatus
    allocated: list[AllocatedAsset]


def create_reservation_with_allocation(
    session: Session, command: ReservationCommand, *, today: date | None = None
) -> ReservationResult:
    """Create a held reservation with its assets allocated, in one transaction.

    Args:
        session: An open session. This function owns the commit.
        command: The booking to create.
        today: Override for the current date, used by tests.

    Returns:
        The committed reservation, its line and the units held.

    Raises:
        NotFound: If the branch or the product model does not exist.
        ValidationFailure: If the period starts in the past or too far ahead.
        AssetUnavailableConflict: If the units could not be held. Raised by the
            allocation use case, which has already rolled the transaction back.

    """
    current_day = today or datetime.now(UTC).date()
    _validate_period_window(command.period, current_day)

    branch = session.get(Branch, command.branch_id)
    if branch is None:
        raise NotFound(
            f"Attempted to create a reservation at branch {command.branch_id}, "
            "which does not exist.",
            {"branch_id": str(command.branch_id)},
        )
    product_model = session.get(ProductModel, command.product_model_id)
    if product_model is None:
        raise NotFound(
            f"Attempted to create a reservation for product model {command.product_model_id}, "
            "which does not exist.",
            {"product_model_id": str(command.product_model_id)},
        )

    reference = _next_reference(session, command.period.start)
    logger.info(
        "reservation.create_started",
        extra={
            "reference": reference,
            "branch_code": branch.code,
            "product_model_sku": product_model.sku,
            "period": command.period.as_postgres_daterange(),
            "quantity": command.quantity,
        },
    )

    reservation = Reservation(
        reference=reference,
        customer_user_id=command.customer_user_id,
        branch_id=command.branch_id,
        status=ReservationStatus.HELD,
        start_date=command.period.start,
        end_date=command.period.end,
        created_by_user_id=command.created_by_user_id,
    )
    session.add(reservation)
    session.flush()

    line = ReservationLine(
        reservation_id=reservation.id,
        product_model_id=command.product_model_id,
        quantity=command.quantity,
        line_position=FIRST_LINE_POSITION,
        daily_rate_snapshot=Decimal(product_model.daily_rate),
        deposit_snapshot=Decimal(product_model.deposit_amount),
    )
    session.add(line)
    session.flush()

    allocated = allocate_assets(
        session,
        AllocationCommand(
            reservation_line_id=line.id,
            product_model_id=command.product_model_id,
            branch_id=command.branch_id,
            period=command.period,
            quantity=command.quantity,
        ),
    )

    result = ReservationResult(
        reservation_id=reservation.id,
        reference=reservation.reference,
        reservation_line_id=line.id,
        status=ReservationStatus.HELD,
        allocated=allocated,
    )
    session.commit()
    logger.info(
        "reservation.create_committed",
        extra={
            "reference": result.reference,
            "reservation_id": str(result.reservation_id),
            "allocated_count": len(result.allocated),
        },
    )
    return result


def _validate_period_window(period: BookingPeriod, current_day: date) -> None:
    """Reject a hire that starts in the past or beyond the booking horizon."""
    if period.start < current_day:
        raise ValidationFailure(
            f"Attempted to book a hire starting {period.start.isoformat()}, which is before "
            f"today, {current_day.isoformat()}. A hire may not start in the past (BR-04).",
            {"start_date": period.start.isoformat(), "today": current_day.isoformat()},
        )
    days_ahead = (period.start - current_day).days
    if days_ahead > MAXIMUM_DAYS_AHEAD:
        raise ValidationFailure(
            f"Attempted to book a hire starting {period.start.isoformat()}, which is "
            f"{days_ahead} days ahead. The booking horizon is {MAXIMUM_DAYS_AHEAD} days (BR-05).",
            {"days_ahead": days_ahead, "maximum_days_ahead": MAXIMUM_DAYS_AHEAD},
        )


def _next_reference(session: Session, start_day: date) -> str:
    """Return the next reservation reference, for example TSH-R-26-000124."""
    next_value = session.execute(text(f"SELECT nextval('{REFERENCE_SEQUENCE}')")).scalar_one()
    year_suffix = f"{start_day.year % 100:02d}"
    return f"{REFERENCE_PREFIX}-{year_suffix}-{int(next_value):06d}"
