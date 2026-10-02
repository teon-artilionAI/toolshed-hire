"""The allocation, the entity availability is made of.

Availability in Toolshed Hire is never a quantity counter. It is the set of
allocations that hold specific tagged units for specific half open periods. A
unit is free for a period exactly when no active allocation of it overlaps that
period. The exclusion constraint in the database enforces that rule, and
`conflicts_with` states it once more here, so the two can be compared.

This is a plain dataclass. The repository in the infrastructure layer maps it
to the `asset_allocation` table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.domain.catalogue import Asset
from app.domain.enums import ReleaseReason
from app.domain.errors import AllocationConflictError
from app.domain.period import BookingPeriod


@dataclass(slots=True)
class AssetAllocation:
    """The hold of one specific asset for one specific half open period.

    An allocation is active exactly while `released_at` is None. The reason and
    the timestamp of a release arrive together, which the database enforces
    with a check constraint and this class enforces at construction.

    Attributes:
        id: The allocation key, generated here so it is known before the insert.
        reservation_line_id: The line the unit is held for.
        asset_id: The physical unit being held.
        branch_id: The branch that holds the unit.
        period: The half open period the unit is held for.
        allocated_at: When the hold was made.
        released_at: When the hold stopped occupying the unit, if it has.
        release_reason: Why it stopped, set exactly when `released_at` is.

    """

    reservation_line_id: UUID
    asset_id: UUID
    branch_id: UUID
    period: BookingPeriod
    allocated_at: datetime
    released_at: datetime | None = None
    release_reason: ReleaseReason | None = None
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        """Refuse a release that carries a reason without a time, or a time without a reason.

        Raises:
            ValueError: If exactly one of the two release fields is set.

        """
        if (self.released_at is None) != (self.release_reason is None):
            raise ValueError(
                "Attempted to build an allocation with a half recorded release. Got "
                f"released_at={self.released_at!r} and release_reason={self.release_reason!r}. "
                "The two are set together or not at all."
            )

    @classmethod
    def hold(
        cls,
        *,
        reservation_line_id: UUID,
        asset: Asset,
        period: BookingPeriod,
        allocated_at: datetime,
    ) -> AssetAllocation:
        """Build an active allocation of one asset for one line.

        Args:
            reservation_line_id: The line the unit is held for.
            asset: The unit to hold.
            period: The half open period to hold it for.
            allocated_at: The moment of the hold, from the clock.

        Raises:
            AllocationConflictError: If the asset is not in a status that may
                be held, for example a unit under repair.

        """
        if not asset.is_allocatable():
            raise AllocationConflictError(
                f"Attempted to hold asset {asset.asset_tag} for {period.as_postgres_daterange()}, "
                f"but its status is {asset.status.value}. Only an AVAILABLE unit may be held.",
                branch_id=asset.branch_id,
                period=period.as_postgres_daterange(),
                asset_tag=asset.asset_tag,
            )
        return cls(
            reservation_line_id=reservation_line_id,
            asset_id=asset.id,
            branch_id=asset.branch_id,
            period=period,
            allocated_at=allocated_at,
        )

    def is_active(self) -> bool:
        """Return True while the allocation still occupies its asset."""
        return self.released_at is None

    def release(self, reason: ReleaseReason, now: datetime) -> None:
        """Stop the allocation occupying its asset, with the reason and the time together.

        An allocation that is already released is left as it was, so the first
        reason and the first time are the ones that stand.

        Args:
            reason: Why the unit is being let go.
            now: The moment of the release, from the clock.

        """
        if not self.is_active():
            return
        self.released_at = now
        self.release_reason = reason

    def conflicts_with(self, other: AssetAllocation) -> bool:
        """Return True when the two allocations could not both stand.

        This is the rule the exclusion constraint enforces, stated once more in
        the domain. Two active allocations of the same asset conflict when
        their periods overlap, and a released allocation conflicts with
        nothing.
        """
        return (
            self.asset_id == other.asset_id
            and self.is_active()
            and other.is_active()
            and self.period.overlaps(other.period)
        )
