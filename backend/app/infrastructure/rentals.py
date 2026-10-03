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

The two reads that return read models are in `app.infrastructure.rental_query`
and `app.infrastructure.checkout_query`.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import text
from sqlmodel import Session, col, select

from app.application.booking.read_models import ReservationKey
from app.application.hire.read_models import CheckoutDetail, RentalDetail, RentalKey
from app.domain import charge as domain_charge
from app.domain import rental as domain
from app.infrastructure.checkout_query import SqlCheckoutReads
from app.infrastructure.models import Charge, Rental, RentalItem
from app.infrastructure.rental_query import SqlRentalReads
from app.infrastructure.schema_ddl import RENTAL_REFERENCE_SEQUENCE

logger = logging.getLogger(__name__)


class SqlRentalRepository:
    """Reads and writes rentals through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to the session of its unit of work."""
        self._session = session
        self._rentals = SqlRentalReads(session)
        self._checkouts = SqlCheckoutReads(session)

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
        self._session.add_all([_charge_row(charge) for charge in rental.charges])
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
    )


def _charge_row(charge: domain_charge.Charge) -> Charge:
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
    )
