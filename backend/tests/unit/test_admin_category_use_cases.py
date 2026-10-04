"""Creating and editing a category, run against ports and nothing else (FR-22, BR-44, BR-49).

Each use case holds the terms to the domain's rules, looks the parent up and
holds it to the cap of two levels, refuses a code or a slug another category
holds, whether its own check finds it or the unique constraint does, and
commits the change with its audit event or commits nothing. Every refusal
names its field the way the request did. The unit of work is the in memory
double of tests/support/memory_catalogue.py.
"""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest

from app.application.catalogue.admin_commands import (
    CategoryChanges,
    Change,
    EditCategoryCommand,
    NewCategoryCommand,
)
from app.application.catalogue.manage_categories import (
    CATEGORY_CREATED_ACTION,
    CATEGORY_UPDATED_ACTION,
    CreateCategoryUseCase,
    EditCategoryUseCase,
)
from app.application.refusal import refused_parameter_of
from app.domain.category_rules import CatalogueCategory
from app.domain.errors import NotFound, ValidationFailure
from tests.support.catalogue_terms import ADMINISTRATOR, a_category
from tests.support.clock import FixedClock
from tests.support.memory_catalogue import (
    COMMIT,
    CatalogueStore,
    MemoryAdminCatalogue,
    MemoryCatalogueUnitOfWork,
    StoreFault,
)


def create(store: CatalogueStore, **fields: object) -> object:
    """Create a category in the store, with any field of the command changed."""
    command = NewCategoryCommand(
        actor=ADMINISTRATOR,
        code="PUMPS",
        name="Pumps",
        slug="pumps",
        description=None,
        parent_category_id=None,
        sort_order=20,
    )
    use_case = CreateCategoryUseCase(
        MemoryCatalogueUnitOfWork(store), FixedClock(), MemoryAdminCatalogue(store)
    )
    return use_case.execute(replace(command, **fields))


def edit(store: CatalogueStore, category: CatalogueCategory, changes: CategoryChanges) -> object:
    """Edit a category in the store."""
    use_case = EditCategoryUseCase(
        MemoryCatalogueUnitOfWork(store), FixedClock(), MemoryAdminCatalogue(store)
    )
    return use_case.execute(
        EditCategoryCommand(actor=ADMINISTRATOR, category_id=category.id, changes=changes)
    )


def refused_field(error: pytest.ExceptionInfo[ValidationFailure]) -> str | None:
    """Return the field a refusal names on the wire."""
    return refused_parameter_of(error.value)


class TestCreatingACategory:
    """A new category is active, and it is written with its audit event or not at all."""

    def test_a_category_is_created_active_and_answered_as_the_list_shows_it(self) -> None:
        store = CatalogueStore()
        entry = create(store)
        assert (entry.code, entry.is_active, entry.parent_name, entry.model_count) == (
            "PUMPS",
            True,
            None,
            0,
        )
        assert store.journal == [COMMIT]

    def test_the_audit_event_records_every_field_as_it_became(self) -> None:
        store = CatalogueStore()
        entry = create(store)
        (event,) = store.events
        assert (event.action, event.entity_type, event.entity_id) == (
            CATEGORY_CREATED_ACTION,
            "category",
            entry.id,
        )
        assert event.before_state is None
        assert event.after_state == {
            "code": "PUMPS",
            "name": "Pumps",
            "slug": "pumps",
            "description": None,
            "parent_category_id": None,
            "sort_order": 20,
            "is_active": True,
        }
        assert event.actor_user_id == ADMINISTRATOR.user_id

    def test_a_category_under_a_top_level_one_names_its_parent(self) -> None:
        parent = a_category()
        store = CatalogueStore()
        store.keep(parent)
        entry = create(store, parent_category_id=parent.id)
        assert (entry.parent_category_id, entry.parent_name) == (parent.id, "Drilling")

    def test_a_parent_nobody_can_find_is_refused_naming_it(self) -> None:
        store = CatalogueStore()
        with pytest.raises(ValidationFailure) as error:
            create(store, parent_category_id=uuid4())
        assert refused_field(error) == "parentCategoryId"
        assert store.journal == []

    def test_a_parent_that_is_itself_a_child_is_refused_naming_it(self) -> None:
        top = a_category()
        child = a_category(code="SDS", slug="sds", parent_category_id=top.id)
        store = CatalogueStore()
        store.keep(top, child)
        with pytest.raises(ValidationFailure) as error:
            create(store, parent_category_id=child.id)
        assert refused_field(error) == "parentCategoryId"

    def test_a_code_out_of_its_form_is_refused_naming_it(self) -> None:
        with pytest.raises(ValidationFailure) as error:
            create(CatalogueStore(), code="pumps")
        assert refused_field(error) == "code"

    @pytest.mark.parametrize(("field", "value"), [("code", "DRILL"), ("slug", "drilling")])
    def test_a_value_another_category_holds_is_refused_naming_it(
        self, field: str, value: str
    ) -> None:
        store = CatalogueStore()
        store.keep(a_category())
        with pytest.raises(ValidationFailure) as error:
            create(store, **{field: value})
        assert refused_field(error) == field
        assert store.journal == []

    def test_a_code_taken_in_a_race_is_refused_as_the_check_would_refuse_it(self) -> None:
        store = CatalogueStore(race_on="code")
        with pytest.raises(ValidationFailure) as error:
            create(store)
        assert (refused_field(error), error.value.message) == (
            "code",
            "Another category already has this code.",
        )
        assert store.committed.categories == {}

    def test_a_failed_audit_write_keeps_nothing(self) -> None:
        store = CatalogueStore(fail_audit=True)
        with pytest.raises(StoreFault):
            create(store)
        assert (store.committed.categories, store.journal) == ({}, [])

    def test_a_category_the_read_cannot_find_after_the_commit_is_a_fault(self) -> None:
        store = CatalogueStore(forget_answers=True)
        with pytest.raises(LookupError):
            create(store)


