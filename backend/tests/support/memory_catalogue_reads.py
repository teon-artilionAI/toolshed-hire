"""The read of the admin catalogue over an in memory store, with no database at all.

It answers the `AdminCatalogueQuery` port from what the store of
`memory_catalogue` has committed, which is what a use case reads its answer
back from once it has committed. It keeps every search it is asked, so a test
can see what the read service handed it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final
from uuid import UUID

from app.application.catalogue.admin_read_models import (
    AdminCategoryEntry,
    AdminCategoryPage,
    AdminCategorySearch,
    AdminModelEntry,
    AdminModelPage,
    AdminModelSearch,
)

if TYPE_CHECKING:
    from tests.support.memory_catalogue import CatalogueStore

NEVER_CHANGED: Final[datetime] = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass
class MemoryAdminCatalogue:
    """The admin catalogue read over what the store has committed."""

    store: CatalogueStore
    asked: list[AdminCategorySearch | AdminModelSearch] = field(default_factory=list)

    def category_page(self, search: AdminCategorySearch) -> AdminCategoryPage:
        """Answer every committed category on one page."""
        self.asked.append(search)
        items = tuple(self._category(key) for key in self.store.committed.categories)
        return AdminCategoryPage(
            items=items, page=search.page, page_size=search.page_size, total=len(items)
        )

    def category(self, category_id: UUID) -> AdminCategoryEntry | None:
        """Answer one committed category, or nothing when the test made the read forget."""
        if self.store.forget_answers or category_id not in self.store.committed.categories:
            return None
        return self._category(category_id)

    def model_page(self, search: AdminModelSearch) -> AdminModelPage:
        """Answer every committed model on one page."""
        self.asked.append(search)
        items = tuple(self._model(key) for key in self.store.committed.entries)
        return AdminModelPage(
            items=items, page=search.page, page_size=search.page_size, total=len(items)
        )

    def model(self, model_id: UUID) -> AdminModelEntry | None:
        """Answer one committed model, or nothing when the test made the read forget."""
        if self.store.forget_answers or model_id not in self.store.committed.entries:
            return None
        return self._model(model_id)

    def _category(self, category_id: UUID) -> AdminCategoryEntry:
        """Return the read model of one committed category."""
        categories = self.store.committed.categories
        terms = categories[category_id].terms
        parent = categories.get(terms.parent_category_id) if terms.parent_category_id else None
        return AdminCategoryEntry(
            id=category_id,
            code=terms.code,
            name=terms.name,
            slug=terms.slug,
            description=terms.description,
            parent_category_id=terms.parent_category_id,
            parent_name=parent.terms.name if parent is not None else None,
            sort_order=terms.sort_order,
            is_active=terms.is_active,
            model_count=sum(
                entry.terms.category_id == category_id
                for entry in self.store.committed.entries.values()
            ),
        )

    def _model(self, model_id: UUID) -> AdminModelEntry:
        """Return the read model of one committed model."""
        entry = self.store.committed.entries[model_id]
        terms = entry.terms
        category = self.store.committed.categories[terms.category_id]
        return AdminModelEntry(
            id=model_id,
            sku=terms.sku,
            name=terms.name,
            slug=terms.slug,
            category_id=terms.category_id,
            category_name=category.terms.name,
            manufacturer=terms.manufacturer,
            model_number=terms.model_number,
            short_description=terms.short_description,
            long_description=terms.long_description,
            daily_rate=terms.daily_rate,
            weekly_rate=terms.weekly_rate,
            deposit_amount=terms.deposit_amount,
            late_fee_per_day=terms.late_fee_per_day,
            replacement_value=terms.replacement_value,
            min_hire_days=terms.min_hire_days,
            max_hire_days=terms.max_hire_days,
            is_published=entry.is_published,
            asset_count=self.store.asset_counts.get(model_id, 0),
            updated_at=self.store.committed.changed_at.get(model_id, NEVER_CHANGED),
        )


__all__ = ["NEVER_CHANGED", "MemoryAdminCatalogue"]
