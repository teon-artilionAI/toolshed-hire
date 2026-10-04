"""The asset register as a query object (FR-23, US-31, SC-21).

The administrator sees every unit of the fleet, at every branch and in every
status, retired ones included. It selects columns and returns the read models
of the application layer.

A list is two statements however long its page is, the count and the page,
and three when it is narrowed to a branch, whose code is looked up first. One
unit is one statement and its history four more, in
`app/infrastructure/asset_history_query.py`. Each row carries two correlated
counts that are one probe of an index each, so neither grows with anything
but the page.

1. The page in tag order, unfiltered, and one unit by its tag, through
   `asset_asset_tag_key`, the unique index on the tag.
2. `branchCode`, alone or with `status`, through `ix_asset_branch_status` of
   the baseline.
3. `modelId`, through `ix_asset_product_model` of revision 0004.
4. `q` on the tag through `ix_asset_tag_trgm` of revision 0004, on the serial
   number through `ix_asset_serial_trgm` of revision 0010, and on the model
   name by a read of `product_model` and then `ix_asset_product_model`.
5. The count of the bookings that hold a unit now, through the GiST index of
   `asset_allocation_no_overlap`, which holds the active allocations only.
6. The count of its open damage reports, through `ix_damage_report_asset` of
   revision 0005.

The text is matched three ways joined with UNION, the way the counter's
locator matches it, so each way can use its own index and the count and the
page run the same condition. It travels as a bound value with the two LIKE
wildcards and the backslash taken out, so a search for `%` finds nothing.

`status` alone has no index that leads with it, so the planner walks the tag
index and keeps the units in that status, which is quick for a status many
units hold and reads the fleet for one few hold. That is what degrades first,
and the README says what to do about it.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Final
from uuid import UUID

from sqlalchemy import ColumnElement, RowMapping, Select, func, union
from sqlalchemy import select as select_columns
from sqlmodel import Session, col

from app.application.catalogue.asset_read_models import (
    AdminAssetEntry,
    AdminAssetPage,
    AdminAssetSearch,
    AssetHistoryFacts,
)
from app.domain.damage import OPEN_REPORT_STATUSES
from app.infrastructure.asset_history_query import history_facts
from app.infrastructure.customer_search import ANY_TEXT, LIKE_SPECIALS
from app.infrastructure.models import (
    Asset,
    AssetAllocation,
    Branch,
    Category,
    DamageReport,
    ProductModel,
)
from app.infrastructure.query_log import logged_query

logger = logging.getLogger(__name__)

MATCHING_SUBQUERY_NAME: Final[str] = "matching"
MATCHED_ASSET_ID: Final[str] = "asset_id"
NO_TEXT: Final[int] = 0


class SqlAssetRegister:
    """Answers what the administrator reads of the fleet, through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the query object to the session of the request."""
        self._session = session

    def branch_id_of(self, branch_code: str) -> UUID | None:
        """Return the key of the branch with this code, trading or not, or None."""
        statement = select_columns(col(Branch.id)).where(col(Branch.code) == branch_code)
        with logged_query(
            logger, "asset.register_branch_lookup", {"branch_code": branch_code}
        ) as outcome:
            branch_id = self._session.execute(statement).scalar_one_or_none()
            outcome.row_count = 0 if branch_id is None else 1
        return branch_id

    def page(self, search: AdminAssetSearch) -> AdminAssetPage:
        """Return one page of the units that match, in tag order."""
        filters: dict[str, object] = {
            "q_length": len(search.text) if search.text is not None else NO_TEXT,
            "branch_id": str(search.branch_id) if search.branch_id else None,
            "status": search.status.value if search.status else None,
            "model_id": str(search.model_id) if search.model_id else None,
            "page": search.page,
            "page_size": search.page_size,
        }
        text = search.text.translate(LIKE_SPECIALS).strip() if search.text is not None else None
        if text == "":
            logger.info("asset.register_search_skipped", extra=filters)
            return AdminAssetPage(items=(), page=search.page, page_size=search.page_size, total=0)
        conditions = _conditions(search, text)
        count_statement = select_columns(func.count()).select_from(Asset).where(*conditions)
        page_statement = (
            _unit_statement()
            .where(*conditions)
            .order_by(col(Asset.asset_tag))
            .limit(search.page_size)
            .offset(search.offset)
        )
        with logged_query(logger, "asset.register_page", filters) as outcome:
            total = int(self._session.execute(count_statement).scalar_one())
            rows = self._session.execute(page_statement).mappings().all()
            outcome.row_count = len(rows)
        return AdminAssetPage(
            items=tuple(_entry_of(row) for row in rows),
            page=search.page,
            page_size=search.page_size,
            total=total,
        )

    def unit(self, asset_tag: str) -> AdminAssetEntry | None:
        """Return one unit as the list shows it, or None when no unit carries the tag."""
        statement = _unit_statement().where(col(Asset.asset_tag) == asset_tag)
        with logged_query(logger, "asset.register_unit", {"asset_tag": asset_tag}) as outcome:
            row = self._session.execute(statement).mappings().first()
            outcome.row_count = 0 if row is None else 1
        return _entry_of(row) if row is not None else None

    def history(self, asset_id: UUID, limit: int) -> AssetHistoryFacts:
        """Return the facts of one unit's history, at most `limit` of each kind, newest first."""
        return history_facts(self._session, asset_id, limit)


