"""The catalogue as the administrator reads it (FR-22, BR-44).

The administrator lists every category, switched off or not, each parent
followed by its children, and lists the product models, published or not,
with how many units of each the fleet holds. Nothing here writes, so there is
no unit of work and no audit event. The reads go through the
`AdminCatalogueQuery` port, and the one rule that is not SQL lives here, that a
model nobody can find is a 404.

The search text is logged by its length only, as every search is.
"""

from __future__ import annotations

import logging
from typing import Final
from uuid import UUID

from app.application.catalogue.admin_ports import AdminCatalogueQuery
from app.application.catalogue.admin_read_models import (
    AdminCategoryPage,
    AdminCategorySearch,
    AdminModelEntry,
    AdminModelPage,
    AdminModelSearch,
)
from app.application.catalogue.manage_models import MODEL_NOT_FOUND_MESSAGE
from app.domain.errors import NotFound
from app.domain.identity import Actor

logger = logging.getLogger(__name__)

NO_TEXT: Final[int] = 0


class ReadAdminCatalogue:
    """Reads the catalogue for an administrator."""

    def __init__(self, catalogue: AdminCatalogueQuery) -> None:
        """Keep the query object the catalogue is read through."""
        self._catalogue = catalogue

    def categories(self, actor: Actor, search: AdminCategorySearch) -> AdminCategoryPage:
        """Return one page of every category, each parent followed by its children."""
        logger.info(
            "catalogue.admin_categories_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "page": search.page,
                "page_size": search.page_size,
            },
        )
        found = self._catalogue.category_page(search)
        logger.info(
            "catalogue.admin_categories_read",
            extra={"row_count": len(found.items), "total": found.total},
        )
        return found

    def models(self, actor: Actor, search: AdminModelSearch) -> AdminModelPage:
        """Return one page of the product models that match, published or not."""
        logger.info(
            "catalogue.admin_models_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "q_length": len(search.text) if search.text is not None else NO_TEXT,
                "category_id": str(search.category_id) if search.category_id else None,
                "published": search.published,
                "page": search.page,
                "page_size": search.page_size,
            },
        )
        found = self._catalogue.model_page(search)
        logger.info(
            "catalogue.admin_models_read",
            extra={"row_count": len(found.items), "total": found.total, "page": found.page},
        )
        return found

    def model(self, actor: Actor, model_id: UUID) -> AdminModelEntry:
        """Return one product model, published or not.

        Raises:
            NotFound: If there is no such model.

        """
        logger.info(
            "catalogue.admin_model_requested",
            extra={"actor_user_id": str(actor.user_id), "model_id": str(model_id)},
        )
        found = self._catalogue.model(model_id)
        if found is None:
            logger.info("catalogue.model_not_found", extra={"model_id": str(model_id)})
            raise NotFound(MODEL_NOT_FOUND_MESSAGE, {"model": str(model_id)})
        return found
