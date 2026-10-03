"""The read of one rental, with its items and its charges, as a read model.

Three statements however many units the hire has. One finds the rental with
its reservation, its branch and its customer. One finds every item with its
unit, its model and the late fee copied onto its reservation line. One finds
every charge. Nothing loops over the database.

The items come in line order and then tag order, which is the order the
counter's checkout sheet lists them in. The charges come in the order they
were raised. Two raised in the same instant, which the hire charge and the
deposit hold of a checkout always are, are ordered by their settlement
reference, which numbers them, and then by key, so the order is the same on
every call.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Final

from sqlalchemy import ColumnElement
from sqlmodel import Session, col, select

from app.application.hire.read_models import (
    ChargeDetail,
    RentalDetail,
    RentalItemDetail,
    RentalKey,
)
from app.infrastructure.booking_mapping import in_utc, required_utc
from app.infrastructure.models import (
    Asset,
    AssetAllocation,
    Branch,
    Charge,
    CustomerProfile,
    ProductModel,
    Rental,
    RentalItem,
    Reservation,
    ReservationLine,
)
from app.infrastructure.query_log import logged_query

logger = logging.getLogger(__name__)

CHECKED_OUT_AT_COLUMN: Final[str] = "rental.checked_out_at"
RAISED_AT_COLUMN: Final[str] = "charge.raised_at"


def rental_key_condition(key: RentalKey) -> ColumnElement[bool]:
    """Return the condition that picks one rental by its key or its reference."""
    if key.rental_id is not None:
        return col(Rental.id) == key.rental_id
    return col(Rental.reference) == key.reference


class SqlRentalReads:
    """Reads rentals as read models through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the reads to the session of the unit of work."""
        self._session = session

    def find_detail(self, key: RentalKey) -> RentalDetail | None:
        """Return one rental with its items and its charges, or None when there is none."""
        statement = (
            select(Rental, Reservation, Branch, CustomerProfile)
            .join(Reservation, col(Reservation.id) == col(Rental.reservation_id))
            .join(Branch, col(Branch.id) == col(Rental.branch_id))
            .join(CustomerProfile, col(CustomerProfile.id) == col(Reservation.customer_profile_id))
            .where(rental_key_condition(key))
        )
        with logged_query(logger, "hire.rental_lookup", {"rental": str(key)}) as outcome:
            found = self._session.exec(statement).first()
            outcome.row_count = 0 if found is None else 1
        if found is None:
            return None
        rental, reservation, branch, customer = found
        return RentalDetail(
            id=rental.id,
            reference=rental.reference,
            status=rental.status,
            reservation_id=rental.reservation_id,
            reservation_reference=reservation.reference,
            branch_id=branch.id,
            branch_code=branch.code,
            branch_name=branch.name,
            customer_profile_id=customer.id,
            customer_name=customer.display_name,
            customer_phone=customer.contact_phone,
            start_date=reservation.start_date,
            due_back_on=rental.due_back_on,
            checked_out_at=required_utc(rental.checked_out_at, CHECKED_OUT_AT_COLUMN),
            returned_at=in_utc(rental.returned_at),
            items=self._items_of(rental),
            charges=self._charges_of(rental),
            deposit_held=Decimal(rental.deposit_held),
            deposit_withheld=Decimal(rental.deposit_withheld),
            deposit_refunded=Decimal(rental.deposit_refunded),
            balance_due=Decimal(rental.balance_due),
            settled_at=in_utc(rental.settled_at),
            agreement_signed=rental.agreement_signed,
        )

    def _items_of(self, rental: Rental) -> tuple[RentalItemDetail, ...]:
        """Return every item of a rental with its unit and its model, in one statement."""
        line_of_allocation = col(ReservationLine.id) == col(AssetAllocation.reservation_line_id)
        rows = self._session.exec(
            select(RentalItem, Asset, ProductModel, ReservationLine)
            .join(AssetAllocation, col(AssetAllocation.id) == col(RentalItem.asset_allocation_id))
            .join(ReservationLine, line_of_allocation)
            .join(ProductModel, col(ProductModel.id) == col(ReservationLine.product_model_id))
            .join(Asset, col(Asset.id) == col(RentalItem.asset_id))
            .where(col(RentalItem.rental_id) == rental.id)
            .order_by(col(ReservationLine.line_position), col(Asset.asset_tag))
        ).all()
        return tuple(
            RentalItemDetail(
                id=item.id,
                asset_tag=asset.asset_tag,
                model_name=model.name,
                model_slug=model.slug,
                condition_out=item.condition_out,
                condition_in=item.condition_in,
                hour_meter_out=item.hour_meter_out,
                hour_meter_in=item.hour_meter_in,
                accessories_out=item.accessories_out,
                accessories_in=item.accessories_in,
                returned_at=in_utc(item.returned_at),
                days_late=item.days_late,
                late_fee_per_day=Decimal(line.late_fee_per_day_snapshot),
            )
            for item, asset, model, line in rows
        )

    def _charges_of(self, rental: Rental) -> tuple[ChargeDetail, ...]:
        """Return every charge of a rental, in the order they were raised, in one statement."""
        rows = self._session.exec(
            select(Charge)
            .where(col(Charge.rental_id) == rental.id)
            .order_by(
                col(Charge.raised_at),
                col(Charge.payment_reference).nulls_last(),
                col(Charge.id),
            )
        ).all()
        return tuple(
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
            )
            for charge in rows
        )
