"""The SQL read of one month's charges (B13.3).

One statement for the branch, when a branch was named, and one for the
charges. The charge statement joins the hire, its booking, the customer and
the branch, so every row carries the names the bookkeeper reconciles against.
It is ordered by the moment the charge was raised and then by its key, so the
same month produces the same file every time.

The application role may read all of these tables. Nothing here writes.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Final
from uuid import UUID

from sqlmodel import Session, col, select

from app.application.reporting.monthly_charges import (
    MonthlyChargeLine,
    MonthlyCharges,
)
from app.domain.errors import ValidationFailure
from app.infrastructure.booking_mapping import in_utc, required_utc
from app.infrastructure.models import (
    Branch,
    Charge,
    CustomerProfile,
    Rental,
    Reservation,
)
from app.infrastructure.query_log import logged_query

logger = logging.getLogger(__name__)

RAISED_AT_COLUMN: Final[str] = "charge.raised_at"
SETTLED_AT_COLUMN: Final[str] = "charge.settled_at"


class SqlMonthlyCharges:
    """Reads one month of charges through the request session."""

    def __init__(self, session: Session) -> None:
        """Bind the read to the request scoped session."""
        self._session = session

    def read(self, month_start: date, month_end: date, branch_code: str | None) -> MonthlyCharges:
        """Return the charges of the month, optionally at one branch."""
        branch_id = self._branch_id(branch_code)
        statement = (
            select(
                Charge,
                col(Rental.reference),
                col(Branch.code),
                col(CustomerProfile.display_name),
            )
            .join(Rental, col(Rental.id) == col(Charge.rental_id))
            .join(Reservation, col(Reservation.id) == col(Rental.reservation_id))
            .join(CustomerProfile, col(CustomerProfile.id) == col(Reservation.customer_profile_id))
            .join(Branch, col(Branch.id) == col(Rental.branch_id))
            .where(
                col(Charge.raised_at) >= _start_of(month_start),
                col(Charge.raised_at) < _start_of(month_end),
            )
            .order_by(col(Charge.raised_at), col(Charge.id))
        )
        if branch_id is not None:
            statement = statement.where(col(Branch.id) == branch_id)
        with logged_query(
            logger,
            "reporting.monthly_charges_query",
            {
                "month_start": month_start.isoformat(),
                "month_end": month_end.isoformat(),
                "branch_code": branch_code,
            },
        ) as outcome:
            rows = self._session.exec(statement).all()
            outcome.row_count = len(rows)
        return MonthlyCharges(
            month_start=month_start,
            month_end=month_end,
            branch_code=branch_code,
            lines=tuple(_line_of(row) for row in rows),
        )

    def _branch_id(self, code: str | None) -> UUID | None:
        """Return the key of the trading branch, or None for every branch."""
        if code is None:
            return None
        found = self._session.exec(
            select(col(Branch.id)).where(
                col(Branch.code) == code.strip().upper(), col(Branch.is_active).is_(True)
            )
        ).first()
        if found is None:
            raise ValidationFailure(
                "Choose one of our branches.", {"branchCode": code}
            )
        return found


def _line_of(row: tuple[Charge, str, str, str]) -> MonthlyChargeLine:
    """Return one charge as the line the file writes."""
    charge, rental_reference, branch_code, customer_name = row
    return MonthlyChargeLine(
        charge_id=charge.id,
        raised_at=required_utc(charge.raised_at, RAISED_AT_COLUMN),
        rental_reference=rental_reference,
        customer_name=customer_name,
        branch_code=branch_code,
        charge_type=charge.charge_type,
        description=charge.description,
        amount_ex_vat=Decimal(charge.amount_ex_vat),
        vat_amount=Decimal(charge.vat_amount),
        amount_inc_vat=Decimal(charge.amount_inc_vat),
        status=charge.status,
        settled_at=in_utc(charge.settled_at),
        reverses_charge_id=charge.reverses_charge_id,
        waiver_reason=charge.waiver_reason,
    )


def _start_of(day: date) -> datetime:
    """Return the first instant of a business day, as the database stores instants."""
    return datetime.combine(day, time.min, tzinfo=UTC)

__all__ = ["SqlMonthlyCharges"]
