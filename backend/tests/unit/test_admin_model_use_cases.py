"""Creating, editing and publishing a product model, run against ports and nothing else (US-30).

A new model starts unpublished. An edit changes the fields it names and
records the figures before and after, so the event of a rate change says the
daily rate went from 280.00 to 310.00. A model is only classified under an
active category, and a SKU or a slug another model holds is refused whether
the check finds it or the unique constraint does. Publishing a model that is
already published changes nothing. Every refusal names its field the way the
request did, and a refused change commits nothing.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest

from app.application.catalogue.admin_commands import (
    Change,
    EditModelCommand,
    ModelChanges,
    NewModelCommand,
    PublicationCommand,
)
from app.application.catalogue.manage_models import (
    MODEL_CREATED_ACTION,
    MODEL_UPDATED_ACTION,
    CreateModelUseCase,
    EditModelUseCase,
)
from app.application.catalogue.publish_model import (
    MODEL_PUBLISHED_ACTION,
    MODEL_UNPUBLISHED_ACTION,
    PublishModelUseCase,
)
from app.application.refusal import refused_parameter_of
from app.domain.catalogue_entry_rules import CatalogueEntry
from app.domain.category_rules import CatalogueCategory
from app.domain.errors import NotFound, ValidationFailure
from tests.support.catalogue_terms import (
    ADMINISTRATOR,
    DAILY_AFTER,
    a_category,
    an_entry,
    model_terms,
)
from tests.support.clock import DEFAULT_INSTANT, FixedClock
from tests.support.memory_catalogue import (
    COMMIT,
    CatalogueStore,
    MemoryAdminCatalogue,
    MemoryCatalogueUnitOfWork,
)


def stocked() -> tuple[CatalogueStore, CatalogueCategory, CatalogueEntry]:
    """Return a store holding one active category and the hammer, published, in it."""
    category = a_category()
    entry = an_entry(category.id)
    store = CatalogueStore()
    store.keep(category, entry)
    return store, category, entry


def create(store: CatalogueStore, category: CatalogueCategory, **fields: object) -> object:
    """Create a model in a category, with any field of its terms changed."""
    use_case = CreateModelUseCase(
        MemoryCatalogueUnitOfWork(store), FixedClock(), MemoryAdminCatalogue(store)
    )
    terms = model_terms(category.id, sku="PU-HONDA-WB20", slug="honda-wb20-pump", **fields)
    return use_case.execute(NewModelCommand(actor=ADMINISTRATOR, terms=terms))


def edit(store: CatalogueStore, entry: CatalogueEntry, **changes: object) -> object:
    """Edit a model, naming each change by its field."""
    use_case = EditModelUseCase(
        MemoryCatalogueUnitOfWork(store), FixedClock(), MemoryAdminCatalogue(store)
    )
    named = ModelChanges(**{field: Change(value) for field, value in changes.items()})
    return use_case.execute(
        EditModelCommand(actor=ADMINISTRATOR, model_id=entry.id, changes=named)
    )


def publish(store: CatalogueStore, model_id: object, published: bool) -> object:
    """Publish a model or take it out of the catalogue."""
    use_case = PublishModelUseCase(
        MemoryCatalogueUnitOfWork(store), FixedClock(), MemoryAdminCatalogue(store)
    )
    return use_case.execute(
        PublicationCommand(actor=ADMINISTRATOR, model_id=model_id, published=published)
    )


def refused_field(error: pytest.ExceptionInfo[ValidationFailure]) -> str | None:
    """Return the field a refusal names on the wire."""
    return refused_parameter_of(error.value)


class TestCreatingAModel:
    """A new model starts unpublished and is written with its audit event or not at all."""

    def test_a_model_is_created_unpublished_and_answered_as_the_list_shows_it(self) -> None:
        store, category, _ = stocked()
        entry = create(store, category)
        assert (entry.sku, entry.is_published, entry.category_name, entry.asset_count) == (
            "PU-HONDA-WB20",
            False,
            "Drilling",
            0,
        )
        assert entry.updated_at == DEFAULT_INSTANT

    def test_the_audit_event_records_the_figures_as_text_and_the_model_unpublished(self) -> None:
        store, category, _ = stocked()
        entry = create(store, category)
        (event,) = store.events
        assert (event.action, event.entity_type, event.entity_id) == (
            MODEL_CREATED_ACTION,
            "product_model",
            entry.id,
        )
        assert event.after_state is not None
        assert (
            event.after_state["daily_rate"],
            event.after_state["category_id"],
            event.after_state["is_published"],
        ) == ("280.00", str(category.id), False)

    def test_a_category_nobody_can_find_is_refused_naming_it(self) -> None:
        store, _, _ = stocked()
        with pytest.raises(ValidationFailure) as error:
            create(store, a_category())
        assert refused_field(error) == "categoryId"
        assert store.journal == []

    def test_a_category_that_was_switched_off_is_refused_naming_it(self) -> None:
        store, _, _ = stocked()
        off = a_category(code="OFF", slug="off", is_active=False)
        store.keep(off)
        with pytest.raises(ValidationFailure) as error:
            create(store, off)
        assert refused_field(error) == "categoryId"

    def test_a_weekly_rate_above_seven_days_is_refused_naming_it(self) -> None:
        store, category, _ = stocked()
        with pytest.raises(ValidationFailure) as error:
            create(store, category, weekly_rate=Decimal("2000.00"))
        assert refused_field(error) == "weeklyRate"

    @pytest.mark.parametrize(
        ("field", "value"),
        [("sku", "DR-BOSCH-GBH226"), ("slug", "bosch-gbh-2-26-dre-rotary-hammer")],
    )
    def test_a_value_another_model_holds_is_refused_naming_it(
        self, field: str, value: str
    ) -> None:
        store, category, _ = stocked()
        use_case = CreateModelUseCase(
            MemoryCatalogueUnitOfWork(store), FixedClock(), MemoryAdminCatalogue(store)
        )
        terms = model_terms(category.id, sku="PU-HONDA-WB20", slug="honda-wb20-pump")
        with pytest.raises(ValidationFailure) as error:
            use_case.execute(
                NewModelCommand(actor=ADMINISTRATOR, terms=replace(terms, **{field: value}))
            )
        assert refused_field(error) == field

    def test_a_sku_taken_in_a_race_is_refused_naming_it(self) -> None:
        store, category, _ = stocked()
        store.race_on = "sku"
        with pytest.raises(ValidationFailure) as error:
            create(store, category)
        assert (refused_field(error), error.value.message) == (
            "sku",
            "Another model already has this SKU.",
        )
        assert store.journal == []

    def test_a_model_the_read_cannot_find_after_the_commit_is_a_fault(self) -> None:
        store, category, _ = stocked()
        store.forget_answers = True
        with pytest.raises(LookupError):
            create(store, category)


class TestEditingAModel:
    """An edit changes what it names and records the figures before and after."""

    def test_a_rate_change_records_the_rate_before_and_after(self) -> None:
        store, _, entry = stocked()
        answered = edit(store, entry, daily_rate=DAILY_AFTER)
        assert answered.daily_rate == DAILY_AFTER
        (event,) = store.events
        assert (event.action, event.before_state, event.after_state) == (
            MODEL_UPDATED_ACTION,
            {"daily_rate": "280.00"},
            {"daily_rate": "310.00"},
        )

    def test_the_sku_is_kept_whatever_else_changes(self) -> None:
        store, _, entry = stocked()
        answered = edit(store, entry, name="Rotary hammer", long_description=None)
        assert (answered.sku, answered.name) == ("DR-BOSCH-GBH226", "Rotary hammer")

    def test_an_edit_that_changes_nothing_writes_nothing(self) -> None:
        store, _, entry = stocked()
        edit(store, entry, daily_rate=Decimal("280"))
        assert (store.journal, store.events) == ([], [])

    def test_a_model_nobody_can_find_is_not_found(self) -> None:
        store, category, _ = stocked()
        with pytest.raises(NotFound):
            edit(store, an_entry(category.id), name="Hammer")

    def test_a_move_to_an_active_category_is_kept(self) -> None:
        store, _, entry = stocked()
        other = a_category(code="BREAK", slug="breaking")
        store.keep(other)
        assert edit(store, entry, category_id=other.id).category_id == other.id

    def test_a_move_to_a_category_that_was_switched_off_is_refused(self) -> None:
        store, _, entry = stocked()
        off = a_category(code="OFF", slug="off", is_active=False)
        store.keep(off)
        with pytest.raises(ValidationFailure) as error:
            edit(store, entry, category_id=off.id)
        assert refused_field(error) == "categoryId"

    def test_a_slug_another_model_holds_is_refused_naming_it(self) -> None:
        store, category, entry = stocked()
        store.keep(an_entry(category.id, sku="PU-HONDA-WB20", slug="honda-wb20-pump"))
        with pytest.raises(ValidationFailure) as error:
            edit(store, entry, slug="honda-wb20-pump")
        assert refused_field(error) == "slug"

    def test_a_slug_taken_in_a_race_is_refused_naming_it(self) -> None:
        store, _, entry = stocked()
        store.race_on = "slug"
        with pytest.raises(ValidationFailure) as error:
            edit(store, entry, slug="rotary-hammer")
        assert refused_field(error) == "slug"
        assert store.events == []

    def test_a_shortest_hire_longer_than_the_longest_is_refused_naming_it(self) -> None:
        store, _, entry = stocked()
        with pytest.raises(ValidationFailure) as error:
            edit(store, entry, min_hire_days=10, max_hire_days=5)
        assert refused_field(error) == "minHireDays"

    def test_an_edit_may_publish_and_records_it_among_the_fields(self) -> None:
        store, category, _ = stocked()
        hidden = an_entry(category.id, published=False, sku="PU-X", slug="pu-x")
        store.keep(hidden)
        assert edit(store, hidden, is_published=True).is_published is True
        (event,) = store.events
        assert (event.before_state, event.after_state) == (
            {"is_published": False},
            {"is_published": True},
        )


class TestPublishingAModel:
    """A model is published or hidden with its event, and asking again changes nothing."""

    def test_a_published_model_is_hidden_with_its_event(self) -> None:
        store, _, entry = stocked()
        answered = publish(store, entry.id, False)
        assert answered.is_published is False
        (event,) = store.events
        assert (event.action, event.before_state, event.after_state) == (
            MODEL_UNPUBLISHED_ACTION,
            {"is_published": True},
            {"is_published": False},
        )

    def test_a_hidden_model_is_published_with_its_event(self) -> None:
        store, category, _ = stocked()
        hidden = an_entry(category.id, published=False, sku="PU-X", slug="pu-x")
        store.keep(hidden)
        assert publish(store, hidden.id, True).is_published is True
        assert [event.action for event in store.events] == [MODEL_PUBLISHED_ACTION]
        assert store.journal == [COMMIT]

    def test_publishing_a_published_model_changes_nothing(self) -> None:
        store, _, entry = stocked()
        assert publish(store, entry.id, True).is_published is True
        assert (store.journal, store.events) == ([], [])

    def test_a_model_nobody_can_find_is_not_found(self) -> None:
        with pytest.raises(NotFound):
            publish(CatalogueStore(), uuid4(), True)
