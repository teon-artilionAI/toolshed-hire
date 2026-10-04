"""The administrator's reads of the catalogue and the small pieces the writes share (FR-22).

The read service hands each search to the query object and answers a model
nobody can find as not found. A search cannot be built for a page out of
range, which is the second line behind the limits the HTTP boundary holds.
An edit names only the fields that were sent, and the audit event records
only the fields that changed.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.application.catalogue.admin_commands import CategoryChanges, Change, chosen
from app.application.catalogue.admin_read_models import AdminCategorySearch, AdminModelSearch
from app.application.catalogue.admin_reads import ReadAdminCatalogue
from app.application.catalogue.catalogue_changes import changed_fields
from app.domain.errors import NotFound
from tests.support.catalogue_terms import ADMINISTRATOR, a_category, an_entry, category_terms
from tests.support.memory_catalogue import CatalogueStore, MemoryAdminCatalogue


def a_search(**fields: object) -> AdminModelSearch:
    """Return a search of every model, first page of twenty, with any field changed."""
    search: dict[str, object] = {
        "text": None,
        "category_id": None,
        "published": None,
        "page": 1,
        "page_size": 20,
        **fields,
    }
    return AdminModelSearch(**search)


class TestTheReads:
    """Each read asks the query object and answers what it found."""

    def test_the_categories_are_read_with_the_search_asked_for(self) -> None:
        category = a_category()
        store = CatalogueStore()
        store.keep(category)
        catalogue = MemoryAdminCatalogue(store)
        page = ReadAdminCatalogue(catalogue).categories(ADMINISTRATOR, AdminCategorySearch())
        assert ([entry.id for entry in page.items], page.page_size) == ([category.id], 100)
        assert catalogue.asked == [AdminCategorySearch(page=1, page_size=100)]

    def test_the_models_are_read_with_the_search_asked_for(self) -> None:
        category = a_category()
        entry = an_entry(category.id, published=False)
        store = CatalogueStore(asset_counts={entry.id: 3})
        store.keep(category, entry)
        catalogue = MemoryAdminCatalogue(store)
        search = a_search(text="hammer", category_id=category.id, published=False)
        page = ReadAdminCatalogue(catalogue).models(ADMINISTRATOR, search)
        assert [(item.sku, item.asset_count) for item in page.items] == [("DR-BOSCH-GBH226", 3)]
        assert catalogue.asked == [search]

    def test_one_model_is_answered_published_or_not(self) -> None:
        category = a_category()
        entry = an_entry(category.id, published=False)
        store = CatalogueStore()
        store.keep(category, entry)
        found = ReadAdminCatalogue(MemoryAdminCatalogue(store)).model(ADMINISTRATOR, entry.id)
        assert (found.id, found.is_published) == (entry.id, False)

    def test_a_model_nobody_can_find_is_not_found(self) -> None:
        reads = ReadAdminCatalogue(MemoryAdminCatalogue(CatalogueStore()))
        with pytest.raises(NotFound):
            reads.model(ADMINISTRATOR, uuid4())


class TestASearchCannotBeOutOfRange:
    """A page is from one to ten thousand and holds from one to a hundred."""

    @pytest.mark.parametrize(("page", "page_size"), [(0, 20), (10_001, 20), (1, 0), (1, 101)])
    def test_a_model_search_out_of_range_cannot_be_built(self, page: int, page_size: int) -> None:
        with pytest.raises(ValueError, match="Attempted to list product models"):
            a_search(page=page, page_size=page_size)

    @pytest.mark.parametrize(("page", "page_size"), [(0, 100), (1, 101)])
    def test_a_category_search_out_of_range_cannot_be_built(
        self, page: int, page_size: int
    ) -> None:
        with pytest.raises(ValueError, match="Attempted to list categories"):
            AdminCategorySearch(page=page, page_size=page_size)

    def test_a_page_says_how_many_rows_come_before_it(self) -> None:
        assert a_search(page=3, page_size=20).offset == 40
        assert AdminCategorySearch(page=2, page_size=10).offset == 10


class TestWhatAnEditNamesAndRecords:
    """A field left out keeps its value, and only a changed field is recorded."""

    def test_a_field_left_out_keeps_its_value_and_a_cleared_one_is_cleared(self) -> None:
        terms = category_terms()
        changed = CategoryChanges(description=Change(None), sort_order=Change(5)).applied_to(terms)
        assert (changed.name, changed.description, changed.sort_order) == ("Drilling", None, 5)

    def test_chosen_keeps_the_current_value_when_nothing_was_named(self) -> None:
        assert (chosen(1, None), chosen(1, Change(2))) == (1, 2)

    def test_only_the_fields_that_changed_are_recorded(self) -> None:
        before, after = changed_fields({"a": "1", "b": 2}, {"a": "1", "b": 3})
        assert (before, after) == ({"b": 2}, {"b": 3})
