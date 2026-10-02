"""Allocation, the piece the whole design turns on.

The reasoning is written down here and not implied.

Candidates are locked through `AssetRepository.lock_allocatable`, which selects
them with `SELECT ... FOR UPDATE SKIP LOCKED`, ordered by asset tag so the
choice is deterministic and reproducible in a test. SKIP LOCKED is what makes
two simultaneous bookings pick two different units instead of queueing on the
same one, which is throughput, not correctness. That repository method is the
only place in the system that issues the statement.

Correctness comes from the database. The exclusion constraint on
`asset_allocation` is the final defence and the only authority on whether a
unit is free. The pre check exists to produce a friendly message, not to prevent
the conflict, because between any pre check and any insert another transaction
can commit. When the constraint does refuse the insert, the repository turns
the violation into `AllocationConflictError` and this module adds what was
being asked for.

Nothing is committed here. The caller owns the unit of work, so a partial
allocation can never be committed by accident (BR-09).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from app.application.availability.ports import AssetRepository
from app.application.clock import Clock
from app.domain.availability import AssetAllocation
from app.domain.errors import AllocationConflictError, ValidationFailure
from app.domain.period import BookingPeriod

logger = logging.getLogger(__name__)

MINIMUM_QUANTITY: Final[int] = 1
MAXIMUM_QUANTITY: Final[int] = 10


@dataclass(frozen=True, slots=True)
class AllocationCommand:
    """A request to hold `quantity` units of one product model for one period."""

    reservation_line_id: UUID
    product_model_id: UUID
    branch_id: UUID
    period: BookingPeriod
    quantity: int


@dataclass(frozen=True, slots=True)
class AllocatedAsset:
    """One unit that was successfully held.

    Attributes:
        allocation: The allocation that holds the unit.
        asset_tag: The tag of the unit, which the allocation itself does not carry.

    """

    allocation: AssetAllocation
    asset_tag: str

    @property
    def allocation_id(self) -> UUID:
        """Return the key of the allocation."""
        return self.allocation.id

    @property
    def asset_id(self) -> UUID:
        """Return the key of the unit that was held."""
        return self.allocation.asset_id


def allocate_assets(
    assets: AssetRepository, clock: Clock, command: AllocationCommand
) -> list[AllocatedAsset]:
    """Hold specific assets for a reservation line, inside the caller's unit of work.

    Args:
        assets: The asset repository of the open unit of work.
        clock: Where the moment of the hold comes from.
        command: What to allocate, for whom and when.

    Returns:
        One AllocatedAsset per unit held, in asset tag order.

    Raises:
        ValidationFailure: If the quantity is outside the permitted range.
        AllocationConflictError: If too few free units exist, or if the
            exclusion constraint rejected the insert because another
            transaction took the unit first.

    """
    _validate_quantity(command.quantity)
    period_text = command.period.as_postgres_daterange()
    logger.info(
        "allocation.started",
        extra={
            "reservation_line_id": str(command.reservation_line_id),
            "product_model_id": str(command.product_model_id),
            "branch_id": str(command.branch_id),
            "period": period_text,
            "quantity": command.quantity,
        },
    )

    candidates = assets.lock_allocatable(
        command.product_model_id, command.branch_id, command.period, command.quantity
    )
    if len(candidates) < command.quantity:
        logger.warning(
            "allocation.insufficient_candidates",
            extra={
                "product_model_id": str(command.product_model_id),
                "branch_id": str(command.branch_id),
                "period": period_text,
                "requested_quantity": command.quantity,
                "available_quantity": len(candidates),
            },
        )
        raise AllocationConflictError(
            "Attempted to allocate "
            f"{command.quantity} unit(s) of product model {command.product_model_id} at branch "
            f"{command.branch_id} for {period_text}, but only "
            f"{len(candidates)} free unit(s) were available.",
            product_model_id=command.product_model_id,
            branch_id=command.branch_id,
            period=period_text,
            requested_quantity=command.quantity,
            available_quantity=len(candidates),
        )

    allocated_at = clock.now()
    allocations = [
        AssetAllocation.hold(
            reservation_line_id=command.reservation_line_id,
            asset=asset,
            period=command.period,
            allocated_at=allocated_at,
        )
        for asset in candidates
    ]
    _save_or_raise_conflict(assets, allocations, command)

    held = [
        AllocatedAsset(allocation=allocation, asset_tag=asset.asset_tag)
        for allocation, asset in zip(allocations, candidates, strict=True)
    ]
    logger.info(
        "allocation.completed",
        extra={
            "reservation_line_id": str(command.reservation_line_id),
            "period": period_text,
            "allocated_count": len(held),
            "asset_tags": [item.asset_tag for item in held],
        },
    )
    return held


def _validate_quantity(quantity: int) -> None:
    """Reject a quantity outside the range a reservation line may carry."""
    if not MINIMUM_QUANTITY <= quantity <= MAXIMUM_QUANTITY:
        raise ValidationFailure(
            f"Attempted to allocate a quantity of {quantity}. A reservation line may hold "
            f"between {MINIMUM_QUANTITY} and {MAXIMUM_QUANTITY} units.",
            {"minimum": MINIMUM_QUANTITY, "maximum": MAXIMUM_QUANTITY, "received": quantity},
        )


def _save_or_raise_conflict(
    assets: AssetRepository, allocations: Sequence[AssetAllocation], command: AllocationCommand
) -> None:
    """Write the allocations, and say what was being asked for if the database refuses.

    The repository knows that the constraint fired and which one. It does not
    know the product model or the quantity that was wanted, and a caller
    deciding whether to try again needs both.

    Raises:
        AllocationConflictError: When the exclusion constraint rejected the
            insert. The repository's own error is kept as the cause.

    """
    period_text = command.period.as_postgres_daterange()
    try:
        assets.save_allocations(allocations)
    except AllocationConflictError as conflict:
        constraint_name = conflict.detail.get("constraint_name")
        logger.warning(
            "allocation.overlap_rejected_by_database",
            extra={
                "constraint": constraint_name,
                "product_model_id": str(command.product_model_id),
                "branch_id": str(command.branch_id),
                "period": period_text,
                "requested_quantity": command.quantity,
            },
        )
        raise AllocationConflictError(
            "The database refused the allocation because another booking took the unit first. "
            f"Attempted to hold {command.quantity} unit(s) of product model "
            f"{command.product_model_id} at branch {command.branch_id} for {period_text}.",
            product_model_id=command.product_model_id,
            branch_id=command.branch_id,
            period=period_text,
            requested_quantity=command.quantity,
            constraint_name=str(constraint_name) if constraint_name else None,
        ) from conflict
