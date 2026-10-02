"""The asset port, which is how allocation reaches the fleet.

`lock_allocatable` is the one method in the system that takes row locks on
candidate units. Every flow that allocates goes through it, so there is one
copy of the locking and no second copy to drift away from it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from app.domain.availability import AssetAllocation
from app.domain.catalogue import Asset
from app.domain.period import BookingPeriod


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
