"""The administrator's catalogue as a query object (FR-22, BR-44).

The administrator sees every category, switched off or not, and every product
model, published or not, which is what a visitor's catalogue never shows. It
selects columns and returns the read models of the application layer.

A list is two statements however long its page is, the count and the page. A
category carries how many models it classifies and a model how many units the
fleet holds of it, and each is a correlated count that is one probe of an
index for each row of the page, so neither grows with anything but the page.

1. The categories are the count and the page. The page joins each parent by
   its primary key, and each count of models is a probe of
   `ix_product_model_category` of revision 0009.
2. The models of one category are the count and the page, through
   `ix_product_model_category`, and the published ones of one category
   through `ix_product_model_published` of the baseline. Each count of units
   is a probe of `ix_asset_product_model` of revision 0004.
3. One category or one model is one statement, by its primary key.

The list of every model, the list narrowed by publication alone and a text
search read `product_model` from end to end. It is the catalogue the business
keeps by hand, 120 rows today, and a text search is a contains match no btree
can serve, as it is for a visitor. `app/infrastructure/catalogue_sql.py` says
what to build when that stops being cheap.

The order of the categories is worked out in the statement, each top level
category followed by its children, by sort order and then name, so a page cut
from it is a stable slice of the same list. The models are ordered by name
and then SKU, which is unique, so a page boundary never splits two rows.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Final
from uuid import UUID

from sqlalchemy import ColumnElement, RowMapping, Select, false, func, or_, select, true
from sqlalchemy.orm import aliased
from sqlmodel import Session, col

from app.application.catalogue.admin_read_models import (
    AdminCategoryEntry,
    AdminCategoryPage,
    AdminCategorySearch,
    AdminModelEntry,
    AdminModelPage,
    AdminModelSearch,
)
from app.infrastructure.booking_mapping import required_utc
from app.infrastructure.models import Asset, Category, ProductModel
from app.infrastructure.query_log import logged_query

logger = logging.getLogger(__name__)

UPDATED_AT_COLUMN: Final[str] = "product_model.updated_at"
NO_TEXT: Final[int] = 0

_PARENT = aliased(Category)

# The order that puts each top level category before its children. A top level
# category sorts as itself and a child as its parent, so the two land
# together. Within that the parent comes first, and the children follow by
# their own sort order and name. The keys end on the category's own key, so
# the order is total.
_TREE_ORDER: Final = (
    func.coalesce(col(_PARENT.sort_order), col(Category.sort_order)),
    func.coalesce(col(_PARENT.name), col(Category.name)),
    func.coalesce(col(_PARENT.id), col(Category.id)),
    col(Category.parent_category_id).is_not(None),
    col(Category.sort_order),
    col(Category.name),
    col(Category.id),
)


class SqlAdminCatalogue:
    """Answers what the administrator reads of the catalogue, through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the query object to the session of the request."""
        self._session = session

    def category_page(self, search: AdminCategorySearch) -> AdminCategoryPage:
        """Return one page of every category, each parent followed by its children."""
        filters = {"page": search.page, "page_size": search.page_size}
        page_statement = (
            _category_statement()
            .order_by(*_TREE_ORDER)
            .limit(search.page_size)
            .offset(search.offset)
        )
        with logged_query(logger, "catalogue.admin_category_page", filters) as outcome:
            total = int(
                self._session.execute(select(func.count()).select_from(Category)).scalar_one()
            )
            rows = self._session.execute(page_statement).mappings().all()
            outcome.row_count = len(rows)
        return AdminCategoryPage(
            items=tuple(_category_entry(row) for row in rows),
            page=search.page,
            page_size=search.page_size,
            total=total,
        )

    def category(self, category_id: UUID) -> AdminCategoryEntry | None:
        """Return one category as the list shows it, or None when there is none."""
        statement = _category_statement().where(col(Category.id) == category_id)
        with logged_query(
            logger, "catalogue.admin_category_lookup", {"category_id": str(category_id)}
        ) as outcome:
            row = self._session.execute(statement).mappings().first()
            outcome.row_count = 0 if row is None else 1
        return _category_entry(row) if row is not None else None

    def model_page(self, search: AdminModelSearch) -> AdminModelPage:
        """Return one page of the product models that match, published or not, by name."""
        conditions = _model_conditions(search)
        count_statement = select(func.count()).select_from(ProductModel).where(*conditions)
        page_statement = (
            _model_statement()
            .where(*conditions)
            .order_by(col(ProductModel.name).asc(), col(ProductModel.sku).asc())
            .limit(search.page_size)
            .offset(search.offset)
        )
        filters = {
            "q_length": len(search.text) if search.text is not None else NO_TEXT,
            "category_id": str(search.category_id) if search.category_id else None,
            "published": search.published,
            "page": search.page,
            "page_size": search.page_size,
        }
        with logged_query(logger, "catalogue.admin_model_page", filters) as outcome:
            total = int(self._session.execute(count_statement).scalar_one())
            rows = self._session.execute(page_statement).mappings().all()
            outcome.row_count = len(rows)
        return AdminModelPage(
            items=tuple(_model_entry(row) for row in rows),
            page=search.page,
            page_size=search.page_size,
            total=total,
        )

    def model(self, model_id: UUID) -> AdminModelEntry | None:
        """Return one product model as the list shows it, or None when there is none."""
        statement = _model_statement().where(col(ProductModel.id) == model_id)
        with logged_query(
            logger, "catalogue.admin_model_lookup", {"model_id": str(model_id)}
        ) as outcome:
            row = self._session.execute(statement).mappings().first()
            outcome.row_count = 0 if row is None else 1
        return _model_entry(row) if row is not None else None


def _category_statement() -> Select[tuple[object, ...]]:
    """Return the columns of a category as the list shows it, with its parent's name."""
    model_count = (
        select(func.count())
        .select_from(ProductModel)
        .where(col(ProductModel.category_id) == col(Category.id))
        .correlate(Category)
        .scalar_subquery()
    )
    return (
        select(
            col(Category.id).label("id"),
            col(Category.code).label("code"),
            col(Category.name).label("name"),
            col(Category.slug).label("slug"),
            col(Category.description).label("description"),
            col(Category.parent_category_id).label("parent_category_id"),
            col(_PARENT.name).label("parent_name"),
            col(Category.sort_order).label("sort_order"),
            col(Category.is_active).label("is_active"),
            model_count.label("model_count"),
        )
        .select_from(Category)
        .outerjoin(_PARENT, col(_PARENT.id) == col(Category.parent_category_id))
    )


