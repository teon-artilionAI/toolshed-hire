"""The SQL repository of the hire module, for rentals, their items and their charges.

It maps the rental aggregate to the three tables and writes them parent first,
because an item and a charge each carry a foreign key to the rental, and the
hire charge of a one unit hire carries one to its item as well.

The reference number comes from the PostgreSQL sequence `rental_reference_seq`,
which the baseline migration started after the worked example. Deriving it
from a row count would hand two checkouts at once the same reference.

Two things in the database back the rules of a checkout up. `rental` carries a
unique key on its reservation, so a reservation is collected once, and
`rental_item` carries a unique key on its allocation and a composite foreign
key to the allocation and its unit, so an allocation becomes one item and an
item cannot name a unit its allocation does not hold.

A rental that is going to change is read with `SELECT ... FOR UPDATE` on the
rental row, so two returns of one rental take turns, and the second reads
what the first committed. The lock waits and does not skip, because a rental
is a particular row. The aggregate it is read into, and the writing back of a
change, are in `app.infrastructure.rental_aggregates`.

`lock_due_overdue` is the overdue part of the lazy sweep (BR-52). It reads
through the partial index `ix_rental_open_due_back`, which holds only the
hires with a unit still out, and it takes the rentals that do not already
read OVERDUE, earliest due date first.

The reads that return read models are in `app.infrastructure.rental_query`,
`app.infrastructure.rental_list_query` and `app.infrastructure.checkout_query`.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Final
from uuid import UUID

from sqlalchemy import text
from sqlmodel import Session, col, select

from app.application.booking.read_models import ReservationKey
from app.application.hire.list_models import RentalPage, RentalSearch
from app.application.hire.read_models import CheckoutDetail, RentalDetail, RentalKey
from app.application.ownership import OwnerScope
from app.domain import rental as domain
from app.domain.enums import RentalStatus
from app.infrastructure.checkout_query import SqlCheckoutReads
from app.infrastructure.models import Rental, RentalItem
from app.infrastructure.rental_aggregates import charge_row, rental_aggregates_of, write_rental
from app.infrastructure.rental_list_query import SqlRentalList
from app.infrastructure.rental_query import SqlRentalReads, rental_key_condition
from app.infrastructure.schema_ddl import RENTAL_REFERENCE_SEQUENCE

logger = logging.getLogger(__name__)

# The statuses a rental may be moved to OVERDUE from by the sweep (BR-52).
OVERDUE_FROM: Final[tuple[RentalStatus, ...]] = (
    RentalStatus.OPEN,
    RentalStatus.PARTIALLY_RETURNED,
)


class SqlRentalRepository:
    """Reads and writes rentals through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to the session of its unit of work."""
        self._session = session
        self._rentals = SqlRentalReads(session)
        self._checkouts = SqlCheckoutReads(session)
        self._list = SqlRentalList(session)

    def next_reference(self, year: int) -> str:
        """Return the next rental reference, for example TSH-H-26-000099."""
        next_value = self._session.execute(
            text(f"SELECT nextval('{RENTAL_REFERENCE_SEQUENCE}')")
        ).scalar_one()
        reference = domain.format_rental_reference(year, int(next_value))
        logger.debug("hire.reference_drawn", extra={"reference": reference})
        return reference

    def add(self, rental: domain.Rental) -> None:
        """Write a new rental, its items and its charges inside the current transaction."""
        logger.debug(
            "hire.rental_insert_started",
            extra={
                "reference": rental.reference,
                "item_count": len(rental.items),
                "charge_count": len(rental.charges),
            },
        )
        self._session.add(_rental_row(rental))
        self._session.flush()
        self._session.add_all([_item_row(item) for item in rental.items])
        self._session.flush()
        self._session.add_all([charge_row(charge) for charge in rental.charges])
        self._session.flush()
        logger.debug(
            "hire.rental_insert_finished",
            extra={"reference": rental.reference, "rental_id": str(rental.id)},
        )

    def find_id_for_reservation(self, reservation_id: UUID) -> UUID | None:
        """Return the key of the rental opened from a reservation, or None when there is none."""
        found = self._session.exec(
            select(col(Rental.id)).where(col(Rental.reservation_id) == reservation_id)
        ).first()
        logger.debug(
            "hire.rental_for_reservation_lookup",
            extra={"reservation_id": str(reservation_id), "found": found is not None},
        )
        return found

    def find_detail(self, key: RentalKey) -> RentalDetail | None:
        """Return one rental with its items and its charges, or None when there is none."""
        return self._rentals.find_detail(key)

    def find_checkout(self, key: ReservationKey) -> CheckoutDetail | None:
        """Return what the counter needs to check a reservation out, or None when there is none."""
        return self._checkouts.find(key)

    def find_for_update(self, key: RentalKey) -> domain.Rental | None:
        """Return one rental with its items and its charges, locked for a change."""
        # populate_existing, so a row this session already holds is read again
        # under the lock and not answered from memory.
        statement = (
            select(Rental)
            .where(rental_key_condition(key))
            .with_for_update(of=Rental)
            .execution_options(populate_existing=True)
        )
        row = self._session.exec(statement).first()
        logger.debug(
            "hire.rental_locked", extra={"rental": str(key), "found": row is not None}
        )
        if row is None:
            return None
        return rental_aggregates_of(self._session, [row])[0]

    def save(self, rental: domain.Rental) -> None:
        """Write what a return, a loss or a settlement changed on a rental read for a change."""
        write_rental(self._session, rental)

    def lock_due_overdue(self, today: date, limit: int) -> list[domain.Rental]:
        """Lock and return up to `limit` rentals with a unit out past their due date."""
        statement = (
            select(Rental)
            .where(
                col(Rental.returned_at).is_(None),
                col(Rental.due_back_on) < today,
                col(Rental.status).in_(OVERDUE_FROM),
            )
            .order_by(col(Rental.due_back_on), col(Rental.id))
            .limit(limit)
            .with_for_update(of=Rental)
            .execution_options(populate_existing=True)
        )
        rows = self._session.exec(statement).all()
        logger.debug(
            "hire.due_overdue_locked", extra={"due_count": len(rows), "limit": limit}
        )
        return rental_aggregates_of(self._session, rows)

    def search(self, search: RentalSearch, scope: OwnerScope) -> RentalPage:
        """Return one page of the rentals the scope lets the caller see."""
        return self._list.search(search, scope)


def _rental_row(rental: domain.Rental) -> Rental:
    """Return the table row for a rental."""
    return Rental(
        id=rental.id,
        reference=rental.reference,
        reservation_id=rental.reservation_id,
        branch_id=rental.branch_id,
        status=rental.status,
        checked_out_at=rental.checked_out_at,
        checked_out_by_user_id=rental.checked_out_by_user_id,
        due_back_on=rental.due_back_on,
        returned_at=rental.returned_at,
        returned_to_user_id=rental.returned_to_user_id,
        deposit_held=rental.deposit_held,
        deposit_refunded=rental.deposit_refunded,
        deposit_withheld=rental.deposit_withheld,
        balance_due=rental.balance_due,
        settled_at=rental.settled_at,
        agreement_signed=rental.agreement_signed,
    )


def _item_row(item: domain.RentalItem) -> RentalItem:
    """Return the table row for one rental item."""
    return RentalItem(
        id=item.id,
        rental_id=item.rental_id,
        asset_allocation_id=item.asset_allocation_id,
        asset_id=item.asset_id,
        condition_out=item.condition_out,
        condition_in=item.condition_in,
        hour_meter_out=item.hour_meter_out,
        hour_meter_in=item.hour_meter_in,
        accessories_out=item.accessories_out,
        accessories_in=item.accessories_in,
        checked_out_at=item.checked_out_at,
        returned_at=item.returned_at,
        days_late=item.days_late,
        notes=item.notes,
        flagged_for_damage=item.flagged_for_damage,
    )
