"""The asset repository of the in memory unit of work.

It knows the allocation rule, because a use case that cannot be refused a unit
cannot be tested for the refusal. A unit is free when it may be held and no
active allocation of it overlaps the period, and an allocation that overlaps
an active one is refused the way the exclusion constraint refuses it. It makes
no attempt at concurrency, which is proved against PostgreSQL.

The force release finds an allocation through the reservations of the working
copy and writes the release onto the allocation the overlap rule reads.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Final
from uuid import UUID

from app.application.availability.ports import HeldUnit
from app.domain.availability import AssetAllocation
from app.domain.catalogue import Asset
from app.domain.errors import AllocationConflictError
from app.domain.period import BookingPeriod

if TYPE_CHECKING:
    from tests.support.memory import MemoryStore, Records

CONSTRAINT_NAME: Final[str] = "asset_allocation_no_overlap"


class MemoryAssets:
    """The asset repository over the working copy."""

    def __init__(self, store: MemoryStore, working: Records) -> None:
        """Bind to the store and to the working copy of one transaction."""
        self._store = store
        self._working = working

    def lock_allocatable(
        self, product_model_id: UUID, branch_id: UUID, period: BookingPeriod, wanted: int
    ) -> list[Asset]:
        """Return up to `wanted` free units in asset tag order."""
        free = [
            asset
            for asset in self._store.assets
            if asset.product_model_id == product_model_id
            and asset.branch_id == branch_id
            and asset.is_allocatable()
            and not self._is_held(asset.id, period)
        ]
        return sorted(free, key=lambda asset: asset.asset_tag)[:wanted]

    def save_allocations(self, allocations: Sequence[AssetAllocation]) -> None:
        """Keep the allocations, refusing one that overlaps an active allocation."""
        for allocation in allocations:
            if any(allocation.conflicts_with(existing) for existing in self._working.allocations):
                raise AllocationConflictError(
                    "The in memory store refused an overlapping allocation.",
                    constraint_name=CONSTRAINT_NAME,
                )
            self._working.allocations.append(allocation)

    def find_allocation(self, allocation_id: UUID) -> HeldUnit | None:
        """Return an allocation of a reservation of the working copy, or None."""
        for reservation in self._working.reservations:
            for line in reservation.lines:
                for allocation in line.allocations:
                    if allocation.id == allocation_id:
                        return HeldUnit(
                            allocation_id=allocation_id,
                            reservation_id=reservation.id,
                            asset_tag=self._store.tag_of(allocation.asset_id),
                        )
        return None

    def release_allocation(self, allocation: AssetAllocation) -> None:
        """Write the release onto the allocation the overlap rule reads.

        Raises:
            LookupError: If the allocation was never saved.

        """
        for stored in self._working.allocations:
            if stored.id == allocation.id:
                stored.released_at = allocation.released_at
                stored.release_reason = allocation.release_reason
                return
        raise LookupError(
            f"Attempted to release allocation {allocation.id}, which was never saved."
        )

    def _is_held(self, asset_id: UUID, period: BookingPeriod) -> bool:
        """Return True when an active allocation of the asset overlaps the period."""
        return any(
            allocation.asset_id == asset_id
            and allocation.is_active()
            and allocation.period.overlaps(period)
            for allocation in self._working.allocations
        )


__all__ = ["CONSTRAINT_NAME", "MemoryAssets"]