def _model_statement() -> Select[tuple[object, ...]]:
    """Return the columns of a product model as the list shows it, with its unit count."""
    asset_count = (
        select(func.count())
        .select_from(Asset)
        .where(col(Asset.product_model_id) == col(ProductModel.id))
        .correlate(ProductModel)
        .scalar_subquery()
    )
    return (
        select(
            col(ProductModel.id).label("id"),
            col(ProductModel.sku).label("sku"),
            col(ProductModel.name).label("name"),
            col(ProductModel.slug).label("slug"),
            col(ProductModel.category_id).label("category_id"),
            col(Category.name).label("category_name"),
            col(ProductModel.manufacturer).label("manufacturer"),
            col(ProductModel.model_number).label("model_number"),
            col(ProductModel.short_description).label("short_description"),
            col(ProductModel.long_description).label("long_description"),
            col(ProductModel.daily_rate).label("daily_rate"),
            col(ProductModel.weekly_rate).label("weekly_rate"),
            col(ProductModel.deposit_amount).label("deposit_amount"),
            col(ProductModel.late_fee_per_day).label("late_fee_per_day"),
            col(ProductModel.replacement_value).label("replacement_value"),
            col(ProductModel.min_hire_days).label("min_hire_days"),
            col(ProductModel.max_hire_days).label("max_hire_days"),
            col(ProductModel.is_published).label("is_published"),
            col(ProductModel.updated_at).label("updated_at"),
            asset_count.label("asset_count"),
        )
        .select_from(ProductModel)
        .join(Category, col(Category.id) == col(ProductModel.category_id))
    )


def _model_conditions(search: AdminModelSearch) -> list[ColumnElement[bool]]:
    """Return the WHERE conditions of a model search, every value bound.

    Publication is written as a literal, so the planner can match the
    predicate of the partial index on published models whatever plan it
    caches. The text is escaped before it is bound, so a percent sign matches
    a percent sign.
    """
    conditions: list[ColumnElement[bool]] = []
    if search.category_id is not None:
        conditions.append(col(ProductModel.category_id) == search.category_id)
    if search.published is not None:
        published = true() if search.published else false()
        conditions.append(col(ProductModel.is_published) == published)
    if search.text is not None:
        columns = (
            col(ProductModel.sku),
            col(ProductModel.name),
            col(ProductModel.manufacturer),
            col(ProductModel.model_number),
        )
        conditions.append(
            or_(*(column.icontains(search.text, autoescape=True) for column in columns))
        )
    return conditions


def _category_entry(row: RowMapping) -> AdminCategoryEntry:
    """Return the read model for one category row."""
    return AdminCategoryEntry(
        id=row["id"],
        code=row["code"],
        name=row["name"],
        slug=row["slug"],
        description=row["description"],
        parent_category_id=row["parent_category_id"],
        parent_name=row["parent_name"],
        sort_order=row["sort_order"],
        is_active=row["is_active"],
        model_count=int(row["model_count"]),
    )


def _model_entry(row: RowMapping) -> AdminModelEntry:
    """Return the read model for one product model row.

    Decimal() on each amount. The driver already returns Decimal for a
    NUMERIC column, and wrapping keeps that true whatever it returns, because
    money is never a float (BR-22).
    """
    return AdminModelEntry(
        id=row["id"],
        sku=row["sku"],
        name=row["name"],
        slug=row["slug"],
        category_id=row["category_id"],
        category_name=row["category_name"],
        manufacturer=row["manufacturer"],
        model_number=row["model_number"],
        short_description=row["short_description"],
        long_description=row["long_description"],
        daily_rate=Decimal(row["daily_rate"]),
        weekly_rate=Decimal(row["weekly_rate"]),
        deposit_amount=Decimal(row["deposit_amount"]),
        late_fee_per_day=Decimal(row["late_fee_per_day"]),
        replacement_value=Decimal(row["replacement_value"]),
        min_hire_days=row["min_hire_days"],
        max_hire_days=row["max_hire_days"],
        is_published=row["is_published"],
        asset_count=int(row["asset_count"]),
        updated_at=required_utc(row["updated_at"], UPDATED_AT_COLUMN),
    )
