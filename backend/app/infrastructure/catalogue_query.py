"""The SQL query object behind the catalogue read port.

This is the read side of the catalogue module. It selects columns, never
entities, and returns the read models of the application layer, so nothing a
visitor is not meant to see can ride along on a row.

Only published models are ever returned, and a model that is not published is
answered exactly as a slug nobody used.

The filters, the order and the summary columns of a model search come from
`app/infrastructure/catalogue_sql.py`. The availability search builds on the
same ones, and that module says how they are written and what slows down first
as the catalogue grows.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict
from decimal import Decimal
from typing import Final
from uuid import UUID

from sqlalchemy import Executable, RowMapping, and_, func, select, true
from sqlmodel import Session, col

from app.application.catalogue.read_models import (
    CategoryEntry,
    ModelDetail,
    ModelPage,
    ModelSearch,
)
from app.infrastructure.catalogue_sql import (
    model_conditions,
    search_filters,
    sort_columns,
    summary_columns,
    summary_of,
)
from app.infrastructure.models import Category, ProductModel
from app.infrastructure.query_log import logged_query

logger = logging.getLogger(__name__)

NO_DESCRIPTION: Final[str] = ""


class SqlCatalogueQuery:
    """Answers what a visitor asks of the catalogue, through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the query object to the session of the request."""
        self._session = session

    def list_categories(self) -> list[CategoryEntry]:
        """Return every active category, each parent followed by its children.

        One statement counts the published models of each category. The count
        of a parent is then rolled up from its children here, because there
        are a dozen categories and a recursive statement would be harder to
        read than the loop.
        """
        statement: Executable = (
            select(
                col(Category.id).label("id"),
                col(Category.code).label("code"),
                col(Category.name).label("name"),
                col(Category.slug).label("slug"),
                col(Category.description).label("description"),
                col(Category.parent_category_id).label("parent_id"),
                col(Category.sort_order).label("sort_order"),
                func.count(col(ProductModel.id)).label("own_models"),
            )
            .select_from(Category)
            .outerjoin(
                ProductModel,
                and_(
                    col(ProductModel.category_id) == col(Category.id),
                    col(ProductModel.is_published) == true(),
                ),
            )
            .where(col(Category.is_active) == true())
            .group_by(col(Category.id))
        )
        with logged_query(logger, "catalogue.category_list", {"active_only": True}) as outcome:
            rows = self._session.execute(statement).mappings().all()
            outcome.row_count = len(rows)
        return _category_tree(rows)

    def category_exists(self, slug: str) -> bool:
        """Return True when an active category carries this slug."""
        statement = (
            select(col(Category.id))
            .where(col(Category.slug) == slug, col(Category.is_active) == true())
            .limit(1)
        )
        with logged_query(logger, "catalogue.category_lookup", {"category": slug}) as outcome:
            found = self._session.execute(statement).first() is not None
            outcome.row_count = int(found)
        return found

    def search_models(self, search: ModelSearch) -> ModelPage:
        """Return one page of the published models that match a search.

        Two statements, the count and the page. Both carry the same conditions,
        so the total always describes the list the page was cut from.
        """
        conditions = model_conditions(search)
        count_statement = select(func.count()).select_from(ProductModel).where(*conditions)
        page_statement = (
            select(*summary_columns())
            .select_from(ProductModel)
            .join(Category, col(Category.id) == col(ProductModel.category_id))
            .where(*conditions)
            .order_by(*sort_columns(search.sort))
            .limit(search.page_size)
            .offset(search.offset)
        )
        with logged_query(logger, "catalogue.model_search", search_filters(search)) as outcome:
            total = int(self._session.execute(count_statement).scalar_one())
            rows = self._session.execute(page_statement).mappings().all()
            outcome.row_count = len(rows)
        return ModelPage(
            items=tuple(summary_of(row) for row in rows),
            page=search.page,
            page_size=search.page_size,
            total=total,
        )

    def find_model(self, slug: str) -> ModelDetail | None:
        """Return the published model with this slug, or None when there is none."""
        statement = (
            select(
                *summary_columns(),
                col(ProductModel.long_description).label("long_description"),
                col(ProductModel.late_fee_per_day).label("late_fee_per_day"),
            )
            .select_from(ProductModel)
            .join(Category, col(Category.id) == col(ProductModel.category_id))
            .where(col(ProductModel.slug) == slug, col(ProductModel.is_published) == true())
        )
        with logged_query(logger, "catalogue.model_lookup", {"slug": slug}) as outcome:
            row = self._session.execute(statement).mappings().first()
            outcome.row_count = 0 if row is None else 1
        if row is None:
            return None
        return ModelDetail(
            **asdict(summary_of(row)),
            long_description=row["long_description"],
            late_fee_per_day=Decimal(row["late_fee_per_day"]),
        )


def _category_tree(rows: Sequence[RowMapping]) -> list[CategoryEntry]:
    """Order the categories parents first and roll the model counts up.

    A category whose parent is missing or inactive is listed at the top level
    with no parent code, so an active category is never dropped from the list
    because of the state of another one.
    """
    codes: dict[UUID, str] = {row["id"]: row["code"] for row in rows}
    children: dict[UUID | None, list[RowMapping]] = defaultdict(list)
    for row in rows:
        parent_id = row["parent_id"]
        children[parent_id if parent_id in codes else None].append(row)
    for siblings in children.values():
        siblings.sort(key=lambda row: (row["sort_order"], row["name"]))

    entries: list[CategoryEntry] = []

    def place(row: RowMapping, parent_code: str | None) -> int:
        """Append a category and everything under it, returning its model count."""
        position = len(entries)
        entries.append(_category_entry(row, parent_code, 0))
        total = int(row["own_models"]) + sum(
            place(child, row["code"]) for child in children[row["id"]]
        )
        entries[position] = _category_entry(row, parent_code, total)
        return total

    for row in children[None]:
        place(row, None)
    return entries


def _category_entry(row: RowMapping, parent_code: str | None, model_count: int) -> CategoryEntry:
    """Return the read model for one category row."""
    return CategoryEntry(
        code=row["code"],
        name=row["name"],
        slug=row["slug"],
        description=row["description"] or NO_DESCRIPTION,
        parent_code=parent_code,
        sort_order=row["sort_order"],
        model_count=model_count,
    )
