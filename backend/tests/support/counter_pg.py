"""A branch with a booking in every state the counter's overview tells apart, built from rows.

`build_counter` commits one branch with two collections due, one due tomorrow,
a hold, a hire due back today with one of its two units back, a hire two days
overdue, a hire that came back yesterday and a unit in quarantine, and another
branch with a collection and a mixer of its own. The business day is Monday the
second of March 2026.

The keys a test reads after a commit are kept as plain values, so reading one
sends no statement to refresh an expired row and the statement counts stay
honest.

Importing this module opens no connection.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final
from uuid import UUID

from sqlmodel import Session

from app.domain.enums import AssetStatus, RentalStatus, ReservationStatus, UserRole
from app.infrastructure.models import (
    Asset,
    Branch,
    CustomerProfile,
    ProductModel,
    UserAccount,
)
from tests.support.factories import Factory
from tests.support.hire_factories import Booked, HireFactory, hire_from

TODAY: Final[date] = date(2026, 3, 2)
ONE_DAY: Final[timedelta] = timedelta(days=1)
HIRE_DAYS: Final[int] = 3
HAMMER: Final[str] = "GBH 2-26 DRE Rotary Hammer"
MIXER: Final[str] = "Concrete Mixer 140L"


@dataclass
class Counter:
    """One branch with a booking in every state the overview tells apart, and another branch."""

    factory: Factory
    hire: HireFactory
    branch: Branch
    elsewhere: Branch
    hammer: ProductModel
    mixer: ProductModel
    customer: CustomerProfile
    staff: UserAccount
    branch_id: UUID
    mixer_id: UUID

    def units(self, count: int, branch: Branch | None = None) -> list[Asset]:
        """Return new hammers at the branch, or at the one named."""
        return [
            self.factory.asset(product_model=self.hammer, branch=branch or self.branch)
            for _ in range(count)
        ]

    def booked(
        self,
        first_day: date,
        status: ReservationStatus = ReservationStatus.CONFIRMED,
        *,
        units: int = 1,
        branch: Branch | None = None,
    ) -> Booked:
        """Return a booking of hammers at the branch, starting on a day, in a status."""
        return self.hire.booking(
            profile=self.customer,
            created_by=self.staff,
            branch=branch or self.branch,
            model=self.hammer,
            units=self.units(units, branch),
            period=hire_from(first_day, HIRE_DAYS),
            status=status,
        )

    def hired(self, due_back_on: date, *, units: int = 1, units_back: int = 0) -> None:
        """Make a hire at the branch that is due back on a day, with some units back."""
        booked = self.booked(
            due_back_on - HIRE_DAYS * ONE_DAY, ReservationStatus.COLLECTED, units=units
        )
        status = RentalStatus.RETURNED if units_back >= units else RentalStatus.OPEN
        self.hire.rental(booked, checked_out_by=self.staff, units_back=units_back, status=status)


def build_counter(session: Session, factory: Factory) -> Counter:
    """Commit the branch of this module, with its bookings, and return it."""
    branch = factory.branch(name="Cape Town CBD")
    mixer = factory.product_model(name=MIXER)
    built = Counter(
        factory=factory,
        hire=HireFactory(factory),
        branch=branch,
        elsewhere=factory.branch(name="Bellville"),
        hammer=factory.product_model(name=HAMMER),
        mixer=mixer,
        customer=factory.customer_profile(branch=branch),
        staff=factory.user(role=UserRole.COUNTER_STAFF, branch=branch),
        branch_id=branch.id,
        mixer_id=mixer.id,
    )
    built.booked(TODAY, units=2)
    built.booked(TODAY - ONE_DAY)
    built.booked(TODAY + ONE_DAY)
    built.booked(TODAY, ReservationStatus.HELD)
    built.booked(TODAY, branch=built.elsewhere)
    built.hired(TODAY, units=2, units_back=1)
    built.hired(TODAY - 2 * ONE_DAY)
    built.hired(TODAY - ONE_DAY, units=1, units_back=1)
    quarantined = built.units(1)[0]
    quarantined.status = AssetStatus.QUARANTINED
    session.add(quarantined)
    factory.asset(product_model=built.mixer, branch=built.elsewhere)
    session.commit()
    return built


__all__ = ["HAMMER", "MIXER", "ONE_DAY", "TODAY", "Counter", "build_counter"]
