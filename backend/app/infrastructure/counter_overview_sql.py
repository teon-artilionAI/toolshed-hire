"""The statements the counter's dashboard and diary are read with, and how their rows are read.

Every statement here is narrowed to one branch and stands on an index.

1. The collections due on the dashboard are the confirmed reservations whose
   hire has started. The status is written as the literal the partial index
   `ix_reservation_confirmed_start` is filtered on, so the planner reads only
   confirmed rows, and a confirmed booking leaves that index as soon as it is
   collected, cancelled or missed.
2. The returns due and the overdue hires are the rentals with a unit still
   out, which are the ones `ix_rental_open_due_back` holds. That index is
   partial on `returned_at IS NULL`, and the statement carries the same
   condition, so a hire that is back costs nothing.
3. The two stock counts read `ix_asset_branch_status`, which the baseline
   built for exactly this.
4. The diary reads the reservations of a run of days through
   `ix_reservation_branch_start` and the rentals through
   `ix_rental_branch_due_back` of revision 0004, because a day in the past
   holds hires that are back and are in no partial index.
5. The lines of the reservations found are read in one statement through the
   unique key on a line's reservation and model, and the units of the rentals
   found in one statement through `ix_rental_item_rental`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Final
from uuid import UUID

from sqlalchemy import ColumnElement, RowMapping, Select, func, literal_column
from sqlalchemy import select as select_columns
from sqlalchemy.orm import Mapped
from sqlmodel import SQLModel, col, select
from sqlmodel.sql.expression import Select as EntitySelect

from app.application.hire.overview_models import (
    BookedLine,
    CollectionEntry,
    DashboardCounts,
    HiredUnit,
    ReturnEntry,
)
from app.domain.enums import AssetStatus, ReservationStatus
from app.infrastructure.booking import CONFIRMED_STATUS_LITERAL
from app.infrastructure.models import (
    Asset,
    AssetAllocation,
    CustomerProfile,
    ProductModel,
    Rental,
    RentalItem,
    Reservation,
    ReservationLine,
)

# One reservation or rental found, with the name and the phone of its customer.
type CollectionRow = tuple[Reservation, str, str]
type RentalRow = tuple[Rental, str, str]
# One line of a reservation, and one unit of a rental, as the overview reads them.
type LineRow = tuple[UUID, int, str]
type UnitRow = tuple[UUID, datetime | None, str, Decimal]

# The statuses a collection in the diary may be in. A draft, a hold, a
# cancellation and a lapse are not bookings anybody comes to collect.
DIARY_STATUSES: Final[tuple[ReservationStatus, ...]] = (
    ReservationStatus.CONFIRMED,
    ReservationStatus.COLLECTED,
    ReservationStatus.RETURNED,
    ReservationStatus.NO_SHOW,
)


def due_for_collection(
    branch_id: UUID | Mapped[UUID], today: date
) -> list[ColumnElement[bool]]:
    """Return the conditions of a confirmed reservation at the branch whose hire has started.

    The branch is a key, or the key column of a `branch` row the conditions
    are correlated with, which is how the admin dashboard counts every branch
    in one statement.
    """
    return [
        col(Reservation.branch_id) == branch_id,
        col(Reservation.status) == literal_column(CONFIRMED_STATUS_LITERAL),
        col(Reservation.start_date) <= today,
    ]


def still_out(branch_id: UUID | Mapped[UUID]) -> list[ColumnElement[bool]]:
    """Return the conditions of a rental at the branch with a unit still out, keyed as above."""
    return [col(Rental.branch_id) == branch_id, col(Rental.returned_at).is_(None)]


def _counted(table: type[SQLModel], *conditions: ColumnElement[bool]) -> ColumnElement[int]:
    """Return a subquery that counts the rows of a table meeting the conditions."""
    return select_columns(func.count()).select_from(table).where(*conditions).scalar_subquery()


def counts_statement(branch_id: UUID, today: date) -> Select[tuple[int, int, int, int, int]]:
    """Return the one statement that counts all five totals of the dashboard."""
    at_branch = col(Asset.branch_id) == branch_id
    return select_columns(
        _counted(Reservation, *due_for_collection(branch_id, today)).label("collections_due"),
        _counted(Rental, *still_out(branch_id), col(Rental.due_back_on) == today).label(
            "returns_due"
        ),
        _counted(Rental, *still_out(branch_id), col(Rental.due_back_on) < today).label("overdue"),
        _counted(Asset, at_branch, col(Asset.status) == AssetStatus.ON_HIRE).label("on_hire"),
        _counted(Asset, at_branch, col(Asset.status) == AssetStatus.QUARANTINED).label(
            "quarantined"
        ),
    )


def counts_of(row: RowMapping) -> DashboardCounts:
    """Return the five totals from the row of `counts_statement`, read by their labels."""
    return DashboardCounts(
        collections_due=int(row["collections_due"]),
        returns_due=int(row["returns_due"]),
        overdue=int(row["overdue"]),
        on_hire=int(row["on_hire"]),
        quarantined=int(row["quarantined"]),
    )


def collections_statement(branch_id: UUID) -> EntitySelect[CollectionRow]:
    """Return the statement that finds reservations at a branch, earliest first day first."""
    return (
        select(Reservation, col(CustomerProfile.display_name), col(CustomerProfile.contact_phone))
        .join(CustomerProfile, col(CustomerProfile.id) == col(Reservation.customer_profile_id))
        .where(col(Reservation.branch_id) == branch_id)
        .order_by(col(Reservation.start_date), col(Reservation.reference))
    )


def rentals_statement(branch_id: UUID) -> EntitySelect[RentalRow]:
    """Return the statement that finds rentals at a branch, earliest due date first."""
    return (
        select(Rental, col(CustomerProfile.display_name), col(CustomerProfile.contact_phone))
        .join(Reservation, col(Reservation.id) == col(Rental.reservation_id))
        .join(CustomerProfile, col(CustomerProfile.id) == col(Reservation.customer_profile_id))
        .where(col(Rental.branch_id) == branch_id)
        .order_by(col(Rental.due_back_on), col(Rental.reference))
    )


def lines_statement(reservation_ids: Sequence[UUID]) -> EntitySelect[LineRow]:
    """Return the statement that reads the lines of every reservation found, in position order."""
    return (
        select(
            col(ReservationLine.reservation_id),
            col(ReservationLine.quantity),
            col(ProductModel.name),
        )
        .join(ProductModel, col(ProductModel.id) == col(ReservationLine.product_model_id))
        .where(col(ReservationLine.reservation_id).in_(reservation_ids))
        .order_by(col(ReservationLine.reservation_id), col(ReservationLine.line_position))
    )


def units_statement(rental_ids: Sequence[UUID]) -> EntitySelect[UnitRow]:
    """Return the statement that reads the units of every rental found, in line and tag order."""
    return (
        select(
            col(RentalItem.rental_id),
            col(RentalItem.returned_at),
            col(ProductModel.name),
            col(ReservationLine.late_fee_per_day_snapshot),
        )
        .join(AssetAllocation, col(AssetAllocation.id) == col(RentalItem.asset_allocation_id))
        .join(ReservationLine, col(ReservationLine.id) == col(AssetAllocation.reservation_line_id))
        .join(ProductModel, col(ProductModel.id) == col(ReservationLine.product_model_id))
        .join(Asset, col(Asset.id) == col(RentalItem.asset_id))
        .where(col(RentalItem.rental_id).in_(rental_ids))
        .order_by(
            col(RentalItem.rental_id), col(ReservationLine.line_position), col(Asset.asset_tag)
        )
    )


def lines_by_reservation(rows: Sequence[LineRow]) -> dict[UUID, list[BookedLine]]:
    """Return the lines read, grouped by the reservation they belong to."""
    grouped: dict[UUID, list[BookedLine]] = defaultdict(list)
    for reservation_id, quantity, model_name in rows:
        grouped[reservation_id].append(BookedLine(model_name=model_name, quantity=quantity))
    return grouped


def units_by_rental(rows: Sequence[UnitRow]) -> dict[UUID, list[HiredUnit]]:
    """Return the units read, grouped by the rental they are on."""
    grouped: dict[UUID, list[HiredUnit]] = defaultdict(list)
    for rental_id, returned_at, model_name, late_fee_per_day in rows:
        grouped[rental_id].append(
            HiredUnit(
                model_name=model_name,
                late_fee_per_day=Decimal(late_fee_per_day),
                is_out=returned_at is None,
            )
        )
    return grouped


def collection_entries(
    rows: Sequence[CollectionRow], lines: dict[UUID, list[BookedLine]]
) -> tuple[CollectionEntry, ...]:
    """Return each reservation found as a collection, with its lines."""
    return tuple(
        CollectionEntry(
            reservation_id=reservation.id,
            reference=reservation.reference,
            status=reservation.status,
            customer_name=customer_name,
            customer_phone=customer_phone,
            start_date=reservation.start_date,
            end_date=reservation.end_date,
            lines=tuple(lines.get(reservation.id, ())),
        )
        for reservation, customer_name, customer_phone in rows
    )


def return_entries(
    rows: Sequence[RentalRow], units: dict[UUID, list[HiredUnit]]
) -> tuple[ReturnEntry, ...]:
    """Return each rental found as a return, with its units."""
    return tuple(
        ReturnEntry(
            rental_id=rental.id,
            reference=rental.reference,
            status=rental.status,
            customer_name=customer_name,
            customer_phone=customer_phone,
            due_back_on=rental.due_back_on,
            units=tuple(units.get(rental.id, ())),
        )
        for rental, customer_name, customer_phone in rows
    )
