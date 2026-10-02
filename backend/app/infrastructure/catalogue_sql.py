"""The SQL a model search is built from, shared by the catalogue and availability queries.

The catalogue lists published models. The availability search lists the same
models in the same order and adds an answer from every branch. Both take their
filters, their order and their summary columns from here, so the two can never
disagree about what a search means.

Three things are decided here and nowhere else.

A published model is the only kind a visitor is shown. The condition is
written so the partial index `ix_product_model_published` on
`(category_id, name) WHERE is_published` can serve a category browse.

The order of a list comes from `_SORT_COLUMNS`, a table from the `ModelSort`
enumeration to columns (C-28). A request can only choose a member. Every order
ends on the SKU, which is unique, so a page boundary never splits two rows that
compare equal and a model can never appear on two pages.

Every value is a bound parameter. The search text is escaped before it is
bound, so a percent sign a visitor typed matches a percent sign.

At ten times the data the text search is the first thing here to slow down. It
is a contains match on three columns, which no btree can serve, so it reads
every published model. At 120 models that is nothing and at 1,200 it is still
a page or two. If the catalogue ever grows past that, the fix is a trigram
index on the three columns, and `pg_trgm` is already installed. The page
itself is read with OFFSET, which costs in proportion to the page number and is
bounded by `MAXIMUM_PAGE`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final
from uuid import UUID

from sqlalchemy import ColumnElement, RowMapping, Select, or_, select, true
from sqlalchemy.orm import aliased
from sqlmodel import col

from app.application.catalogue.read_models import ModelSearch, ModelSort, ModelSummary
from app.infrastructure.models import Category, ProductModel

type SummaryColumn = (
    ColumnElement[str] | ColumnElement[str | None] | ColumnElement[Decimal] | ColumnElement[int]
)
type SortColumn = ColumnElement[str] | ColumnElement[Decimal]

# The server side enumeration of sort orders (C-28). The name and the SKU break
# ties, so the order is total and a page boundary is stable.
_SORT_COLUMNS: Final[dict[ModelSort, tuple[SortColumn, ...]]] = {
    ModelSort.NAME: (col(ProductModel.name).asc(), col(ProductModel.sku).asc()),
    ModelSort.DAILY_RATE_ASC: (
        col(ProductModel.daily_rate).asc(),
        col(ProductModel.name).asc(),
        col(ProductModel.sku).asc(),
    ),
    ModelSort.DAILY_RATE_DESC: (
        col(ProductModel.daily_rate).desc(),
        col(ProductModel.name).asc(),
        col(ProductModel.sku).asc(),
    ),
}

# The columns the free text of a search is matched against.
_TEXT_COLUMNS: Final = (
    col(ProductModel.name),
    col(ProductModel.manufacturer),
    col(ProductModel.model_number),
)


def summary_columns() -> tuple[SummaryColumn, ...]:
    """Return the labelled columns of a model summary.

    The statement that selects them has to join `category` to `product_model`.
    """
    return (
        col(ProductModel.sku).label("sku"),
        col(ProductModel.slug).label("slug"),
        col(ProductModel.name).label("name"),
        col(ProductModel.manufacturer).label("manufacturer"),
        col(ProductModel.model_number).label("model_number"),
        col(Category.code).label("category_code"),
        col(Category.name).label("category_name"),
        col(ProductModel.short_description).label("short_description"),
        col(ProductModel.daily_rate).label("daily_rate"),
        col(ProductModel.weekly_rate).label("weekly_rate"),
        col(ProductModel.deposit_amount).label("deposit_amount"),
        col(ProductModel.min_hire_days).label("min_hire_days"),
        col(ProductModel.max_hire_days).label("max_hire_days"),
        col(ProductModel.image_path).label("image_path"),
    )


def summary_of(row: RowMapping) -> ModelSummary:
    """Return the model summary a row of `summary_columns` holds.

    Decimal() on each price. The driver already returns Decimal for a NUMERIC
    column, and wrapping keeps that true whatever it returns, because money is
    never a float (BR-22).
    """
    return ModelSummary(
        sku=row["sku"],
        slug=row["slug"],
        name=row["name"],
        manufacturer=row["manufacturer"],
        model_number=row["model_number"],
        category_code=row["category_code"],
        category_name=row["category_name"],
        short_description=row["short_description"],
        daily_rate=Decimal(row["daily_rate"]),
        weekly_rate=Decimal(row["weekly_rate"]),
        deposit_amount=Decimal(row["deposit_amount"]),
        min_hire_days=row["min_hire_days"],
        max_hire_days=row["max_hire_days"],
        image_path=row["image_path"],
    )


def model_conditions(search: ModelSearch) -> list[ColumnElement[bool]]:
    """Return the WHERE conditions of a model search, every value bound."""
    conditions: list[ColumnElement[bool]] = [col(ProductModel.is_published) == true()]
    if search.category_slug is not None:
        conditions.append(
            col(ProductModel.category_id).in_(_category_scope(search.category_slug))
        )
    if search.text is not None:
        conditions.append(
            or_(*(column.icontains(search.text, autoescape=True) for column in _TEXT_COLUMNS))
        )
    return conditions


def sort_columns(sort: ModelSort) -> tuple[SortColumn, ...]:
    """Return the ORDER BY columns a sort order stands for."""
    return _SORT_COLUMNS[sort]


def search_filters(search: ModelSearch) -> dict[str, object]:
    """Return what a model search was asked with, for the log.

    The search text is reported by its length only. What a visitor typed into
    a search box is never written to the log.
    """
    return {
        "category": search.category_slug,
        "q_length": len(search.text) if search.text is not None else 0,
        "sort": search.sort.value,
        "page": search.page,
        "page_size": search.page_size,
    }


def _category_scope(slug: str) -> Select[tuple[UUID]]:
    """Return the keys of the active category with this slug and of its active children.

    Both tables are aliased, so the subquery stands on its own inside a
    statement that already joins `category` for the name of each model.
    """
    chosen = aliased(Category)
    member = aliased(Category)
    chosen_id = (
        select(col(chosen.id))
        .where(col(chosen.slug) == slug, col(chosen.is_active) == true())
        .scalar_subquery()
    )
    return select(col(member.id)).where(
        col(member.is_active) == true(),
        or_(col(member.id) == chosen_id, col(member.parent_category_id) == chosen_id),
    )
