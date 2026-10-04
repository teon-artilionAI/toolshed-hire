"""The two statements behind the force release of one allocation (US-32).

`held_unit` finds an allocation by its primary key, with the reservation whose
line holds it and the tag of its unit, in one statement through the primary
keys of the line and the unit. Nothing is locked, because the use case locks
the reservation next and changes the allocation only under that lock.

`write_release` writes the release the domain made on the row the session
already holds, so the reservation read after it sees the allocation released.
It refuses a row that is not stored as active, which can only happen when the
caller did not hold the reservation's lock. The release drops the row out of
the exclusion constraint without deleting it.

`SqlAssetRepository` calls both, so the release goes through the allocation
repository of the system.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlmodel import Session, col

from app.application.availability.ports import HeldUnit
from app.domain import availability
from app.infrastructure.models import Asset, AssetAllocation, ReservationLine

logger = logging.getLogger(__name__)


def held_unit(session: Session, allocation_id: UUID) -> HeldUnit | None:
    """Return an allocation with its reservation and its unit's tag, or None when there is none."""
    found = session.execute(
        select(col(ReservationLine.reservation_id), col(Asset.asset_tag))
        .select_from(AssetAllocation)
        .join(ReservationLine, col(ReservationLine.id) == col(AssetAllocation.reservation_line_id))
        .join(Asset, col(Asset.id) == col(AssetAllocation.asset_id))
        .where(col(AssetAllocation.id) == allocation_id)
    ).first()
    logger.debug(
        "allocation.lookup",
        extra={"allocation_id": str(allocation_id), "found": found is not None},
    )
    if found is None:
        return None
    reservation_id, asset_tag = found
    return HeldUnit(
        allocation_id=allocation_id, reservation_id=reservation_id, asset_tag=asset_tag
    )


def write_release(session: Session, allocation: availability.AssetAllocation) -> None:
    """Write the release of one allocation, which must still be stored as active.

    Raises:
        LookupError: If no active allocation has the key, which means the
            caller did not hold the lock of its reservation.
        ValueError: If the domain handed over an allocation it did not release.

    """
    if allocation.released_at is None or allocation.release_reason is None:
        raise ValueError(
            f"Attempted to write the release of allocation {allocation.id}, which was not "
            "released."
        )
    row = session.get(AssetAllocation, allocation.id)
    if row is None or row.released_at is not None:
        raise LookupError(
            f"Attempted to release allocation {allocation.id}, which is not stored as active."
        )
    row.released_at = allocation.released_at
    row.release_reason = allocation.release_reason
    session.add(row)
    session.flush()
    logger.info(
        "allocation.release_written",
        extra={
            "allocation_id": str(allocation.id),
            "release_reason": allocation.release_reason.value,
        },
    )
