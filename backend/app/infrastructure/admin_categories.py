"""The SQL repository of the categories the administrator writes (FR-22).

It maps the `category` rows to the domain's `CatalogueCategory` and back, on
the session of the unit of work that created it. A category about to change
is read with `SELECT ... FOR UPDATE`, so two administrators editing one
category take turns and the second reads what the first committed.

Every statement here stands on a key. A category is read by its primary key,
a code and a slug are looked up through their unique indexes in one statement,
and whether a category has children is one probe of a table that holds a few
dozen rows. A unique constraint that refuses a row is named by
`app/infrastructure/catalogue_uniques.py`.

Every instant written comes from the clock the use case was handed.
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, or_
from sqlmodel import Session, col, select

from app.domain import category_rules as fields
from app.domain.category_rules import CatalogueCategory, CategoryTerms
from app.infrastructure.catalogue_uniques import CATEGORY_UNIQUES, flushed
from app.infrastructure.models import Category

logger = logging.getLogger(__name__)


class SqlCategoryRepository:
    """Reads and writes categories through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to the session of its unit of work."""
        self._session = session

    def get(self, category_id: UUID) -> CatalogueCategory | None:
        """Return the category with this key, or None when there is none."""
        statement = (
            select(Category)
            .where(col(Category.id) == category_id)
            .execution_options(populate_existing=True)
        )
        row = self._session.exec(statement).first()
        logger.debug(
            "catalogue.category_read",
            extra={"category_id": str(category_id), "found": row is not None},
        )
        return _category_of(row) if row is not None else None

    def get_for_update(self, category_id: UUID) -> CatalogueCategory | None:
        """Return the category with this key locked for the rest of the transaction, or None."""
        statement = (
            select(Category)
            .where(col(Category.id) == category_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        row = self._session.exec(statement).first()
        logger.debug(
            "catalogue.category_locked",
            extra={"category_id": str(category_id), "found": row is not None},
        )
        return _category_of(row) if row is not None else None

    def has_children(self, category_id: UUID) -> bool:
        """Return True when another category sits under this one."""
        statement = (
            select(col(Category.id)).where(col(Category.parent_category_id) == category_id).limit(1)
        )
        found = self._session.exec(statement).first() is not None
        logger.debug(
            "catalogue.category_children_read",
            extra={"category_id": str(category_id), "has_children": found},
        )
        return found

    def taken_fields(
        self, *, code: str | None, slug: str | None, other_than: UUID | None
    ) -> frozenset[str]:
        """Return which of a code and a slug another category already holds, in one read."""
        wanted: list[ColumnElement[bool]] = []
        if code is not None:
            wanted.append(col(Category.code) == code)
        if slug is not None:
            wanted.append(col(Category.slug) == slug)
        if not wanted:
            return frozenset()
        statement = select(col(Category.code), col(Category.slug)).where(or_(*wanted))
        if other_than is not None:
            statement = statement.where(col(Category.id) != other_than)
        taken: set[str] = set()
        for held_code, held_slug in self._session.exec(statement).all():
            if code is not None and held_code == code:
                taken.add(fields.CODE)
            if slug is not None and held_slug == slug:
                taken.add(fields.SLUG)
        logger.debug("catalogue.category_values_checked", extra={"taken": sorted(taken)})
        return frozenset(taken)

    def add(self, category: CatalogueCategory, now: datetime) -> None:
        """Write a new category inside the current transaction.

        Raises:
            DuplicateCatalogueValue: If the unique constraint on the code or
                the slug refused it.

        """
        row = Category(id=category.id, created_at=now)
        _copy_terms(row, category.terms, now)
        self._session.add(row)
        flushed(self._session, CATEGORY_UNIQUES, "insert a category row")
        logger.info(
            "catalogue.category_added",
            extra={"category_id": str(category.id), "code": category.terms.code},
        )

    def save(self, category: CatalogueCategory, now: datetime) -> None:
        """Write a category this transaction locked back, stamped as changed now.

        Raises:
            DuplicateCatalogueValue: If the unique constraint on the code or
                the slug refused it.
            RuntimeError: If the category has no row, which would mean a use
                case is saving a category it never read.

        """
        row = self._session.get(Category, category.id)
        if row is None:
            raise RuntimeError(
                f"Attempted to save category {category.id}, which has no row. Read it with "
                "get_for_update first."
            )
        _copy_terms(row, category.terms, now)
        self._session.add(row)
        flushed(self._session, CATEGORY_UNIQUES, "update a category row")
        logger.info(
            "catalogue.category_saved",
            extra={"category_id": str(category.id), "code": category.terms.code},
        )


def _copy_terms(row: Category, terms: CategoryTerms, now: datetime) -> None:
    """Copy the terms of a category onto its row and stamp the row as changed now."""
    row.code = terms.code
    row.name = terms.name
    row.slug = terms.slug
    row.description = terms.description
    row.parent_category_id = terms.parent_category_id
    row.sort_order = terms.sort_order
    row.is_active = terms.is_active
    row.updated_at = now


def _category_of(row: Category) -> CatalogueCategory:
    """Return the domain category for a `category` row."""
    return CatalogueCategory(
        id=row.id,
        terms=CategoryTerms(
            code=row.code,
            name=row.name,
            slug=row.slug,
            description=row.description,
            parent_category_id=row.parent_category_id,
            sort_order=row.sort_order,
            is_active=row.is_active,
        ),
    )