def _conditions(search: AdminAssetSearch, text: str | None) -> list[ColumnElement[bool]]:
    """Return the WHERE conditions of a search of the register, every value bound."""
    conditions: list[ColumnElement[bool]] = []
    if search.branch_id is not None:
        conditions.append(col(Asset.branch_id) == search.branch_id)
    if search.status is not None:
        conditions.append(col(Asset.status) == search.status)
    if search.model_id is not None:
        conditions.append(col(Asset.product_model_id) == search.model_id)
    if text is not None:
        conditions.append(col(Asset.id).in_(_matching(f"{ANY_TEXT}{text}{ANY_TEXT}")))
    return conditions


def _matching(pattern: str) -> Select[tuple[UUID]]:
    """Return the keys of the units whose tag, serial number or model name holds the text."""
    matched = union(
        select_columns(col(Asset.id).label(MATCHED_ASSET_ID)).where(
            col(Asset.asset_tag).ilike(pattern)
        ),
        select_columns(col(Asset.id).label(MATCHED_ASSET_ID)).where(
            col(Asset.serial_number).ilike(pattern)
        ),
        select_columns(col(Asset.id).label(MATCHED_ASSET_ID))
        .join(ProductModel, col(ProductModel.id) == col(Asset.product_model_id))
        .where(col(ProductModel.name).ilike(pattern)),
    ).subquery(MATCHING_SUBQUERY_NAME)
    return select_columns(matched.c[MATCHED_ASSET_ID])


def _unit_statement() -> Select[tuple[object, ...]]:
    """Return the columns of a unit as the register shows it, with its two counts."""
    active_allocations = (
        select_columns(func.count())
        .select_from(AssetAllocation)
        .where(
            col(AssetAllocation.asset_id) == col(Asset.id),
            col(AssetAllocation.released_at).is_(None),
        )
        .correlate(Asset)
        .scalar_subquery()
    )
    open_reports = (
        select_columns(func.count())
        .select_from(DamageReport)
        .where(
            col(DamageReport.asset_id) == col(Asset.id),
            col(DamageReport.status).in_(OPEN_REPORT_STATUSES),
        )
        .correlate(Asset)
        .scalar_subquery()
    )
    return (
        select_columns(
            col(Asset.id).label("id"),
            col(Asset.asset_tag).label("asset_tag"),
            col(Asset.product_model_id).label("model_id"),
            col(ProductModel.name).label("model_name"),
            col(ProductModel.slug).label("model_slug"),
            col(Category.name).label("category_name"),
            col(Branch.code).label("branch_code"),
            col(Branch.name).label("branch_name"),
            col(Asset.serial_number).label("serial_number"),
            col(Asset.status).label("status"),
            col(Asset.condition_grade).label("condition_grade"),
            col(Asset.acquired_on).label("acquired_on"),
            col(Asset.acquisition_cost).label("acquisition_cost"),
            col(Asset.hour_meter_reading).label("hour_meter_reading"),
            col(Asset.notes).label("notes"),
            col(Asset.retired_on).label("retired_on"),
            active_allocations.label("active_allocation_count"),
            open_reports.label("open_damage_reports"),
        )
        .select_from(Asset)
        .join(ProductModel, col(ProductModel.id) == col(Asset.product_model_id))
        .join(Category, col(Category.id) == col(ProductModel.category_id))
        .join(Branch, col(Branch.id) == col(Asset.branch_id))
    )


def _entry_of(row: RowMapping) -> AdminAssetEntry:
    """Return the read model of one unit row.

    Decimal() on the cost. The driver already returns Decimal for a NUMERIC
    column, and wrapping keeps that true whatever it returns, because money is
    never a float (BR-22).
    """
    return AdminAssetEntry(
        id=row["id"],
        asset_tag=row["asset_tag"],
        model_id=row["model_id"],
        model_name=row["model_name"],
        model_slug=row["model_slug"],
        category_name=row["category_name"],
        branch_code=row["branch_code"],
        branch_name=row["branch_name"],
        serial_number=row["serial_number"],
        status=row["status"],
        condition_grade=row["condition_grade"],
        acquired_on=row["acquired_on"],
        acquisition_cost=Decimal(row["acquisition_cost"]),
        hour_meter_reading=row["hour_meter_reading"],
        notes=row["notes"],
        retired_on=row["retired_on"],
        active_allocation_count=int(row["active_allocation_count"]),
        open_damage_reports=int(row["open_damage_reports"]),
    )
