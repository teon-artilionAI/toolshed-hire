"""The allocation use case.

This is the piece the whole design turns on, so the reasoning is written down
rather than implied.

Candidates are selected with `SELECT ... FOR UPDATE SKIP LOCKED`, ordered by
asset tag so the choice is deterministic and reproducible in a test. SKIP
LOCKED is what makes two simultaneous bookings pick two different units instead
of queueing on the same one, which is throughput, not correctness.

Correctness comes from the database. The exclusion constraint on
`asset_allocations` is the final defence and the only authority on whether a
unit is free. The pre check exists to produce a friendly message, not to prevent
the conflict, because between any pre check and any insert another transaction
can commit.

A violation is recognised by SQLSTATE `23P01` and the constraint name reported
by the driver in its diagnostics. The error message is never parsed. A message
is a human artefact that changes with a PostgreSQL release or a locale, and
building a control decision on one is how a 409 silently becomes a 500.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col

from app.domain.enums import AllocationStatus, AssetStatus
from app.domain.errors import AssetUnavailableConflict, ValidationFailure
from app.domain.period import BookingPeriod
from app.infrastructure.models import Asset, AssetAllocation
from app.infrastructure.schema_ddl import OVERLAP_CONSTRAINT_NAME

logger = logging.getLogger(__name__)

# PostgreSQL exclusion_violation. The one code that means "the constraint that
# stops double booking rejected this row".
EXCLUSION_VIOLATION_SQLSTATE: Final[str] = "23P01"
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
    """One unit that was successfully held."""

    allocation_id: UUID
    asset_id: UUID
    asset_tag: str


def allocate_assets(session: Session, command: AllocationCommand) -> list[AllocatedAsset]:
    """Hold specific assets for a reservation line, inside the caller's transaction.

    The caller owns the transaction boundary. Nothing is committed here, so a
    partial allocation can never be committed by accident (BR-09).

    Args:
        session: An open session already inside a transaction.
        command: What to allocate, for whom and when.

    Returns:
        One AllocatedAsset per unit held, in asset tag order.

    Raises:
        ValidationFailure: If the quantity is outside the permitted range.
        AssetUnavailableConflict: If too few free units exist, or if the
            exclusion constraint rejected the insert because another
            transaction took the unit first.
        IntegrityError: Re raised unchanged for any violation that is not the
            overlap constraint, because misreporting a foreign key fault as a
            booking conflict would hide a real defect.

    """
    _validate_quantity(command.quantity)
    logger.info(
        "allocation.started",
        extra={
            "reservation_line_id": str(command.reservation_line_id),
            "product_model_id": str(command.product_model_id),
            "branch_id": str(command.branch_id),
            "period": command.period.as_postgres_daterange(),
            "quantity": command.quantity,
        },
    )

    candidates = _lock_candidate_assets(session, command)
    if len(candidates) < command.quantity:
        logger.warning(
            "allocation.insufficient_candidates",
            extra={
                "product_model_id": str(command.product_model_id),
                "branch_id": str(command.branch_id),
                "period": command.period.as_postgres_daterange(),
                "requested_quantity": command.quantity,
                "available_quantity": len(candidates),
            },
        )
        raise AssetUnavailableConflict(
            "Attempted to allocate "
            f"{command.quantity} unit(s) of product model {command.product_model_id} at branch "
            f"{command.branch_id} for {command.period.as_postgres_daterange()}, but only "
            f"{len(candidates)} free unit(s) were available.",
            product_model_id=command.product_model_id,
            branch_id=command.branch_id,
            period=command.period.as_postgres_daterange(),
            requested_quantity=command.quantity,
            available_quantity=len(candidates),
        )

    allocations = [
        AssetAllocation(
            reservation_line_id=command.reservation_line_id,
            asset_id=asset.id,
            branch_id=asset.branch_id,
            start_date=command.period.start,
            end_date=command.period.end,
            status=AllocationStatus.ACTIVE,
            allocated_at=datetime.now(UTC),
            released_at=None,
        )
        for asset in candidates
    ]
    session.add_all(allocations)

    try:
        session.flush()
    except IntegrityError as exc:
        _raise_conflict_or_reraise(session, exc, command)

    held = [
        AllocatedAsset(
            allocation_id=allocation.id,
            asset_id=asset.id,
            asset_tag=asset.asset_tag,
        )
        for allocation, asset in zip(allocations, candidates, strict=True)
    ]
    logger.info(
        "allocation.completed",
        extra={
            "reservation_line_id": str(command.reservation_line_id),
            "period": command.period.as_postgres_daterange(),
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


def _lock_candidate_assets(session: Session, command: AllocationCommand) -> list[Asset]:
    """Lock up to `quantity` free assets, skipping rows another transaction holds.

    The candidate must be at the requested branch, realise the requested
    product model, be `AVAILABLE`, and hold no active allocation overlapping
    the requested period. The overlap test is written with the same half open
    comparison the exclusion constraint uses, so the pre check and the
    constraint agree about what a conflict is.
    """
    # Every column reference goes through sqlmodel.col. A SQLModel field is
    # annotated with its Python type, so `AssetAllocation.start_date < x` reads
    # to a type checker as a comparison between two dates that produces a bool,
    # not as a SQL expression. col() is the accessor that returns the mapped
    # column, which is what SQLAlchemy is given either way at run time. Without
    # it the whole statement degrades to Select[Any] and the type checker stops
    # inspecting the query that decides which physical unit gets held.
    overlapping_allocation = (
        select(col(AssetAllocation.id))
        .where(
            col(AssetAllocation.asset_id) == col(Asset.id),
            col(AssetAllocation.released_at).is_(None),
            col(AssetAllocation.start_date) < command.period.end,
            col(AssetAllocation.end_date) > command.period.start,
        )
        .correlate(Asset)
    )
    statement = (
        select(Asset)
        .where(
            col(Asset.product_model_id) == command.product_model_id,
            col(Asset.branch_id) == command.branch_id,
            col(Asset.status) == AssetStatus.AVAILABLE,
            ~exists(overlapping_allocation),
        )
        .order_by(col(Asset.asset_tag))
        .limit(command.quantity)
        .with_for_update(skip_locked=True, of=Asset)
    )
    logger.debug(
        "allocation.candidate_query_started",
        extra={
            "product_model_id": str(command.product_model_id),
            "branch_id": str(command.branch_id),
            "limit": command.quantity,
            "lock": "FOR UPDATE SKIP LOCKED",
        },
    )
    candidates = list(session.execute(statement).scalars().all())
    logger.debug(
        "allocation.candidate_query_finished",
        extra={"locked_count": len(candidates), "requested_quantity": command.quantity},
    )
    return candidates


def _raise_conflict_or_reraise(
    session: Session, exc: IntegrityError, command: AllocationCommand
) -> None:
    """Translate an exclusion violation into a domain conflict, or re raise.

    Raises:
        AssetUnavailableConflict: When SQLSTATE is 23P01, which is the overlap
            constraint rejecting the insert.
        IntegrityError: Unchanged, for every other integrity fault.

    """
    sqlstate = _sqlstate_of(exc)
    constraint_name = _constraint_name_of(exc)
    session.rollback()

    if sqlstate != EXCLUSION_VIOLATION_SQLSTATE:
        logger.error(
            "allocation.unexpected_integrity_error",
            extra={
                "sqlstate": sqlstate,
                "constraint": constraint_name,
                "reservation_line_id": str(command.reservation_line_id),
                "attempted": "insert asset_allocations rows",
            },
        )
        raise exc

    logger.warning(
        "allocation.overlap_rejected_by_database",
        extra={
            "sqlstate": sqlstate,
            "constraint": constraint_name,
            "product_model_id": str(command.product_model_id),
            "branch_id": str(command.branch_id),
            "period": command.period.as_postgres_daterange(),
            "requested_quantity": command.quantity,
        },
    )
    raise AssetUnavailableConflict(
        "The database refused the allocation because another booking took the unit first. "
        f"Attempted to hold {command.quantity} unit(s) of product model "
        f"{command.product_model_id} at branch {command.branch_id} for "
        f"{command.period.as_postgres_daterange()}.",
        product_model_id=command.product_model_id,
        branch_id=command.branch_id,
        period=command.period.as_postgres_daterange(),
        requested_quantity=command.quantity,
        constraint_name=constraint_name or OVERLAP_CONSTRAINT_NAME,
    ) from exc


def _sqlstate_of(exc: IntegrityError) -> str | None:
    """Return the five character SQLSTATE the driver reported, if any.

    psycopg 3 exposes `sqlstate`. The `pgcode` fallback covers psycopg 2, so a
    driver swap does not quietly turn every conflict into a 500.
    """
    original = exc.orig
    state = getattr(original, "sqlstate", None)
    if state is None:
        state = getattr(original, "pgcode", None)
    return str(state) if state is not None else None


def _constraint_name_of(exc: IntegrityError) -> str | None:
    """Return the constraint name from the driver diagnostics, if any."""
    diagnostics = getattr(exc.orig, "diag", None)
    name = getattr(diagnostics, "constraint_name", None) if diagnostics is not None else None
    return str(name) if name else None
