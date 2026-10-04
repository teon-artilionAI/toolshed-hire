"""The use cases by which an administrator creates and edits a category (FR-22, BR-44).

A category is created active, at the top or under a top level category, and
an edit changes the fields it names. Both hold the terms to the rules of
`app.domain.category_rules`, look the chosen parent up and hold it to the cap
of two levels, and check that no other category holds the code or the slug
before the row is written. The unique constraints have the last word, and a
race lost to one of them is answered as the check would have answered it.

The change and its audit event, `category.created` or `category.updated`,
commit in one unit of work (BR-49). An edit that changes nothing writes
nothing. The answer is the category as the administrator's list shows it,
read once the transaction has committed.

Nothing is ever deleted (BR-51). A category leaves the catalogue by being
switched off, which is an edit of `is_active`.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Final
from uuid import UUID, uuid4

from app.application.catalogue.admin_commands import EditCategoryCommand, NewCategoryCommand
from app.application.catalogue.admin_ports import AdminCatalogueQuery, DuplicateCatalogueValue
from app.application.catalogue.admin_read_models import AdminCategoryEntry
from app.application.catalogue.catalogue_changes import (
    category_state,
    changed_fields,
    checked,
    ensure_untaken,
    record_change,
    refused_duplicate,
)
from app.application.clock import Clock
from app.application.identity.account_rules import refused_field, wire_name
from app.application.refusal import refused
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.category_rules import (
    CODE,
    PARENT_CATEGORY_ID,
    SLUG,
    CatalogueCategory,
    CategoryTerms,
    checked_category_terms,
    ensure_parent_may_hold,
)
from app.domain.errors import NotFound, ValidationFailure

logger = logging.getLogger(__name__)

CATEGORY_ENTITY_TYPE: Final[str] = "category"
CATEGORY_CREATED_ACTION: Final[str] = "category.created"
CATEGORY_UPDATED_ACTION: Final[str] = "category.updated"
CATEGORY_NOT_FOUND_MESSAGE: Final[str] = "We could not find that category."
UNKNOWN_PARENT_MESSAGE: Final[str] = "Choose a category from the list."
# Checked in this order, so a request that repeats both is told about the code.
TAKEN_MESSAGES: Final[dict[str, str]] = {
    CODE: "Another category already has this code.",
    SLUG: "Another category already has this slug.",
}


class _CategoryUseCase[CommandT](UseCase[CommandT, AdminCategoryEntry]):
    """What creating and editing a category share, the reads and the checks."""

    def __init__(self, uow: UnitOfWork, clock: Clock, catalogue: AdminCatalogueQuery) -> None:
        """Keep the unit of work, the clock and the read the answer comes from."""
        super().__init__(uow, clock)
        self._catalogue = catalogue

    def _answer(self, category_id: UUID) -> AdminCategoryEntry:
        """Return the category as the list shows it, read after the commit.

        Raises:
            LookupError: If the category cannot be read back, which would
                mean the commit did not keep what it was handed.

        """
        entry = self._catalogue.category(category_id)
        if entry is None:
            raise LookupError(
                f"Attempted to read back category {category_id} after writing it, and it could "
                "not be read."
            )
        return entry


class CreateCategoryUseCase(_CategoryUseCase[NewCategoryCommand]):
    """Create a category, active, with its audit event."""

    def execute(self, command: NewCategoryCommand) -> AdminCategoryEntry:
        """Create the category, or refuse and write nothing.

        Raises:
            ValidationFailure: Naming the field, for a field that breaks a
                rule, a parent that is unknown or too deep, or a code or slug
                already taken.

        """
        logger.info(
            "catalogue.category_create_requested",
            extra={"actor_user_id": str(command.actor.user_id), "code": command.code},
        )
        now = self._clock.now()
        with self._uow as uow:
            terms = checked(
                checked_category_terms,
                CategoryTerms(
                    code=command.code,
                    name=command.name,
                    slug=command.slug,
                    description=command.description,
                    parent_category_id=command.parent_category_id,
                    sort_order=command.sort_order,
                    is_active=True,
                ),
            )
            if terms.parent_category_id is not None:
                _ensure_parent(uow, None, terms.parent_category_id, has_children=False)
            ensure_untaken(
                uow.categories.taken_fields(code=terms.code, slug=terms.slug, other_than=None),
                TAKEN_MESSAGES,
            )
            category = CatalogueCategory(id=uuid4(), terms=terms)
            try:
                uow.categories.add(category, now)
            except DuplicateCatalogueValue as duplicate:
                raise refused_duplicate(duplicate, TAKEN_MESSAGES) from duplicate
            record_change(
                uow,
                actor=command.actor,
                entity_type=CATEGORY_ENTITY_TYPE,
                entity_id=category.id,
                action=CATEGORY_CREATED_ACTION,
                now=now,
                before=None,
                after=category_state(terms),
            )
            uow.commit()
        logger.info(
            "catalogue.category_created",
            extra={"category_id": str(category.id), "code": terms.code},
        )
        return self._answer(category.id)


class EditCategoryUseCase(_CategoryUseCase[EditCategoryCommand]):
    """Change the fields of a category an edit names, with its audit event."""

    def execute(self, command: EditCategoryCommand) -> AdminCategoryEntry:
        """Change the category, or refuse and write nothing.

        Raises:
            NotFound: If there is no such category.
            ValidationFailure: Naming the field, as for a creation.

        """
        logger.info(
            "catalogue.category_edit_requested",
            extra={
                "actor_user_id": str(command.actor.user_id),
                "category_id": str(command.category_id),
            },
        )
        now = self._clock.now()
        with self._uow as uow:
            stored = uow.categories.get_for_update(command.category_id)
            if stored is None:
                logger.info(
                    "catalogue.category_not_found",
                    extra={"category_id": str(command.category_id)},
                )
                raise NotFound(CATEGORY_NOT_FOUND_MESSAGE, {"category": str(command.category_id)})
            terms = checked(checked_category_terms, command.changes.applied_to(stored.terms))
            before, after = changed_fields(category_state(stored.terms), category_state(terms))
            if not after:
                logger.info(
                    "catalogue.category_unchanged", extra={"category_id": str(stored.id)}
                )
                return self._answer(stored.id)
            parent_id = terms.parent_category_id
            if parent_id is not None and parent_id != stored.terms.parent_category_id:
                _ensure_parent(
                    uow, stored.id, parent_id, has_children=uow.categories.has_children(stored.id)
                )
            ensure_untaken(
                uow.categories.taken_fields(
                    code=terms.code if terms.code != stored.terms.code else None,
                    slug=terms.slug if terms.slug != stored.terms.slug else None,
                    other_than=stored.id,
                ),
                TAKEN_MESSAGES,
            )
            try:
                uow.categories.save(replace(stored, terms=terms), now)
            except DuplicateCatalogueValue as duplicate:
                raise refused_duplicate(duplicate, TAKEN_MESSAGES) from duplicate
            record_change(
                uow,
                actor=command.actor,
                entity_type=CATEGORY_ENTITY_TYPE,
                entity_id=stored.id,
                action=CATEGORY_UPDATED_ACTION,
                now=now,
                before=before,
                after=after,
            )
            uow.commit()
        logger.info(
            "catalogue.category_edited",
            extra={"category_id": str(stored.id), "changed": sorted(after)},
        )
        return self._answer(stored.id)


def _ensure_parent(
    uow: UnitOfWork, category_id: UUID | None, parent_id: UUID, *, has_children: bool
) -> None:
    """Refuse a parent that does not exist or that would nest categories too deep.

    Raises:
        ValidationFailure: Naming `parentCategoryId`.

    """
    parent = uow.categories.get(parent_id)
    if parent is None:
        logger.info("catalogue.parent_not_found", extra={"parent_category_id": str(parent_id)})
        raise refused(wire_name(PARENT_CATEGORY_ID), UNKNOWN_PARENT_MESSAGE)
    try:
        ensure_parent_may_hold(category_id, parent, has_children=has_children)
    except ValidationFailure as failure:
        raise refused_field(failure) from failure
