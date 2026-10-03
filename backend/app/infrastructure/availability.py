"""The SQL asset repository, which is where units are locked and allocations written.

Two things live here and nowhere else in the system.

`lock_allocatable` is the only place that issues `SELECT ... FOR UPDATE SKIP
LOCKED`. Every flow that allocates goes through it, so the locking exists once
and cannot drift between copies.

`translate_integrity_error` is the only place a violation of the exclusion
constraint becomes `AllocationConflictError`. A violation is recognised by
SQLSTATE `23P01` together with the name of the constraint, both read from the
driver's diagnostics. The error message is never parsed. A message is a human
artefact that changes with a PostgreSQL release or a locale, and building a
control decision on one is how a 409 silently becomes a 500. Any other
integrity fault is re-raised unchanged, because reporting a foreign key fault
as a booking conflict would hide a real defect.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Final
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col

from app.domain import availability, catalogue
from app.domain.enums import AssetStatus
from app.domain.errors import AllocationConflictError
from app.domain.period import BookingPeriod
from app.infrastructure.models import Asset, AssetAllocation
from app.infrastructure.schema_ddl import OVERLAP_CONSTRAINT_NAME

logger = logging.getLogger(__name__)

# PostgreSQL exclusion_violation. The code the exclusion constraint that stops
# double booking reports when it rejects a row.
EXCLUSION_VIOLATION_SQLSTATE: Final[str] = "23P01"


class SqlAssetRepository:
    """Locks free units and writes allocations through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to the session of its unit of work."""
        self._session = session

    def lock_allocatable(
        self, product_model_id: UUID, branch_id: UUID, period: BookingPeriod, wanted: int
    ) -> list[catalogue.Asset]:
        """Lock up to `wanted` free assets, skipping rows another transaction holds.

        The candidate must be at the requested branch, realise the requested
        product model, be `AVAILABLE`, and hold no active allocation overlapping
        the requested period. The overlap test is written with the same half
        open comparison the exclusion constraint uses, so the pre check and the
        constraint agree about what a conflict is.

        Returns:
            The locked units in asset tag order. Fewer than `wanted` when
            fewer are free.

        """
        # Every column reference goes through sqlmodel.col. A SQLModel field is
        # annotated with its Python type, so `AssetAllocation.start_date < x`
        # reads to a type checker as a comparison between two dates that
        # produces a bool, not as a SQL expression. col() is the accessor that
        # returns the mapped column, which is what SQLAlchemy is given either
        # way at run time. Without it the whole statement degrades to
        # Select[Any] and the type checker stops inspecting the query that
        # decides which physical unit gets held.
        overlapping_allocation = (
            select(col(AssetAllocation.id))
            .where(
                col(AssetAllocation.asset_id) == col(Asset.id),
                col(AssetAllocation.released_at).is_(None),
                col(AssetAllocation.start_date) < period.end,
                col(AssetAllocation.end_date) > period.start,
            )
            .correlate(Asset)
        )
        statement = (
            select(Asset)
            .where(
                col(Asset.product_model_id) == product_model_id,
                col(Asset.branch_id) == branch_id,
                col(Asset.status) == AssetStatus.AVAILABLE,
                ~exists(overlapping_allocation),
            )
            .order_by(col(Asset.asset_tag))
            .limit(wanted)
            .with_for_update(skip_locked=True, of=Asset)
        )
        logger.debug(
            "allocation.candidate_query_started",
            extra={
                "product_model_id": str(product_model_id),
                "branch_id": str(branch_id),
                "limit": wanted,
                "lock": "FOR UPDATE SKIP LOCKED",
            },
        )
        rows = self._session.execute(statement).scalars().all()
        logger.debug(
            "allocation.candidate_query_finished",
            extra={"locked_count": len(rows), "requested_quantity": wanted},
        )
        return [_asset_of(row) for row in rows]

    def save_allocations(self, allocations: Sequence[availability.AssetAllocation]) -> None:
        """Write the allocations inside the current transaction.

        Raises:
            AllocationConflictError: If the exclusion constraint refused a row
                because another transaction took the unit first.
            IntegrityError: Unchanged, for every other integrity fault.

        """
        self._session.add_all([_allocation_row(allocation) for allocation in allocations])
        logger.debug(
            "allocation.insert_started", extra={"allocation_count": len(allocations)}
        )
        try:
            self._session.flush()
        except IntegrityError as error:
            conflict = self.translate_integrity_error(error)
            if conflict is None:
                logger.error(
                    "allocation.unexpected_integrity_error",
                    extra={
                        "sqlstate": _sqlstate_of(error),
                        "constraint": _constraint_name_of(error),
                        "attempted": "insert asset_allocation rows",
                    },
                )
                raise
            raise conflict from error
        logger.debug(
            "allocation.insert_finished", extra={"allocation_count": len(allocations)}
        )

    def lock_units(self, asset_ids: Sequence[UUID]) -> list[catalogue.Asset]:
        """Lock particular units to change their status, waiting where another transaction has one.

        The rows are locked in asset tag order, so two transactions that lock
        overlapping sets of units always take them in the same order and
        cannot deadlock on each other.
        """
        statement = (
            select(Asset)
            .where(col(Asset.id).in_(list(asset_ids)))
            .order_by(col(Asset.asset_tag))
            .with_for_update(of=Asset)
            .execution_options(populate_existing=True)
        )
        rows = self._session.execute(statement).scalars().all()
        logger.debug(
            "asset.units_locked",
            extra={"requested_count": len(asset_ids), "locked_count": len(rows)},
        )
        return [_asset_of(row) for row in rows]

    def save_units(self, assets: Sequence[catalogue.Asset]) -> None:
        """Write the status, the condition, the meter and the retirement of units locked earlier.

        Raises:
            LookupError: If a unit was never stored, which would mean a use
                case is saving a unit it did not read.

        """
        for asset in assets:
            row = self._session.get(Asset, asset.id)
            if row is None:
                raise LookupError(
                    f"Attempted to save unit {asset.asset_tag}, which is not in the database."
                )
            row.status = asset.status
            row.condition_grade = asset.condition_grade
            row.hour_meter_reading = asset.hour_meter_reading
            row.retired_on = asset.retired_on
            self._session.add(row)
        self._session.flush()
        logger.debug("asset.units_saved", extra={"unit_count": len(assets)})

    def translate_integrity_error(self, error: IntegrityError) -> AllocationConflictError | None:
        """Return the booking conflict an integrity error stands for, if it is one.

        Args:
            error: The integrity error raised by a flush.

        Returns:
            `AllocationConflictError` when the error is SQLSTATE `23P01` raised
            by the overlap constraint, and None for anything else. The caller
            re-raises the original error in that case.

        """
        sqlstate = _sqlstate_of(error)
        constraint_name = _constraint_name_of(error)
        if sqlstate != EXCLUSION_VIOLATION_SQLSTATE or constraint_name != OVERLAP_CONSTRAINT_NAME:
            return None
        logger.debug(
            "allocation.exclusion_violation_translated",
            extra={"sqlstate": sqlstate, "constraint": constraint_name},
        )
        return AllocationConflictError(
            "The database refused an allocation because another booking holds the same unit "
            f"for an overlapping period. The constraint {constraint_name} rejected the insert.",
            constraint_name=constraint_name,
        )


def _asset_of(row: Asset) -> catalogue.Asset:
    """Return the domain entity for an asset row."""
    return catalogue.Asset(
        id=row.id,
        asset_tag=row.asset_tag,
        product_model_id=row.product_model_id,
        branch_id=row.branch_id,
        status=row.status,
        condition_grade=row.condition_grade,
        hour_meter_reading=row.hour_meter_reading,
        retired_on=row.retired_on,
    )


def _allocation_row(allocation: availability.AssetAllocation) -> AssetAllocation:
    """Return the table row for a domain allocation."""
    return AssetAllocation(
        id=allocation.id,
        reservation_line_id=allocation.reservation_line_id,
        asset_id=allocation.asset_id,
        branch_id=allocation.branch_id,
        start_date=allocation.period.start,
        end_date=allocation.period.end,
        allocated_at=allocation.allocated_at,
        released_at=allocation.released_at,
        release_reason=allocation.release_reason,
    )


def _sqlstate_of(error: IntegrityError) -> str | None:
    """Return the five character SQLSTATE the driver reported, if any.

    psycopg 3 exposes `sqlstate`. The `pgcode` fallback covers psycopg 2, so a
    driver swap does not quietly turn every conflict into a 500.
    """
    original = error.orig
    state = getattr(original, "sqlstate", None)
    if state is None:
        state = getattr(original, "pgcode", None)
    return str(state) if state is not None else None


def _constraint_name_of(error: IntegrityError) -> str | None:
    """Return the constraint name from the driver diagnostics, if any."""
    diagnostics = getattr(error.orig, "diag", None)
    name = getattr(diagnostics, "constraint_name", None) if diagnostics is not None else None
    return str(name) if name else None
