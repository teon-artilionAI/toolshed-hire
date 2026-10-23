"""The SQL read behind a customer's statement (FR-28, US-27).

Two statements, however many hires or charges the period holds. The first
finds the hires of one customer whose activity touches the period, with the
branch each went out from. The second reads every charge on those hires in
one query. Nothing is summed in the database, because the statement must show
the ledger's own rows and the totals are a sum of what was read.

A hire belongs to the period when it went out in it, came back in it, or had
a charge raised in it. That is three narrow conditions over the indexes on
`rental.checked_out_at`, `rental.returned_at` and `charge.raised_at`, and the
customer condition is applied in the same statement, so another customer's
hire is never read (BR-42).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Final
from uuid import UUID

from sqlalchemy import ColumnElement, and_, or_
from sqlmodel import Session, col, select

from app.application.hire.read_models import ChargeDetail
from app.application.hire.statement import StatementLine
from app.infrastructure.booking_mapping import in_utc, required_utc
from app.infrastructure.models import Branch, Charge, Rental, Reservation
from app.infrastructure.query_log import logged_query
from app.infrastructure.rental_query import (
    CHECKED_OUT_AT_COLUMN,
    RAISED_AT_COLUMN,
    charge_order,
)

logger = logging.getLogger(__name__)

# How many statement reads one log line describes.
STATEMENT_READ: Final[str] = "hire.statement"


class SqlStatementReads:
    """Reads the hires and charges of one customer's statement."""

    def __init__(self, session: Session) -> None:
        """Bind the read to the session of its unit of work."""
        self._session = session

    def for_customer(
        self, customer_profile_id: UUID, starts_on: date, ends_on: date
    ) -> tuple[StatementLine, ...]:
        """Return the hires of one customer that belong to the period, oldest first."""
        starts_at = _utc_start(starts_on)
        ends_at = _utc_start(ends_on)
        with logged_query(
            logger,
            STATEMENT_READ,
            {
                "customer_profile_id": str(customer_profile_id),
                "from": starts_on.isoformat(),
                "to": ends_on.isoformat(),
            },
        ) as outcome:
            rows = self._session.exec(
                select(Rental, Reservation, Branch)
                .join(Reservation, col(Reservation.id) == col(Rental.reservation_id))
                .join(Branch, col(Branch.id) == col(Rental.branch_id))
                .where(
                    col(Reservation.customer_profile_id) == customer_profile_id,
                    _activity(starts_at, ends_at),
                )
                .order_by(col(Rental.checked_out_at), col(Rental.id))
            ).all()
            outcome.row_count = len(rows)
        if not rows:
            return ()
        charges = self._charges_for([rental.id for rental, _reservation, _branch in rows])
        return tuple(
            _line_of(rental, reservation, branch, charges[rental.id])
            for rental, reservation, branch in rows
        )

    def _charges_for(self, rental_ids: list[UUID]) -> dict[UUID, tuple[ChargeDetail, ...]]:
        """Return the charges of every hire named, in the order they were raised."""
        found: dict[UUID, list[ChargeDetail]] = defaultdict(list)
        rows = self._session.exec(
            select(Charge)
            .where(col(Charge.rental_id).in_(rental_ids))
            .order_by(col(Charge.rental_id), *charge_order())
        ).all()
        for charge in rows:
            found[charge.rental_id].append(
                ChargeDetail(
                    id=charge.id,
                    charge_type=charge.charge_type,
                    description=charge.description,
                    amount_ex_vat=Decimal(charge.amount_ex_vat),
                    vat_rate=Decimal(charge.vat_rate),
                    vat_amount=Decimal(charge.vat_amount),
                    amount_inc_vat=Decimal(charge.amount_inc_vat),
                    status=charge.status,
                    raised_at=required_utc(charge.raised_at, RAISED_AT_COLUMN),
                    rental_item_id=charge.rental_item_id,
                    reverses_charge_id=charge.reverses_charge_id,
                    reason=charge.waiver_reason,
                )
            )
        return {rental_id: tuple(items) for rental_id, items in found.items()}


def _activity(starts_at: datetime, ends_at: datetime) -> ColumnElement[bool]:
    """Return the condition that says a hire touches the statement period."""
    charged = (
        select(col(Charge.id))
        .where(
            col(Charge.rental_id) == col(Rental.id),
            col(Charge.raised_at) >= starts_at,
            col(Charge.raised_at) < ends_at,
        )
        .exists()
    )
    return or_(
        and_(col(Rental.checked_out_at) >= starts_at, col(Rental.checked_out_at) < ends_at),
        and_(
            col(Rental.returned_at).is_not(None),
            col(Rental.returned_at) >= starts_at,
            col(Rental.returned_at) < ends_at,
        ),
        charged,
    )


def _line_of(
    rental: Rental,
    reservation: Reservation,
    branch: Branch,
    charges: tuple[ChargeDetail, ...],
) -> StatementLine:
    """Return one hire as a statement line."""
    return StatementLine(
        rental_id=rental.id,
        reference=rental.reference,
        branch_code=branch.code,
        branch_name=branch.name,
        status=rental.status,
        starts_on=reservation.start_date,
        due_back_on=rental.due_back_on,
        checked_out_at=required_utc(rental.checked_out_at, CHECKED_OUT_AT_COLUMN),
        returned_at=in_utc(rental.returned_at),
        deposit_held=Decimal(rental.deposit_held),
        deposit_withheld=Decimal(rental.deposit_withheld),
        deposit_refunded=Decimal(rental.deposit_refunded),
        balance_due=Decimal(rental.balance_due),
        charges=charges,
    )


def _utc_start(day: date) -> datetime:
    """Return the first instant of a business day, as the database stores instants."""
    return datetime.combine(day, time.min, tzinfo=UTC)


__all__ = ["SqlStatementReads"]
