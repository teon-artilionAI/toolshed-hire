"""The smallest world in which an allocation means anything.

An allocation cannot exist on its own. It needs a branch to be at, a product
model to realise, a physical asset to be, a customer to belong to, a reservation
to hang from and a line inside that reservation. Six rows, in that order, every
time, in a dozen tests. Built here once so that a test about overlapping dates
is about overlapping dates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.domain.enums import UserRole
from app.domain.period import BookingPeriod
from app.infrastructure.models import (
    Asset,
    Branch,
    ProductModel,
    Reservation,
    ReservationLine,
    UserAccount,
)
from tests.support.factories import Factory

logger = logging.getLogger(__name__)

SINGLE_ASSET = 1


@dataclass(frozen=True, slots=True)
class AllocationScenario:
    """One branch, one product model and enough assets to fight over."""

    branch: Branch
    product_model: ProductModel
    assets: list[Asset]
    customer: UserAccount
    reservation: Reservation
    line: ReservationLine

    @property
    def asset(self) -> Asset:
        """Return the single asset, for the many scenarios that have exactly one.

        Raises:
            ValueError: If the scenario holds more than one asset, because then
                "the asset" does not name anything and the test must say which.

        """
        if len(self.assets) != SINGLE_ASSET:
            raise ValueError(
                "Attempted to read the single asset of a scenario holding "
                f"{len(self.assets)} assets. Use `assets` and name the one you mean."
            )
        return self.assets[0]


def build_allocation_scenario(
    factory: Factory, period: BookingPeriod, *, asset_count: int = SINGLE_ASSET
) -> AllocationScenario:
    """Create a branch, a catalogue entry, its units, a customer and a booking line.

    Args:
        factory: The factory bound to the session under test.
        period: The period the reservation covers.
        asset_count: How many interchangeable units the branch holds.

    Returns:
        The whole scenario, with nothing committed. The test owns the commit,
        which matters because a concurrency test has to commit before its
        threads can see any of it.

    """
    branch = factory.branch()
    model = factory.product_model()
    assets = [factory.asset(product_model=model, branch=branch) for _ in range(asset_count)]
    customer = factory.user(role=UserRole.CUSTOMER)
    reservation = factory.reservation(customer=customer, branch=branch, period=period)
    line = factory.reservation_line(reservation=reservation, product_model=model)
    logger.debug(
        "test.allocation_scenario_built",
        extra={
            "branch_code": branch.code,
            "product_model_sku": model.sku,
            "asset_count": len(assets),
            "period": period.as_postgres_daterange(),
        },
    )
    return AllocationScenario(
        branch=branch,
        product_model=model,
        assets=assets,
        customer=customer,
        reservation=reservation,
        line=line,
    )


__all__ = ["AllocationScenario", "build_allocation_scenario"]
