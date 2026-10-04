"""The SQL repository of the asset register, the units the administrator writes (FR-23, BR-34).

It maps the `asset` rows to the domain's `RegisteredUnit` and back, on the
session of the unit of work that created it. A unit about to change is read
with `SELECT ... FOR UPDATE`, so two administrators moving one unit take turns,
and a booking that wants it at the same moment skips it, because
`lock_allocatable` takes the same row lock with `SKIP LOCKED`, and finds it out
of the shelf once the move commits.

Every statement stands on a key or an index. A unit is found by its tag
through the unique index on the tag. The booking that holds a unit is found
through the GiST index of the exclusion constraint, which holds the active
allocations only and leads with the unit, and joined to its booking by keys.
An open damage report of a unit is found through `ix_damage_report_asset` of
revision 0005.

A change of status is not written here. It goes through `save_units` of the
asset repository, where checkout, a return, a loss and a damage report write
theirs. A tag that another unit carries is refused by the unique constraint
`asset_asset_tag_key`, recognised by `app/infrastructure/catalogue_uniques.py`.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Final
from uuid import UUID

from sqlalchemy import exists
from sqlalchemy import select as select_columns
from sqlmodel import Session, col, select

from app.domain import asset_register as unit_fields
from app.domain.asset_register import RegisteredUnit
from app.domain.catalogue import Asset as Unit
from app.domain.damage import OPEN_REPORT_STATUSES
from app.infrastructure.catalogue_uniques import flushed
from app.infrastructure.models import (
    Asset,
    AssetAllocation,
    DamageReport,
    Reservation,
    ReservationLine,
)
from app.infrastructure.schema_ddl import ASSET_TAG_CONSTRAINT_NAME

logger = logging.getLogger(__name__)

TAG_UNIQUES: Final[dict[str, str]] = {ASSET_TAG_CONSTRAINT_NAME: unit_fields.ASSET_TAG}
_LINE_OF_ALLOCATION: Final = col(AssetAllocation.reservation_line_id)


class SqlAssetRegisterRepository:
    """Reads and writes the units of the register through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to the session of its unit of work."""
        self._session = session

    def tag_taken(self, asset_tag: str) -> bool:
        """Return True when a unit already carries this tag."""
        taken = self._session.execute(
            select_columns(exists().where(col(Asset.asset_tag) == asset_tag))
        ).scalar_one()
        logger.debug("asset.tag_checked", extra={"asset_tag": asset_tag, "taken": bool(taken)})
        return bool(taken)

    def add(self, unit: RegisteredUnit, now: datetime) -> None:
        """Write a new unit inside the current transaction.

        Raises:
            DuplicateCatalogueValue: If the unique constraint on the tag refused it.

        """
        asset = unit.unit
        row = Asset(
            id=asset.id,
            asset_tag=asset.asset_tag,
            product_model_id=asset.product_model_id,
            branch_id=asset.branch_id,
            serial_number=unit.serial_number,
            status=asset.status,
            condition_grade=asset.condition_grade,
            acquired_on=unit.acquired_on,
            acquisition_cost=unit.acquisition_cost,
            hour_meter_reading=asset.hour_meter_reading,
            notes=unit.notes,
            retired_on=asset.retired_on,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        flushed(self._session, TAG_UNIQUES, "insert an asset row")
        logger.info(
            "asset.unit_added", extra={"asset_id": str(asset.id), "asset_tag": asset.asset_tag}
        )

    def find_for_update(self, asset_tag: str) -> RegisteredUnit | None:
        """Return the unit with this tag, locked until the transaction ends, or None."""
        statement = (
            select(Asset)
            .where(col(Asset.asset_tag) == asset_tag)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        row = self._session.exec(statement).first()
        logger.debug(
            "asset.unit_locked", extra={"asset_tag": asset_tag, "found": row is not None}
        )
        return _registered_of(row) if row is not None else None

    def save_details(self, unit: RegisteredUnit, now: datetime) -> None:
        """Write the paperwork of a unit this transaction locked, stamped as changed now.

        The tag, the model, the branch and the status are never written here.

        Raises:
            RuntimeError: If the unit has no row, which would mean a use case
                is saving a unit it never read.

        """
        asset = unit.unit
        row = self._session.get(Asset, asset.id)
        if row is None:
            raise RuntimeError(
                f"Attempted to save unit {asset.asset_tag}, which has no row. Read it with "
                "find_for_update first."
            )
        row.serial_number = unit.serial_number
        row.condition_grade = asset.condition_grade
        row.hour_meter_reading = asset.hour_meter_reading
        row.notes = unit.notes
        row.updated_at = now
        self._session.add(row)
        self._session.flush()
        logger.info("asset.unit_details_saved", extra={"asset_tag": asset.asset_tag})

    def holding_reservation(self, asset_id: UUID) -> str | None:
        """Return the reference of a booking that holds the unit now, the earliest hire first."""
        statement = (
            select_columns(col(Reservation.reference))
            .select_from(AssetAllocation)
            .join(ReservationLine, col(ReservationLine.id) == _LINE_OF_ALLOCATION)
            .join(Reservation, col(Reservation.id) == col(ReservationLine.reservation_id))
            .where(
                col(AssetAllocation.asset_id) == asset_id,
                col(AssetAllocation.released_at).is_(None),
            )
            .order_by(col(AssetAllocation.start_date))
            .limit(1)
        )
        reference = self._session.execute(statement).scalar_one_or_none()
        logger.debug(
            "asset.holding_reservation_checked",
            extra={"asset_id": str(asset_id), "held": reference is not None},
        )
        return str(reference) if reference is not None else None

    def open_damage_report(self, asset_id: UUID) -> str | None:
        """Return the reference of a damage report of the unit still open, the oldest first."""
        statement = (
            select_columns(col(DamageReport.reference))
            .where(
                col(DamageReport.asset_id) == asset_id,
                col(DamageReport.status).in_(OPEN_REPORT_STATUSES),
            )
            .order_by(col(DamageReport.reported_at))
            .limit(1)
        )
        reference = self._session.execute(statement).scalar_one_or_none()
        logger.debug(
            "asset.open_report_checked",
            extra={"asset_id": str(asset_id), "open": reference is not None},
        )
        return str(reference) if reference is not None else None


def _registered_of(row: Asset) -> RegisteredUnit:
    """Return the unit as the register holds it, for an `asset` row.

    Decimal() on the cost. The driver already returns Decimal for a NUMERIC
    column, and wrapping keeps that true whatever it returns, because money is
    never a float (BR-22).
    """
    return RegisteredUnit(
        unit=Unit(
            id=row.id,
            asset_tag=row.asset_tag,
            product_model_id=row.product_model_id,
            branch_id=row.branch_id,
            status=row.status,
            condition_grade=row.condition_grade,
            hour_meter_reading=row.hour_meter_reading,
            retired_on=row.retired_on,
        ),
        serial_number=row.serial_number,
        acquired_on=row.acquired_on,
        acquisition_cost=Decimal(row.acquisition_cost),
        notes=row.notes,
    )
