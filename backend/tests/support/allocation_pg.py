"""Units, rival bookings and a stale free list for the tests of a force release and a reallocation.

The force release and the reallocation are proved on PostgreSQL against the
real exclusion constraint, so the tests need a few things no route does. The
units of a world as the domain sees them, a second booking of the same model
for the same days whose line can take a unit, an allocation for that line
written in a transaction of its own, a unit taken out of service, and a unit of
work whose locking query offers a unit another booking already holds, which is
what a reallocation sees when it read the free units a moment before another
booking committed one of them.

Every helper commits what it writes on a connection of its own, except
`rival_line`, which commits through the session it is handed.

Importing this module opens no connection.
"""

from __future__ import annotations

from typing import Self
from uuid import UUID

from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.domain import catalogue
from app.domain.enums import AssetStatus
from app.domain.period import BookingPeriod
from app.infrastructure.availability import SqlAssetRepository
from app.infrastructure.models import Asset, AssetAllocation
from app.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from tests.support.booking_api import BookingWorld
from tests.support.checkout_api import TODAY_HIRE
from tests.support.checkout_pg import held_allocations
from tests.support.clock import DEFAULT_INSTANT
from tests.support.factories import Factory


def domain_units(engine: Engine, world: BookingWorld) -> dict[UUID, catalogue.Asset]:
    """Return the units of a world as the domain sees them, available, by their key."""
    keys = [asset.id for asset in world.assets]
    with Session(engine) as reader:
        rows = reader.exec(select(Asset).where(col(Asset.id).in_(keys))).all()
        return {
            row.id: catalogue.Asset(
                id=row.id,
                asset_tag=row.asset_tag,
                product_model_id=row.product_model_id,
                branch_id=row.branch_id,
                status=AssetStatus.AVAILABLE,
                condition_grade=row.condition_grade,
            )
            for row in rows
        }


def rival_line(session: Session, factory: Factory, world: BookingWorld) -> UUID:
    """Commit another booking of the world's model for today and return the key of its line."""
    rival = factory.reservation(
        profile=world.profile, created_by=world.customer, branch=world.branch, period=TODAY_HIRE
    )
    line = factory.reservation_line(reservation=rival, product_model=world.product_model)
    session.commit()
    return line.id


def the_held_allocation(engine: Engine, reservation_id: UUID) -> AssetAllocation:
    """Return the one allocation a booking of one unit holds."""
    (allocation,) = held_allocations(engine, reservation_id)
    return allocation


def take_for_the_rival(
    engine: Engine, line_id: UUID, unit: catalogue.Asset, period: BookingPeriod
) -> AssetAllocation:
    """Write an allocation of a unit for the rival line in a transaction of its own, and commit."""
    allocation = AssetAllocation(
        reservation_line_id=line_id,
        asset_id=unit.id,
        branch_id=unit.branch_id,
        start_date=period.start,
        end_date=period.end,
        allocated_at=DEFAULT_INSTANT,
    )
    with Session(engine) as writer:
        writer.add(allocation)
        writer.commit()
        writer.refresh(allocation)
    return allocation


def take_out_of_service(engine: Engine, unit_id: UUID) -> None:
    """Move a unit to QUARANTINED and commit, so the locking query no longer offers it."""
    with Session(engine) as writer:
        unit = writer.get(Asset, unit_id)
        assert unit is not None
        unit.status = AssetStatus.QUARANTINED
        writer.add(unit)
        writer.commit()


def stale_free_list(stale: list[catalogue.Asset]) -> type[SqlAlchemyUnitOfWork]:
    """Return a unit of work whose locking query claims the units given are free.

    The insert is the real one, so the exclusion constraint is what refuses a
    unit another booking holds.
    """

    class StaleRepository(SqlAssetRepository):
        """The real asset repository, with a free list that is out of date."""

        def lock_allocatable(
            self, product_model_id: UUID, branch_id: UUID, period: BookingPeriod, wanted: int
        ) -> list[catalogue.Asset]:
            """Return the stale answer in place of the locking query."""
            return stale[:wanted]

    class UnitOfWorkWithAStaleFreeList(SqlAlchemyUnitOfWork):
        """The real unit of work, with the stale asset repository."""

        def __enter__(self) -> Self:
            """Open the real transaction, then replace the asset repository."""
            entered = super().__enter__()
            self.assets = StaleRepository(self._open_session())
            return entered

    return UnitOfWorkWithAStaleFreeList


def database_error_behind(error: BaseException) -> IntegrityError:
    """Return the database error at the bottom of a chain of causes.

    Raises:
        AssertionError: If no error in the chain came from the database.

    """
    cause: BaseException | None = error
    while cause is not None:
        if isinstance(cause, IntegrityError):
            return cause
        cause = cause.__cause__
    raise AssertionError(f"No database error is behind {error!r}.")


__all__ = [
    "database_error_behind",
    "domain_units",
    "rival_line",
    "stale_free_list",
    "take_for_the_rival",
    "take_out_of_service",
    "the_held_allocation",
]