class TestEditingACategory:
    """An edit changes what it names, records what changed and nothing else."""

    def test_a_name_is_changed_and_the_event_records_it_before_and_after(self) -> None:
        category = a_category()
        store = CatalogueStore()
        store.keep(category)
        entry = edit(store, category, CategoryChanges(name=Change("Drills and breakers")))
        assert entry.name == "Drills and breakers"
        (event,) = store.events
        assert (event.action, event.before_state, event.after_state) == (
            CATEGORY_UPDATED_ACTION,
            {"name": "Drilling"},
            {"name": "Drills and breakers"},
        )

    def test_a_category_is_switched_off_and_its_description_cleared(self) -> None:
        category = a_category()
        store = CatalogueStore()
        store.keep(category)
        entry = edit(
            store, category, CategoryChanges(is_active=Change(False), description=Change(None))
        )
        assert (entry.is_active, entry.description) == (False, None)

    def test_an_edit_that_changes_nothing_writes_nothing(self) -> None:
        category = a_category()
        store = CatalogueStore()
        store.keep(category)
        entry = edit(store, category, CategoryChanges(code=Change("DRILL")))
        assert entry.code == "DRILL"
        assert (store.journal, store.events) == ([], [])

    def test_a_category_nobody_can_find_is_not_found(self) -> None:
        with pytest.raises(NotFound):
            edit(CatalogueStore(), a_category(), CategoryChanges(name=Change("Pumps")))

    def test_a_category_is_moved_under_a_top_level_one(self) -> None:
        top, other = a_category(), a_category(code="PUMPS", slug="pumps")
        store = CatalogueStore()
        store.keep(top, other)
        entry = edit(store, other, CategoryChanges(parent_category_id=Change(top.id)))
        assert entry.parent_category_id == top.id

    def test_a_child_is_moved_back_to_the_top_with_no_check_of_a_parent(self) -> None:
        top = a_category()
        child = a_category(code="SDS", slug="sds", parent_category_id=top.id)
        store = CatalogueStore()
        store.keep(top, child)
        entry = edit(store, child, CategoryChanges(parent_category_id=Change(None)))
        assert entry.parent_category_id is None

    def test_a_category_with_children_cannot_be_put_under_another(self) -> None:
        top, other = a_category(), a_category(code="PUMPS", slug="pumps")
        child = a_category(code="SDS", slug="sds", parent_category_id=top.id)
        store = CatalogueStore()
        store.keep(top, other, child)
        with pytest.raises(ValidationFailure) as error:
            edit(store, top, CategoryChanges(parent_category_id=Change(other.id)))
        assert refused_field(error) == "parentCategoryId"

    def test_a_category_cannot_be_put_under_itself(self) -> None:
        category = a_category()
        store = CatalogueStore()
        store.keep(category)
        with pytest.raises(ValidationFailure) as error:
            edit(store, category, CategoryChanges(parent_category_id=Change(category.id)))
        assert refused_field(error) == "parentCategoryId"

    def test_a_slug_another_category_holds_is_refused_and_its_own_is_not(self) -> None:
        first, second = a_category(), a_category(code="PUMPS", slug="pumps")
        store = CatalogueStore()
        store.keep(first, second)
        with pytest.raises(ValidationFailure) as error:
            edit(store, second, CategoryChanges(slug=Change("drilling")))
        assert refused_field(error) == "slug"
        entry = edit(store, second, CategoryChanges(code=Change("WATER"), slug=Change("pumps")))
        assert entry.code == "WATER"

    def test_a_slug_taken_in_a_race_is_refused_naming_it(self) -> None:
        category = a_category()
        store = CatalogueStore()
        store.keep(category)
        store.race_on = "slug"
        with pytest.raises(ValidationFailure) as error:
            edit(store, category, CategoryChanges(slug=Change("drills")))
        assert refused_field(error) == "slug"
        assert store.events == []

    def test_a_blank_name_is_refused_naming_it(self) -> None:
        category = a_category()
        store = CatalogueStore()
        store.keep(category)
        with pytest.raises(ValidationFailure) as error:
            edit(store, category, CategoryChanges(name=Change("  ")))
        assert refused_field(error) == "name"
