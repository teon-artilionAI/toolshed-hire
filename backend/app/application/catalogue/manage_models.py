"""The use cases by which an administrator creates and edits a product model (FR-22, US-30).

A rate, a deposit, a late fee and a replacement value are set here once for
all three branches. A new model starts unpublished, so a visitor never sees a
model before the administrator has finished it. An edit changes the fields it
names and never the SKU. It may name publication too, which it records among
the fields it changed.

Both hold the terms to the rules of `app.domain.catalogue_entry_rules`, look
the category up and refuse one that has been switched off, and check that no
other model holds the SKU or the slug before the row is written. The unique
constraints have the last word, and a race lost to one of them is answered as
the check would have answered it.

A change of a rate never touches an existing reservation line or rental,
because each of them copied the figures when it was made (BR-20). Nothing here
reads or writes either of them. The audit event, `product_model.created` or
`product_model.updated`, records the figures before and after and commits with
the change (BR-49). An edit that changes nothing writes nothing.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Final
from uuid import UUID, uuid4

from app.application.catalogue.admin_commands import EditModelCommand, NewModelCommand, chosen
from app.application.catalogue.admin_ports import AdminCatalogueQuery, DuplicateCatalogueValue
from app.application.catalogue.admin_read_models import AdminModelEntry
from app.application.catalogue.catalogue_changes import (
    changed_fields,
    checked,
    ensure_untaken,
    model_state,
    record_change,
    refused_duplicate,
)
from app.application.clock import Clock
from app.application.identity.account_rules import refused_field, wire_name
from app.application.refusal import refused
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.catalogue_entry_rules import (
    CATEGORY_ID,
    IS_PUBLISHED,
    SKU,
    SLUG,
    CatalogueEntry,
    checked_model_terms,
    ensure_category_may_classify,
)
from app.domain.errors import NotFound, ValidationFailure

logger = logging.getLogger(__name__)

MODEL_ENTITY_TYPE: Final[str] = "product_model"
MODEL_CREATED_ACTION: Final[str] = "product_model.created"
MODEL_UPDATED_ACTION: Final[str] = "product_model.updated"
MODEL_NOT_FOUND_MESSAGE: Final[str] = "We could not find that model."
UNKNOWN_CATEGORY_MESSAGE: Final[str] = "Choose a category from the list."
# Checked in this order, so a request that repeats both is told about the SKU.
TAKEN_MESSAGES: Final[dict[str, str]] = {
    SKU: "Another model already has this SKU.",
    SLUG: "Another model already has this slug.",
}


class ModelUseCase[CommandT](UseCase[CommandT, AdminModelEntry]):
    """What every use case of a product model shares, the lookup and the answer."""

    def __init__(self, uow: UnitOfWork, clock: Clock, catalogue: AdminCatalogueQuery) -> None:
        """Keep the unit of work, the clock and the read the answer comes from."""
        super().__init__(uow, clock)
        self._catalogue = catalogue

    def _answer(self, model_id: UUID) -> AdminModelEntry:
        """Return the model as the list shows it, read after the commit.

        Raises:
            LookupError: If the model cannot be read back, which would mean
                the commit did not keep what it was handed.

        """
        entry = self._catalogue.model(model_id)
        if entry is None:
            raise LookupError(
                f"Attempted to read back product model {model_id} after writing it, and it "
                "could not be read."
            )
        return entry


def locked_model(uow: UnitOfWork, model_id: UUID) -> CatalogueEntry:
    """Return the product model with this key, locked for the rest of the transaction.

    Raises:
        NotFound: If there is no such model.

    """
    stored = uow.catalogue_entries.get_for_update(model_id)
    if stored is None:
        logger.info("catalogue.model_not_found", extra={"model_id": str(model_id)})
        raise NotFound(MODEL_NOT_FOUND_MESSAGE, {"model": str(model_id)})
    return stored


class CreateModelUseCase(ModelUseCase[NewModelCommand]):
    """Create a product model, unpublished, with its audit event."""

    def execute(self, command: NewModelCommand) -> AdminModelEntry:
        """Create the model, or refuse and write nothing.

        Raises:
            ValidationFailure: Naming the field, for a field that breaks a
                rule, a category that is unknown or switched off, or a SKU or
                slug already taken.

        """
        logger.info(
            "catalogue.model_create_requested",
            extra={"actor_user_id": str(command.actor.user_id), "sku": command.terms.sku},
        )
        now = self._clock.now()
        with self._uow as uow:
            terms = checked(checked_model_terms, command.terms)
            _ensure_category(uow, terms.category_id)
            taken = uow.catalogue_entries.taken_fields(
                sku=terms.sku, slug=terms.slug, other_than=None
            )
            ensure_untaken(taken, TAKEN_MESSAGES)
            entry = CatalogueEntry(id=uuid4(), terms=terms, is_published=False)
            try:
                uow.catalogue_entries.add(entry, now)
            except DuplicateCatalogueValue as duplicate:
                raise refused_duplicate(duplicate, TAKEN_MESSAGES) from duplicate
            record_change(
                uow,
                actor=command.actor,
                entity_type=MODEL_ENTITY_TYPE,
                entity_id=entry.id,
                action=MODEL_CREATED_ACTION,
                now=now,
                before=None,
                after={**model_state(terms), IS_PUBLISHED: entry.is_published},
            )
            uow.commit()
        logger.info("catalogue.model_created", extra={"model_id": str(entry.id), "sku": terms.sku})
        return self._answer(entry.id)


class EditModelUseCase(ModelUseCase[EditModelCommand]):
    """Change the fields of a product model an edit names, with its audit event."""

    def execute(self, command: EditModelCommand) -> AdminModelEntry:
        """Change the model, or refuse and write nothing.

        Raises:
            NotFound: If there is no such model.
            ValidationFailure: Naming the field, as for a creation.

        """
        logger.info(
            "catalogue.model_edit_requested",
            extra={"actor_user_id": str(command.actor.user_id), "model_id": str(command.model_id)},
        )
        now = self._clock.now()
        with self._uow as uow:
            stored = locked_model(uow, command.model_id)
            terms = checked(checked_model_terms, command.changes.applied_to(stored.terms))
            published = chosen(stored.is_published, command.changes.is_published)
            before, after = changed_fields(
                {**model_state(stored.terms), IS_PUBLISHED: stored.is_published},
                {**model_state(terms), IS_PUBLISHED: published},
            )
            if not after:
                logger.info("catalogue.model_unchanged", extra={"model_id": str(stored.id)})
                return self._answer(stored.id)
            if terms.category_id != stored.terms.category_id:
                _ensure_category(uow, terms.category_id)
            if terms.slug != stored.terms.slug:
                ensure_untaken(
                    uow.catalogue_entries.taken_fields(
                        sku=None, slug=terms.slug, other_than=stored.id
                    ),
                    TAKEN_MESSAGES,
                )
            try:
                uow.catalogue_entries.save(
                    replace(stored, terms=terms, is_published=published), now
                )
            except DuplicateCatalogueValue as duplicate:
                raise refused_duplicate(duplicate, TAKEN_MESSAGES) from duplicate
            record_change(
                uow,
                actor=command.actor,
                entity_type=MODEL_ENTITY_TYPE,
                entity_id=stored.id,
                action=MODEL_UPDATED_ACTION,
                now=now,
                before=before,
                after=after,
            )
            uow.commit()
        logger.info(
            "catalogue.model_edited",
            extra={"model_id": str(stored.id), "sku": stored.terms.sku, "changed": sorted(after)},
        )
        return self._answer(stored.id)


def _ensure_category(uow: UnitOfWork, category_id: UUID) -> None:
    """Refuse a category that does not exist or that has been switched off.

    Raises:
        ValidationFailure: Naming `categoryId`.

    """
    category = uow.categories.get(category_id)
    if category is None:
        logger.info("catalogue.category_not_found", extra={"category_id": str(category_id)})
        raise refused(wire_name(CATEGORY_ID), UNKNOWN_CATEGORY_MESSAGE)
    try:
        ensure_category_may_classify(category)
    except ValidationFailure as failure:
        raise refused_field(failure) from failure
