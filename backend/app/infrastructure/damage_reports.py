"""The SQL repository of damage reports, and what a report asks about its unit and its hire.

The reference number comes from the PostgreSQL sequence
`damage_report_reference_seq`, which the baseline migration created and nothing
used until now. Deriving it from a row count would hand two reports filed at
once the same reference.

A report that is going to change is read with `SELECT ... FOR UPDATE` on its
row, so two administrators closing one report take turns, and the second reads
what the first committed. The lock waits and does not skip, because a report is
a particular row.

The questions about a unit each take one statement and stand on an index. A
tag is found through the unique index on the tag. The rental of an item through
the item's key. The last hire of a unit through `ix_rental_item_asset`, the
open reports of a unit through `ix_damage_report_asset` of revision 0005, and
whether a booking still holds it through the exclusion constraint's index on
active allocations.

The reads that return read models are in `app.infrastructure.damage_report_query`.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Final
from uuid import UUID

from sqlalchemy import exists, func, text
from sqlalchemy import select as select_columns
from sqlmodel import Session, col, select

from app.application.hire.damage_models import (
    DamageReportDetail,
    DamageReportKey,
    DamageReportPage,
    DamageReportSearch,
)
from app.domain import damage as domain
from app.domain.damage_filing import UnitLastHire
from app.domain.quarantine import damage_assessment_of, was_flagged
from app.infrastructure.booking_mapping import in_utc, required_utc
from app.infrastructure.damage_report_query import SqlDamageReportReads, report_key_condition
from app.infrastructure.models import Asset, AssetAllocation, DamageReport, Rental, RentalItem
from app.infrastructure.rental_query import damage_reported
from app.infrastructure.schema_ddl import DAMAGE_REPORT_REFERENCE_SEQUENCE

logger = logging.getLogger(__name__)

REPORTED_AT_COLUMN: Final[str] = "damage_report.reported_at"
MOST_RECENT: Final[int] = 1


class SqlDamageReportRepository:
    """Reads and writes damage reports through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to the session of its unit of work."""
        self._session = session
        self._reads = SqlDamageReportReads(session)

    def next_reference(self, year: int) -> str:
        """Return the next report reference, for example TSH-D-26-00031."""
        next_value = self._session.execute(
            text(f"SELECT nextval('{DAMAGE_REPORT_REFERENCE_SEQUENCE}')")
        ).scalar_one()
        reference = domain.format_damage_reference(year, int(next_value))
        logger.debug("damage_report.reference_drawn", extra={"reference": reference})
        return reference

    def add(self, report: domain.DamageReport) -> None:
        """Write a new report inside the current transaction, flushed so a charge can name it."""
        self._session.add(
            DamageReport(
                id=report.id,
                reference=report.reference,
                asset_id=report.asset_id,
                rental_item_id=report.rental_item_id,
                severity=report.severity,
                status=report.status,
                description=report.description,
                repair_estimate=report.repair_estimate,
                actual_repair_cost=report.actual_repair_cost,
                chargeable_to_customer=report.chargeable_to_customer,
                reported_by_user_id=report.reported_by_user_id,
                reported_at=report.reported_at,
                resolved_at=report.resolved_at,
                resolution_notes=report.resolution_notes,
            )
        )
        self._session.flush()
        logger.debug(
            "damage_report.inserted",
            extra={"reference": report.reference, "damage_report_id": str(report.id)},
        )

    def find_for_update(self, key: DamageReportKey) -> domain.DamageReport | None:
        """Return one report, locked for a change, or None when there is none."""
        row = self._session.exec(
            select(DamageReport)
            .where(report_key_condition(key))
            .with_for_update(of=DamageReport)
            .execution_options(populate_existing=True)
        ).first()
        logger.debug(
            "damage_report.locked", extra={"damage_report": str(key), "found": row is not None}
        )
        return None if row is None else _report_of(row)

    def save(self, report: domain.DamageReport) -> None:
        """Write the status, the cost, the notes and the time a report was closed.

        Raises:
            LookupError: If the report was never stored.

        """
        row = self._session.get(DamageReport, report.id)
        if row is None:
            raise LookupError(
                f"Attempted to save damage report {report.reference}, which is not in the "
                "database. A change can only be saved for a report read through this session."
            )
        row.status = report.status
        row.actual_repair_cost = report.actual_repair_cost
        row.resolved_at = report.resolved_at
        row.resolution_notes = report.resolution_notes
        self._session.add(row)
        self._session.flush()
        logger.debug(
            "damage_report.saved",
            extra={"reference": report.reference, "status": report.status.value},
        )

    def unit_id_of_tag(self, asset_tag: str) -> UUID | None:
        """Return the key of the unit with this tag, or None when no unit has it."""
        return self._session.exec(
            select(col(Asset.id)).where(col(Asset.asset_tag) == asset_tag)
        ).first()

    def hire_of_item(self, rental_item_id: UUID) -> UUID | None:
        """Return the key of the rental an item is on, or None when there is no such item."""
        return self._session.exec(
            select(col(RentalItem.rental_id)).where(col(RentalItem.id) == rental_item_id)
        ).first()

    def last_hire_of(self, asset_id: UUID) -> UnitLastHire | None:
        """Return the most recent hire of a unit, or None when it was never hired."""
        found = self._session.execute(
            select_columns(
                col(RentalItem.id),
                col(RentalItem.condition_out),
                col(RentalItem.condition_in),
                col(RentalItem.notes),
                col(Rental.reference),
                damage_reported(),
            )
            .join(Rental, col(Rental.id) == col(RentalItem.rental_id))
            .where(col(RentalItem.asset_id) == asset_id)
            .order_by(col(RentalItem.checked_out_at).desc())
            .limit(MOST_RECENT)
        ).first()
        if found is None:
            return None
        item_id, condition_out, condition_in, notes, rental_reference, reported = found
        return UnitLastHire(
            rental_item_id=item_id,
            rental_reference=rental_reference,
            assessment=damage_assessment_of(
                condition_out=condition_out,
                condition_in=condition_in,
                flagged=was_flagged(notes),
                reported=bool(reported),
            ),
        )

    def other_open_reports(self, asset_id: UUID, report_id: UUID) -> int:
        """Return how many reports of a unit are still open, one report left out."""
        counted = self._session.execute(
            select_columns(func.count())
            .select_from(DamageReport)
            .where(
                col(DamageReport.asset_id) == asset_id,
                col(DamageReport.status).in_(domain.OPEN_REPORT_STATUSES),
                col(DamageReport.id) != report_id,
            )
        ).scalar_one()
        return int(counted)

    def holds_active_allocation(self, asset_id: UUID) -> bool:
        """Return True when a booking still holds the unit (BR-37)."""
        held = self._session.execute(
            select_columns(
                exists().where(
                    col(AssetAllocation.asset_id) == asset_id,
                    col(AssetAllocation.released_at).is_(None),
                )
            )
        ).scalar_one()
        return bool(held)

    def find_detail(self, key: DamageReportKey) -> DamageReportDetail | None:
        """Return one report as staff read it, or None when there is none."""
        return self._reads.find_detail(key)

    def search(self, search: DamageReportSearch) -> DamageReportPage:
        """Return one page of the reports that match, newest first."""
        return self._reads.search(search)


def _report_of(row: DamageReport) -> domain.DamageReport:
    """Return the domain entity for a report row."""
    return domain.DamageReport(
        id=row.id,
        reference=row.reference,
        asset_id=row.asset_id,
        rental_item_id=row.rental_item_id,
        severity=row.severity,
        description=row.description,
        repair_estimate=Decimal(row.repair_estimate),
        chargeable_to_customer=row.chargeable_to_customer,
        reported_by_user_id=row.reported_by_user_id,
        reported_at=required_utc(row.reported_at, REPORTED_AT_COLUMN),
        status=row.status,
        actual_repair_cost=(
            Decimal(row.actual_repair_cost) if row.actual_repair_cost is not None else None
        ),
        resolved_at=in_utc(row.resolved_at),
        resolution_notes=row.resolution_notes,
    )
