"""The use case by which an administrator publishes a product model or hides it (FR-22, US-30).

A published model is in the public catalogue, in the availability search and
in a quote, and a visitor or the counter may book it. An unpublished one is in
none of them from the moment the change commits, because each of those reads
asks for published models only. Hiding a model leaves every existing booking
of it alone. A reservation already made carries its own copy of the figures,
can still be held, confirmed and checked out, and its rental runs as it would.

The change and its audit event, `product_model.published` or
`product_model.unpublished`, commit in one unit of work (BR-49). Asking for
the state a model is already in changes nothing and writes nothing, and the
model is answered as it stands.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Final

from app.application.catalogue.admin_commands import PublicationCommand
from app.application.catalogue.admin_read_models import AdminModelEntry
from app.application.catalogue.catalogue_changes import record_change
from app.application.catalogue.manage_models import MODEL_ENTITY_TYPE, ModelUseCase, locked_model
from app.domain.catalogue_entry_rules import IS_PUBLISHED

logger = logging.getLogger(__name__)

MODEL_PUBLISHED_ACTION: Final[str] = "product_model.published"
MODEL_UNPUBLISHED_ACTION: Final[str] = "product_model.unpublished"


class PublishModelUseCase(ModelUseCase[PublicationCommand]):
    """Publish a product model or take it out of the public catalogue."""

    def execute(self, command: PublicationCommand) -> AdminModelEntry:
        """Publish or hide the model, or change nothing when it already is.

        Raises:
            NotFound: If there is no such model.

        """
        logger.info(
            "catalogue.publication_requested",
            extra={
                "actor_user_id": str(command.actor.user_id),
                "model_id": str(command.model_id),
                "published": command.published,
            },
        )
        now = self._clock.now()
        with self._uow as uow:
            stored = locked_model(uow, command.model_id)
            if stored.is_published is command.published:
                logger.info(
                    "catalogue.publication_unchanged",
                    extra={"model_id": str(stored.id), "published": stored.is_published},
                )
                return self._answer(stored.id)
            uow.catalogue_entries.save(replace(stored, is_published=command.published), now)
            record_change(
                uow,
                actor=command.actor,
                entity_type=MODEL_ENTITY_TYPE,
                entity_id=stored.id,
                action=MODEL_PUBLISHED_ACTION if command.published else MODEL_UNPUBLISHED_ACTION,
                now=now,
                before={IS_PUBLISHED: stored.is_published},
                after={IS_PUBLISHED: command.published},
            )
            uow.commit()
        logger.info(
            "catalogue.publication_changed",
            extra={
                "model_id": str(stored.id),
                "sku": stored.terms.sku,
                "published": command.published,
            },
        )
        return self._answer(stored.id)
