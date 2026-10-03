"""The read of a reservation as the counter is about to check it out.

Two statements however many units the reservation holds. One finds the
reservation with its branch, its customer and the rental opened from it, if
there is one. One finds every unit the reservation holds right now, with its
tag, its model, its last condition and meter reading, and the deposit copied
onto its line. Nothing loops over the database, and nothing is locked, because
a read decides nothing. The checkout locks what it changes.

The units come in line order and then tag order, which is the order the
counter's checkout sheet lists them in.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from sqlmodel import Session, col, select

from app.application.booking.read_models import ReservationKey
from app.application.hire.read_models import CheckoutCustomer, CheckoutDetail, CheckoutUnit
from app.infrastructure.booking_query import key_condition
from app.infrastructure.models import (
    Asset,
    AssetAllocation,
    Branch,
    CustomerProfile,
    ProductModel,
    Rental,
    Reservation,
    ReservationLine,
)
from app.infrastructure.query_log import logged_query

logger = logging.getLogger(__name__)


class SqlCheckoutReads:
    """Reads a reservation for its checkout through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the reads to the session of the unit of work."""
        self._session = session

    def find(self, key: ReservationKey) -> CheckoutDetail | None:
        """Return the reservation as the counter checks it out, or None when there is none."""
        statement = (
            select(Reservation, Branch, CustomerProfile, col(Rental.id))
            .join(Branch, col(Branch.id) == col(Reservation.branch_id))
            .join(CustomerProfile, col(CustomerProfile.id) == col(Reservation.customer_profile_id))
            .outerjoin(Rental, col(Rental.reservation_id) == col(Reservation.id))
            .where(key_condition(key))
        )
        with logged_query(logger, "hire.checkout_lookup", {"reservation": str(key)}) as outcome:
            found = self._session.exec(statement).first()
            outcome.row_count = 0 if found is None else 1
        if found is None:
            return None
        reservation, branch, customer, rental_id = found
        return CheckoutDetail(
            reservation_id=reservation.id,
            reference=reservation.reference,
            status=reservation.status,
            branch_id=branch.id,
            branch_code=branch.code,
            branch_name=branch.name,
            customer=CheckoutCustomer(
                id=customer.id,
                display_name=customer.display_name,
                phone=customer.contact_phone,
                id_document_type=customer.id_document_type,
                id_document_last4=customer.id_document_last4,
                account_status=customer.account_status,
            ),
            start_date=reservation.start_date,
            end_date=reservation.end_date,
            units=self._units_of(reservation),
            hire_total_inc_vat=Decimal(reservation.estimated_total_inc_vat),
            rental_id=rental_id,
        )

    def _units_of(self, reservation: Reservation) -> tuple[CheckoutUnit, ...]:
        """Return every unit the reservation holds right now, in one statement."""
        line_of_allocation = col(ReservationLine.id) == col(AssetAllocation.reservation_line_id)
        rows = self._session.exec(
            select(col(AssetAllocation.id), Asset, ProductModel, ReservationLine)
            .join(ReservationLine, line_of_allocation)
            .join(ProductModel, col(ProductModel.id) == col(ReservationLine.product_model_id))
            .join(Asset, col(Asset.id) == col(AssetAllocation.asset_id))
            .where(
                col(ReservationLine.reservation_id) == reservation.id,
                col(AssetAllocation.released_at).is_(None),
            )
            .order_by(col(ReservationLine.line_position), col(Asset.asset_tag))
        ).all()
        return tuple(
            CheckoutUnit(
                allocation_id=allocation_id,
                asset_tag=asset.asset_tag,
                model_name=model.name,
                model_slug=model.slug,
                condition_grade=asset.condition_grade,
                hour_meter=asset.hour_meter_reading,
                deposit_per_unit=Decimal(line.deposit_snapshot),
            )
            for allocation_id, asset, model, line in rows
        )
