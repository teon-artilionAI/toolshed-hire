"""The asset port, which is how allocation reaches the fleet, and the availability port.

`lock_allocatable` is the one method in the system that takes row locks on
candidate units. Every flow that allocates goes through it, so there is one
copy of the locking and no second copy to drift away from it.

`AvailabilityQuery` is the read side. It answers where a model is free for a
period without locking anything and without holding anything, so a search can
never get in the way of a booking. The answer it gives is advice. The
exclusion constraint still has the last word when somebody books.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from app.application.availability.read_models import (
    AvailabilityPage,
    AvailabilitySearch,
    BranchAvailability,
)
from app.domain.availability import AssetAllocation
from app.domain.catalogue import Asset
from app.domain.period import BookingPeriod


class AvailabilityQuery(Protocol):
    """Where the fleet is free, as far as a visitor may know.

    A unit is free for a period when its status is `AVAILABLE` and it holds no
    active allocation whose half open period overlaps the one asked about
    (BR-10). Every answer is a boolean for a branch. No tag and no count ever
    leaves an implementation of this port.
    """

    def search(self, search: AvailabilitySearch) -> AvailabilityPage:
        """Answer for every model on one page and every active branch.

        The whole page is answered by one statement, however many models and
        branches it holds.
        """
        ...

    def for_model(
        self, model_slug: str, period: BookingPeriod, quantity: int
    ) -> list[BranchAvailability]:
        """Answer for one published model at every active branch.

        A branch is available when at least `quantity` of its units of the
        model are free for the whole period.
        """
        ...


class AssetRepository(Protocol):
    """The fleet, as far as holding units for a hire is concerned."""

    def lock_allocatable(
        self, product_model_id: UUID, branch_id: UUID, period: BookingPeriod, wanted: int
    ) -> list[Asset]:
        """Lock and return up to `wanted` free units, in asset tag order.

        A unit qualifies when it is at the branch, realises the product model,
        is `AVAILABLE` and holds no active allocation overlapping the period.
        A row another transaction has locked is skipped, not waited for. The
        locks last until the unit of work commits or rolls back.
        """
        ...

    def save_allocations(self, allocations: Sequence[AssetAllocation]) -> None:
        """Write the allocations inside the current transaction.

        Raises:
            AllocationConflictError: If the exclusion constraint refused a row
                because another transaction took the unit first.

        """
        ...

    def lock_units(self, asset_ids: Sequence[UUID]) -> list[Asset]:
        """Lock and return particular units, in asset tag order, to change their status.

        A unit another transaction is changing is waited for, not skipped,
        because these are the units of one booking and no other will do.
        """
        ...

    def save_units(self, assets: Sequence[Asset]) -> None:
        """Write the status, the condition and the meter reading of units locked earlier."""
        ...
