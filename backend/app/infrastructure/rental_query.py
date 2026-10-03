"""The read of rentals, with their items and their charges, as read models.

One rental is three statements however many units the hire has. One finds the
rental with its reservation, its branch and its customer. One finds every item
with its unit, its model, the late fee copied onto its reservation line and
whether a damage report names it. One finds every charge. A page of rentals is
the same three statements for every rental on the page at once, with a count
before them, so nothing loops over the database. The list itself is in
`app.infrastructure.rental_list_query`.

The items come in line order and then tag order, which is the order the
counter's checkout sheet lists them in. The charges come in the order they
were raised. Two raised in the same instant, which the hire charge and the
deposit hold of a checkout always are, are ordered by their settlement
reference, which numbers them, and then by key, so the order is the same on
every call.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Final
from uuid import UUID

from sqlalchemy import ColumnElement, Label, UnaryExpression
from sqlalchemy import select as select_columns
from sqlalchemy.orm import Mapped
from sqlmodel import Session, col, select

from app.application.hire.read_models import (
    ChargeDetail,
    RentalDetail,
    RentalItemDetail,
    RentalKey,
)
from app.domain.quarantine import was_flagged
from app.infrastructure.booking_mapping import in_utc, required_utc
from app.infrastructure.models import (
    Asset,
    AssetAllocation,
    Branch,
    Charge,
    CustomerProfile,
    DamageReport,
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
DAMAGE_REPORTED_LABEL: Final[str] = "damage_reported"

# One rental found, with the reservation, the branch and the customer it is read with.
type RentalRow = tuple[Rental, Reservation, Branch, CustomerProfile]


def rental_key_condition(key: RentalKey) -> ColumnElement[bool]:
    """Return the condition that picks one rental by its key or its reference."""
    if key.rental_id is not None:
        return col(Rental.id) == key.rental_id
    return col(Rental.reference) == key.reference


def damage_reported() -> Label[bool]:
    """Return the column that says whether a damage report names the rental item of the row.

    It is a correlated EXISTS, answered through `ix_damage_report_rental_item`
    of revision 0005, so it adds no statement to a read.
    """
    return (
        select_columns(col(DamageReport.id))
        .where(col(DamageReport.rental_item_id) == col(RentalItem.id))
        .correlate(RentalItem)
        .exists()
        .label(DAMAGE_REPORTED_LABEL)
    )


def charge_order() -> tuple[Mapped[datetime], UnaryExpression[str | None], Mapped[UUID]]:
    """Return the order charges are read in, which is the order they were raised."""
    return (
        col(Charge.raised_at),
        col(Charge.payment_reference).nulls_last(),
        col(Charge.id),
    )


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
        (detail,) = self.details_of([found])
        return detail

    def details_of(self, rows: Sequence[RentalRow]) -> list[RentalDetail]:
        """Return the rentals found as read models, reading all their items and charges at once."""
        if not rows:
            return []
        rental_ids = [rental.id for rental, _reservation, _branch, _customer in rows]
        items = self._items_by_rental(rental_ids)
        charges = self._charges_by_rental(rental_ids)
        return [
            _detail_of(row, tuple(items[row[0].id]), tuple(charges[row[0].id])) for row in rows
        ]

    def _items_by_rental(self, rental_ids: list[UUID]) -> dict[UUID, list[RentalItemDetail]]:
        """Return the items of every rental named, with their units and models, in one statement."""
        line_of_allocation = col(ReservationLine.id) == col(AssetAllocation.reservation_line_id)
        rows = self._session.execute(
            select_columns(RentalItem, Asset, ProductModel, ReservationLine, damage_reported())
            .join(AssetAllocation, col(AssetAllocation.id) == col(RentalItem.asset_allocation_id))
            .join(ReservationLine, line_of_allocation)
            .join(ProductModel, col(ProductModel.id) == col(ReservationLine.product_model_id))
            .join(Asset, col(Asset.id) == col(RentalItem.asset_id))
            .where(col(RentalItem.rental_id).in_(rental_ids))
            .order_by(
                col(RentalItem.rental_id),
                col(ReservationLine.line_position),
                col(Asset.asset_tag),
            )
        ).all()
        grouped: dict[UUID, list[RentalItemDetail]] = defaultdict(list)
        for item, asset, model, line, reported in rows:
            grouped[item.rental_id].append(
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
                    flagged_for_damage=was_flagged(item.notes),
                    damage_reported=bool(reported),
                    replacement_value=Decimal(line.replacement_value_snapshot),
                )
            )
        return grouped

    def _charges_by_rental(self, rental_ids: list[UUID]) -> dict[UUID, list[ChargeDetail]]:
        """Return the charges of every rental named, in the order they were raised."""
        rows = self._session.exec(
            select(Charge)
            .where(col(Charge.rental_id).in_(rental_ids))
            .order_by(col(Charge.rental_id), *charge_order())
        ).all()
        grouped: dict[UUID, list[ChargeDetail]] = defaultdict(list)
        for charge in rows:
            grouped[charge.rental_id].append(
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
            )
        return grouped


def _detail_of(
    row: RentalRow, items: tuple[RentalItemDetail, ...], charges: tuple[ChargeDetail, ...]
) -> RentalDetail:
    """Return one rental as a read model, from its row and what was read with it."""
    rental, reservation, branch, customer = row
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
        items=items,
        charges=charges,
        deposit_held=Decimal(rental.deposit_held),
        deposit_withheld=Decimal(rental.deposit_withheld),
        deposit_refunded=Decimal(rental.deposit_refunded),
        balance_due=Decimal(rental.balance_due),
        settled_at=in_utc(rental.settled_at),
        agreement_signed=rental.agreement_signed,
    )
