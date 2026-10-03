"""Rentals read as domain aggregates for a change, and written back.

A rental that is going to change is read with its items and its charges, and
each item with the figures its booking line carries for it (BR-20), which are
read through the item's allocation and never stored on the item, and with
whether a damage report names it, which the settlement asks (BR-35). However many
rentals are read at once, that is two statements after the rentals
themselves, one for every item and one for every charge.

Writing a rental back changes three things. The rental row takes the status,
the return and the three figures of the deposit. An item that came back or
was recorded as lost takes what the counter recorded. A charge that is new is
inserted, and a charge the domain settled is moved from PENDING to SETTLED.
Nothing else about a charge is ever written. A charge whose stored status is
no longer PENDING is never touched, and an attempt to change one is refused
here as well as in the domain, so there is no path in the application that
edits a settled charge (BR-24).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal
from typing import Final
from uuid import UUID

from sqlalchemy import select as select_columns
from sqlmodel import Session, col, select

from app.domain import charge as domain_charge
from app.domain import rental as domain
from app.domain.enums import ChargeStatus
from app.domain.errors import StateTransitionError
from app.infrastructure.booking_mapping import in_utc, required_utc
from app.infrastructure.models import (
    AssetAllocation,
    Charge,
    Rental,
    RentalItem,
    ReservationLine,
)
from app.infrastructure.rental_query import charge_order, damage_reported

logger = logging.getLogger(__name__)

CHECKED_OUT_AT_COLUMN: Final[str] = "rental_item.checked_out_at"
RAISED_AT_COLUMN: Final[str] = "charge.raised_at"
SETTLED_CHARGE_RULE: Final[str] = "BR-24"


def rental_aggregates_of(session: Session, rows: Sequence[Rental]) -> list[domain.Rental]:
    """Return the rentals read as aggregates, with their items, their terms and their charges."""
    if not rows:
        return []
    rental_ids = [row.id for row in rows]
    items = _items_by_rental(session, rental_ids)
    charges = _charges_by_rental(session, rental_ids)
    return [
        domain.Rental(
            id=row.id,
            reference=row.reference,
            reservation_id=row.reservation_id,
            branch_id=row.branch_id,
            checked_out_at=required_utc(row.checked_out_at, "rental.checked_out_at"),
            checked_out_by_user_id=row.checked_out_by_user_id,
            due_back_on=row.due_back_on,
            deposit_held=Decimal(row.deposit_held),
            agreement_signed=row.agreement_signed,
            status=row.status,
            items=items[row.id],
            charges=charges[row.id],
            returned_at=in_utc(row.returned_at),
            returned_to_user_id=row.returned_to_user_id,
            deposit_refunded=Decimal(row.deposit_refunded),
            deposit_withheld=Decimal(row.deposit_withheld),
            balance_due=Decimal(row.balance_due),
            settled_at=in_utc(row.settled_at),
        )
        for row in rows
    ]


def write_rental(session: Session, rental: domain.Rental) -> None:
    """Write what a change did to a rental read through this session.

    Raises:
        LookupError: If the rental was never stored.
        StateTransitionError: If a charge whose stored status is no longer
            PENDING would be changed (BR-24).

    """
    row = session.get(Rental, rental.id)
    if row is None:
        raise LookupError(
            f"Attempted to save rental {rental.reference}, which is not in the database. A "
            "change can only be saved for a rental read through this session."
        )
    row.status = rental.status
    row.returned_at = rental.returned_at
    row.returned_to_user_id = rental.returned_to_user_id
    row.deposit_withheld = rental.deposit_withheld
    row.deposit_refunded = rental.deposit_refunded
    row.balance_due = rental.balance_due
    row.settled_at = rental.settled_at
    session.add(row)
    _write_items(session, rental)
    inserted, settled = _write_charges(session, rental)
    session.flush()
    logger.debug(
        "hire.rental_saved",
        extra={
            "reference": rental.reference,
            "status": rental.status.value,
            "charges_inserted": inserted,
            "charges_settled": settled,
        },
    )


def _write_items(session: Session, rental: domain.Rental) -> None:
    """Write what the counter recorded on every item that is no longer out."""
    closed = {item.id: item for item in rental.items if not item.is_out()}
    if not closed:
        return
    rows = session.exec(
        select(RentalItem).where(
            col(RentalItem.rental_id) == rental.id, col(RentalItem.id).in_(list(closed))
        )
    ).all()
    for row in rows:
        item = closed[row.id]
        row.condition_in = item.condition_in
        row.hour_meter_in = item.hour_meter_in
        row.accessories_in = item.accessories_in
        row.returned_at = item.returned_at
        row.days_late = item.days_late
        row.notes = item.notes
        row.flagged_for_damage = item.flagged_for_damage
        session.add(row)


def _write_charges(session: Session, rental: domain.Rental) -> tuple[int, int]:
    """Insert the new charges and settle the pending ones the domain settled.

    Returns:
        How many charges were inserted and how many were settled.

    Raises:
        StateTransitionError: If a stored charge that is no longer pending
            differs from the domain's (BR-24).

    """
    stored = {
        row.id: row
        for row in session.exec(select(Charge).where(col(Charge.rental_id) == rental.id)).all()
    }
    inserted = settled = 0
    for charge in rental.charges:
        row = stored.get(charge.id)
        if row is None:
            session.add(charge_row(charge))
            inserted += 1
        elif row.status is not charge.status:
            _ensure_still_pending(row, rental.reference)
            row.status = charge.status
            row.settled_at = charge.settled_at
            row.payment_reference = charge.payment_reference
            session.add(row)
            settled += 1
    return inserted, settled


def _ensure_still_pending(row: Charge, rental_reference: str) -> None:
    """Refuse to write over a stored charge that is no longer pending (BR-24).

    Raises:
        StateTransitionError: If the stored charge is settled, waived or reversed.

    """
    if row.status is ChargeStatus.PENDING:
        return
    raise StateTransitionError(
        f"Attempted to change {row.status.value} charge {row.id} on rental {rental_reference}. "
        "A charge that is no longer pending is never edited.",
        from_status=row.status.value,
        to_status=ChargeStatus.SETTLED.value,
        rule=SETTLED_CHARGE_RULE,
    )


def charge_row(charge: domain_charge.Charge) -> Charge:
    """Return the table row for one charge."""
    return Charge(
        id=charge.id,
        rental_id=charge.rental_id,
        rental_item_id=charge.rental_item_id,
        charge_type=charge.charge_type,
        description=charge.description,
        amount_ex_vat=charge.amount_ex_vat,
        vat_rate=charge.vat_rate,
        vat_amount=charge.vat_amount,
        amount_inc_vat=charge.amount_inc_vat,
        status=charge.status,
        raised_at=charge.raised_at,
        raised_by_user_id=charge.raised_by_user_id,
        settled_at=charge.settled_at,
        payment_reference=charge.payment_reference,
        damage_report_id=charge.damage_report_id,
    )


def _items_by_rental(
    session: Session, rental_ids: list[UUID]
) -> dict[UUID, list[domain.RentalItem]]:
    """Return the items of every rental named, each with its terms, in one statement."""
    rows = session.execute(
        select_columns(RentalItem, ReservationLine, damage_reported())
        .join(AssetAllocation, col(AssetAllocation.id) == col(RentalItem.asset_allocation_id))
        .join(ReservationLine, col(ReservationLine.id) == col(AssetAllocation.reservation_line_id))
        .where(col(RentalItem.rental_id).in_(rental_ids))
        .order_by(col(RentalItem.rental_id), col(ReservationLine.line_position), col(RentalItem.id))
    ).all()
    grouped: dict[UUID, list[domain.RentalItem]] = defaultdict(list)
    for item, line, reported in rows:
        grouped[item.rental_id].append(
            domain.RentalItem(
                id=item.id,
                rental_id=item.rental_id,
                asset_allocation_id=item.asset_allocation_id,
                asset_id=item.asset_id,
                condition_out=item.condition_out,
                checked_out_at=required_utc(item.checked_out_at, CHECKED_OUT_AT_COLUMN),
                terms=domain.UnitTerms(
                    late_fee_per_day=Decimal(line.late_fee_per_day_snapshot),
                    deposit=Decimal(line.deposit_snapshot),
                    replacement_value=Decimal(line.replacement_value_snapshot),
                ),
                hour_meter_out=item.hour_meter_out,
                accessories_out=item.accessories_out,
                condition_in=item.condition_in,
                hour_meter_in=item.hour_meter_in,
                accessories_in=item.accessories_in,
                returned_at=in_utc(item.returned_at),
                days_late=item.days_late,
                notes=item.notes,
                flagged_for_damage=item.flagged_for_damage,
                damage_reported=bool(reported),
            )
        )
    return grouped


def _charges_by_rental(
    session: Session, rental_ids: list[UUID]
) -> dict[UUID, list[domain_charge.Charge]]:
    """Return the charges of every rental named, in the order they were raised, in one statement."""
    rows = session.exec(
        select(Charge)
        .where(col(Charge.rental_id).in_(rental_ids))
        .order_by(col(Charge.rental_id), *charge_order())
    ).all()
    grouped: dict[UUID, list[domain_charge.Charge]] = defaultdict(list)
    for row in rows:
        grouped[row.rental_id].append(
            domain_charge.Charge(
                id=row.id,
                rental_id=row.rental_id,
                charge_type=row.charge_type,
                description=row.description,
                amount_ex_vat=Decimal(row.amount_ex_vat),
                vat_rate=Decimal(row.vat_rate),
                vat_amount=Decimal(row.vat_amount),
                amount_inc_vat=Decimal(row.amount_inc_vat),
                status=row.status,
                raised_at=required_utc(row.raised_at, RAISED_AT_COLUMN),
                raised_by_user_id=row.raised_by_user_id,
                rental_item_id=row.rental_item_id,
                settled_at=in_utc(row.settled_at),
                payment_reference=row.payment_reference,
                damage_report_id=row.damage_report_id,
            )
        )
    return grouped
