"""The reads of damage reports, as read models, in a bounded number of statements.

One report is one statement. A page of reports is two, the count and the page,
however long the page is. Each row is the report joined to its unit, the
unit's model and branch and the account that filed it, and, for a report that
names a rental item, to the rental, the allocation and the booking line the
item came from.

Two figures are worked out in the statement. The replacement value is the one
copied onto the booking line of the hire (BR-20), which is the value that
capped the recovery, and the model's own value for a report outside a hire.
The recovery charged is the sum of the charges that point back at the report.
It is found through the rental item, so the subquery stands on the partial
index of the charges of a unit, `ix_charge_rental_item`, and not on a scan of
every charge. A report outside a hire raises no charge, so it reads null.

A list is narrowed by the tag of a unit, through the unique index on the tag
and `ix_damage_report_asset`, by the status of the report and by the branch
that holds the unit, and is newest first. What degrades first as the reports
grow is a list with no tag, which sorts every report that matches to find one
page, the way the list of rentals does. A page keyed on when a report was filed,
with an index behind it, is the durable fix when that day comes.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Final

from sqlalchemy import ColumnElement, RowMapping, Select, func
from sqlalchemy import select as select_columns
from sqlmodel import Session, col

from app.application.hire.damage_models import (
    DamageReportDetail,
    DamageReportKey,
    DamageReportPage,
    DamageReportSearch,
)
from app.infrastructure.booking_mapping import in_utc, required_utc
from app.infrastructure.models import (
    Asset,
    AssetAllocation,
    Branch,
    Charge,
    DamageReport,
    ProductModel,
    Rental,
    RentalItem,
    ReservationLine,
    UserAccount,
)
from app.infrastructure.query_log import logged_query

logger = logging.getLogger(__name__)

REPORTED_AT_COLUMN: Final[str] = "damage_report.reported_at"


def report_key_condition(key: DamageReportKey) -> ColumnElement[bool]:
    """Return the condition that picks one report by its key or its reference."""
    if key.report_id is not None:
        return col(DamageReport.id) == key.report_id
    return col(DamageReport.reference) == key.reference


class SqlDamageReportReads:
    """Reads damage reports as read models through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the reads to the session of the unit of work."""
        self._session = session

    def find_detail(self, key: DamageReportKey) -> DamageReportDetail | None:
        """Return one report as staff read it, or None when there is none."""
        with logged_query(logger, "damage_report.lookup", {"damage_report": str(key)}) as outcome:
            row = (
                self._session.execute(_reports().where(report_key_condition(key)))
                .mappings()
                .first()
            )
            outcome.row_count = 0 if row is None else 1
        return None if row is None else _detail_of(row)

    def search(self, search: DamageReportSearch) -> DamageReportPage:
        """Return one page of the reports that match, newest first."""
        conditions = _conditions_of(search)
        filters: dict[str, object] = {
            "asset_tag": search.asset_tag,
            "status": search.status.value if search.status else None,
            "branch_id": str(search.branch_id) if search.branch_id else None,
            "page": search.page,
            "page_size": search.page_size,
        }
        newest_first = (col(DamageReport.reported_at).desc(), col(DamageReport.reference).desc())
        with logged_query(logger, "damage_report.list", filters) as outcome:
            total = self._session.execute(
                select_columns(func.count())
                .select_from(DamageReport)
                .join(Asset, col(Asset.id) == col(DamageReport.asset_id))
                .where(*conditions)
            ).scalar_one()
            page = (
                _reports()
                .where(*conditions)
                .order_by(*newest_first)
                .offset(search.offset)
                .limit(search.page_size)
            )
            rows = self._session.execute(page).mappings().all()
            outcome.row_count = len(rows)
        return DamageReportPage(
            items=tuple(_detail_of(row) for row in rows),
            page=search.page,
            page_size=search.page_size,
            total=int(total),
        )


def _conditions_of(search: DamageReportSearch) -> list[ColumnElement[bool]]:
    """Return the conditions a report has to meet to be on the list."""
    conditions: list[ColumnElement[bool]] = []
    if search.asset_tag is not None:
        conditions.append(col(Asset.asset_tag) == search.asset_tag)
    if search.status is not None:
        conditions.append(col(DamageReport.status) == search.status)
    if search.branch_id is not None:
        conditions.append(col(Asset.branch_id) == search.branch_id)
    return conditions


def _reports() -> Select[tuple[object, ...]]:
    """Return the statement that reads reports with everything their read model carries."""
    recovery = (
        select_columns(func.sum(col(Charge.amount_inc_vat)))
        .where(
            col(Charge.rental_item_id) == col(DamageReport.rental_item_id),
            col(Charge.damage_report_id) == col(DamageReport.id),
        )
        .correlate(DamageReport)
        .scalar_subquery()
    )
    replacement = func.coalesce(
        col(ReservationLine.replacement_value_snapshot), col(ProductModel.replacement_value)
    )
    return (
        select_columns(
            col(DamageReport.id).label("id"),
            col(DamageReport.reference).label("reference"),
            col(Asset.asset_tag).label("asset_tag"),
            col(ProductModel.name).label("model_name"),
            col(Branch.code).label("branch_code"),
            col(Rental.id).label("rental_id"),
            col(Rental.reference).label("rental_reference"),
            col(DamageReport.rental_item_id).label("rental_item_id"),
            col(DamageReport.severity).label("severity"),
            col(DamageReport.status).label("status"),
            col(DamageReport.description).label("description"),
            col(DamageReport.repair_estimate).label("repair_estimate"),
            col(DamageReport.actual_repair_cost).label("actual_repair_cost"),
            col(DamageReport.chargeable_to_customer).label("chargeable_to_customer"),
            recovery.label("recovery_charged"),
            replacement.label("replacement_value"),
            col(DamageReport.reported_at).label("reported_at"),
            col(UserAccount.full_name).label("reported_by_name"),
            col(DamageReport.resolved_at).label("resolved_at"),
            col(DamageReport.resolution_notes).label("resolution_notes"),
        )
        .select_from(DamageReport)
        .join(Asset, col(Asset.id) == col(DamageReport.asset_id))
        .join(ProductModel, col(ProductModel.id) == col(Asset.product_model_id))
        .join(Branch, col(Branch.id) == col(Asset.branch_id))
        .join(UserAccount, col(UserAccount.id) == col(DamageReport.reported_by_user_id))
        .outerjoin(RentalItem, col(RentalItem.id) == col(DamageReport.rental_item_id))
        .outerjoin(Rental, col(Rental.id) == col(RentalItem.rental_id))
        .outerjoin(AssetAllocation, col(AssetAllocation.id) == col(RentalItem.asset_allocation_id))
        .outerjoin(
            ReservationLine, col(ReservationLine.id) == col(AssetAllocation.reservation_line_id)
        )
    )


def _detail_of(row: RowMapping) -> DamageReportDetail:
    """Return one report as a read model, from a row of the statement."""
    actual = row["actual_repair_cost"]
    recovered = row["recovery_charged"]
    return DamageReportDetail(
        id=row["id"],
        reference=row["reference"],
        asset_tag=row["asset_tag"],
        model_name=row["model_name"],
        branch_code=row["branch_code"],
        rental_id=row["rental_id"],
        rental_reference=row["rental_reference"],
        rental_item_id=row["rental_item_id"],
        severity=row["severity"],
        status=row["status"],
        description=row["description"],
        repair_estimate=_money(row["repair_estimate"]),
        actual_repair_cost=None if actual is None else _money(actual),
        chargeable_to_customer=bool(row["chargeable_to_customer"]),
        recovery_charged=None if recovered is None else _money(recovered),
        replacement_value=_money(row["replacement_value"]),
        reported_at=required_utc(row["reported_at"], REPORTED_AT_COLUMN),
        reported_by_name=row["reported_by_name"],
        resolved_at=in_utc(row["resolved_at"]),
        resolution_notes=row["resolution_notes"],
    )


def _money(value: object) -> Decimal:
    """Return an amount the driver handed back as an exact `Decimal`."""
    return value if isinstance(value, Decimal) else Decimal(str(value))
