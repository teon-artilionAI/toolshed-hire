"""The ports of the administrator's catalogue, two that write and one that reads (FR-22).

`CategoryRepository` and `CatalogueEntryRepository` are reached through the
unit of work, so a change to the catalogue and its audit event commit together
(BR-49). Each reads a row under a lock before it is changed, so two
administrators editing one model cannot both read the same figures and the
second write cannot silently undo the first.

A code, a SKU and a slug are unique, and the database has the last word on it.
A use case asks first which values are already taken, so it can say so in a
plain sentence, and a repository that loses a race to the unique constraint
raises `DuplicateCatalogueValue` naming the field, which the use case answers
the same way.

`AdminCatalogueQuery` is the read side. It answers the administrator's lists
and the one model, and it returns the read models of this package.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.application.catalogue.admin_read_models import (
    AdminCategoryEntry,
    AdminCategoryPage,
    AdminCategorySearch,
    AdminModelEntry,
    AdminModelPage,
    AdminModelSearch,
)
from app.domain.catalogue_entry_rules import CatalogueEntry
from app.domain.category_rules import CatalogueCategory


class DuplicateCatalogueValue(Exception):
    """A unique constraint refused a value another category, model or unit already holds.

    Attributes:
        field: The field whose value was taken, named the way the domain names
            it, for example `slug`.

    """

    def __init__(self, field: str) -> None:
        """Keep the field whose value was taken."""
        super().__init__(f"Attempted to store a {field} that another row already holds.")
        self.field = field


class CategoryRepository(Protocol):
    """The categories, read and written inside a unit of work."""

    def get(self, category_id: UUID) -> CatalogueCategory | None:
        """Return the category with this key, or None when there is none."""
        ...

    def get_for_update(self, category_id: UUID) -> CatalogueCategory | None:
        """Return the category with this key locked for the rest of the transaction, or None."""
        ...

    def has_children(self, category_id: UUID) -> bool:
        """Return True when another category sits under this one."""
        ...

    def taken_fields(
        self, *, code: str | None, slug: str | None, other_than: UUID | None
    ) -> frozenset[str]:
        """Return which of a code and a slug another category already holds, in one read.

        Args:
            code: The code to look for, or None not to look.
            slug: The slug to look for, or None not to look.
            other_than: The category being edited, which may hold its own values.

        """
        ...

    def add(self, category: CatalogueCategory, now: datetime) -> None:
        """Write a new category inside the current transaction.

        Raises:
            DuplicateCatalogueValue: If the unique constraint on the code or
                the slug refused it.

        """
        ...

    def save(self, category: CatalogueCategory, now: datetime) -> None:
        """Write a category this transaction locked back, stamped as changed now.

        Raises:
            DuplicateCatalogueValue: If the unique constraint on the code or
                the slug refused it.

        """
        ...


class CatalogueEntryRepository(Protocol):
    """The product models, read and written inside a unit of work."""

    def get_for_update(self, model_id: UUID) -> CatalogueEntry | None:
        """Return the product model with this key, locked until the transaction ends, or None."""
        ...

    def taken_fields(
        self, *, sku: str | None, slug: str | None, other_than: UUID | None
    ) -> frozenset[str]:
        """Return which of a SKU and a slug another product model already holds, in one read.

        Args:
            sku: The SKU to look for, or None not to look.
            slug: The slug to look for, or None not to look.
            other_than: The model being edited, which may hold its own values.

        """
        ...

    def add(self, entry: CatalogueEntry, now: datetime) -> None:
        """Write a new product model inside the current transaction.

        Raises:
            DuplicateCatalogueValue: If the unique constraint on the SKU or the
                slug refused it.

        """
        ...

    def save(self, entry: CatalogueEntry, now: datetime) -> None:
        """Write a product model this transaction locked back, stamped as changed now.

        Raises:
            DuplicateCatalogueValue: If the unique constraint on the slug refused it.

        """
        ...


class AdminCatalogueQuery(Protocol):
    """What the administrator reads of the catalogue."""

    def category_page(self, search: AdminCategorySearch) -> AdminCategoryPage:
        """Return one page of every category, active or not, each parent followed by its children.

        It takes the same number of statements however many categories there are.
        """
        ...

    def category(self, category_id: UUID) -> AdminCategoryEntry | None:
        """Return one category as the list shows it, or None when there is none."""
        ...

    def model_page(self, search: AdminModelSearch) -> AdminModelPage:
        """Return one page of the product models that match, published or not, by name.

        It takes the same number of statements however long the page is.
        """
        ...

    def model(self, model_id: UUID) -> AdminModelEntry | None:
        """Return one product model as the list shows it, or None when there is none."""
        ...
