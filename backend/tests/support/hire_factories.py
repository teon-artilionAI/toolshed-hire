"""Factories for the rows of a booking that has gone further than a hold.

`tests/support/factories.py` builds the rows the first flows wrote. The
counter's dashboard and diary read reservations that are confirmed, collected
or missed and the rentals opened from them, so a test of those reads needs
such rows without driving every one of them through the routes. They are built
here, each with the shape the database requires, and a test names only what it
cares about.

Like the other factories these flush and never commit, so the test owns the
transaction.
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Final

from app.domain.enums import (
    AssetStatus,
    ConditionGrade,
    ReleaseReason,
    RentalStatus,
    ReservationStatus,
)
from app.domain.period import BookingPeriod
from app.infrastructure.models import (
    Asset,
    AssetAllocation,
    Branch,
    CustomerProfile,
    ProductModel,
    Rental,
    RentalItem,
    Reservation,
    UserAccount,
)
from tests.support.factories import Factory

logger = logging.getLogger(__name__)

DEPOSIT_PER_UNIT: Final[Decimal] = Decimal("600.00")
DEFAULT_HIRE_DAYS: Final[int] = 3
# When a factory hire went out. A read of the overview never looks at it.
CHECKED_OUT_AT: Final[datetime] = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
RETURNED_AT: Final[datetime] = datetime(2026, 1, 8, 8, 0, tzinfo=UTC)
# The released states a reservation's allocations end in, by its status.
_RELEASED_AS: Final[dict[ReservationStatus, ReleaseReason]] = {
    ReservationStatus.NO_SHOW: ReleaseReason.NO_SHOW,
    ReservationStatus.RETURNED: ReleaseReason.RETURNED,
    ReservationStatus.CANCELLED: ReleaseReason.CANCELLED,
}

_numbers: Final[itertools.count[int]] = itertools.count(1)


@dataclass(frozen=True, slots=True)
class Booked:
    """A reservation built by the factory, with the units it holds or held."""

    reservation: Reservation
    allocations: list[AssetAllocation]
    units: list[Asset]


@dataclass(frozen=True, slots=True)
class HireFactory:
    """Builds reservations in any status and the rentals opened from them."""

    factory: Factory

    def booking(
        self,
        *,
        profile: CustomerProfile,
        created_by: UserAccount,
        branch: Branch,
        model: ProductModel,
        units: list[Asset],
        period: BookingPeriod,
        status: ReservationStatus = ReservationStatus.CONFIRMED,
    ) -> Booked:
        """Create a reservation of one line, holding the units given, in the status given.

        A reservation that has ended has let its units go, with the reason its
        ending gives. Any other holds them.
        """
        session = self.factory.session
        reservation = self.factory.reservation(
            profile=profile, created_by=created_by, branch=branch, period=period
        )
        reservation.status = status
        session.add(reservation)
        line = self.factory.reservation_line(
            reservation=reservation, product_model=model, quantity=max(len(units), 1)
        )
        reason = _RELEASED_AS.get(status)
        allocations = [
            self.factory.allocation(
                line=line,
                asset=unit,
                period=period,
                released_at=CHECKED_OUT_AT if reason is not None else None,
                release_reason=reason,
            )
            for unit in units
        ]
        session.add_all(allocations)
        session.flush()
        return Booked(reservation=reservation, allocations=allocations, units=units)

    def rental(
        self,
        booked: Booked,
        *,
        checked_out_by: UserAccount,
        units_back: int = 0,
        status: RentalStatus = RentalStatus.OPEN,
    ) -> Rental:
        """Create the rental of a collected booking, with an item for each unit it holds.

        The first `units_back` units have come back. A unit still out is
        ON_HIRE, and the rental is marked returned once none is out.
        """
        session = self.factory.session
        reservation = booked.reservation
        all_back = units_back >= len(booked.units)
        rental = Rental(
            reference=f"TSH-H-26-{next(_numbers):06d}",
            reservation_id=reservation.id,
            branch_id=reservation.branch_id,
            status=status,
            checked_out_at=CHECKED_OUT_AT,
            checked_out_by_user_id=checked_out_by.id,
            due_back_on=reservation.end_date,
            deposit_held=DEPOSIT_PER_UNIT * len(booked.units),
            returned_at=RETURNED_AT if all_back else None,
            agreement_signed=True,
        )
        session.add(rental)
        session.flush()
        for position, (allocation, unit) in enumerate(
            zip(booked.allocations, booked.units, strict=True)
        ):
            back = position < units_back
            session.add(
                RentalItem(
                    rental_id=rental.id,
                    asset_allocation_id=allocation.id,
                    asset_id=unit.id,
                    condition_out=ConditionGrade.A,
                    checked_out_at=CHECKED_OUT_AT,
                    returned_at=RETURNED_AT if back else None,
                )
            )
            unit.status = AssetStatus.AVAILABLE if back else AssetStatus.ON_HIRE
            session.add(unit)
        session.flush()
        logger.debug(
            "test.rental_built",
            extra={"reference": rental.reference, "units": len(booked.units)},
        )
        return rental


def hire_from(first_day: date, days: int = DEFAULT_HIRE_DAYS) -> BookingPeriod:
    """Return a hire that starts on a day and lasts a number of days."""
    return BookingPeriod(first_day, first_day + timedelta(days=days))


__all__ = ["Booked", "HireFactory", "hire_from"]
