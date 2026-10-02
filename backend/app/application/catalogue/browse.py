"""Browsing the catalogue, which is FR-02.

A visitor with no account lists the categories, lists the published models and
opens one model. Nothing here writes, so there is no unit of work and no audit
event. The reads go through the `CatalogueQuery` port, and the two rules that
are not SQL live here.

1. A search that names a category nobody can find is refused and says which
   parameter was wrong. Answering it with an empty page would look like a
   category with nothing in it.
2. A model that does not exist and a model that is not published are the same
   answer, `NotFound`.
"""

from __future__ import annotations

import logging
from typing import Final

from app.application.catalogue.ports import CatalogueQuery
from app.application.catalogue.read_models import (
    CategoryEntry,
    ModelDetail,
    ModelPage,
    ModelSearch,
)
from app.application.refusal import refused
from app.domain.errors import NotFound

logger = logging.getLogger(__name__)

# The name of the parameter a search carries its category in.
CATEGORY_PARAMETER: Final[str] = "category"


def ensure_category_exists(catalogue: CatalogueQuery, slug: str | None) -> None:
    """Refuse a search that names a category no visitor can see.

    Args:
        catalogue: The catalogue read port.
        slug: The category slug of the search, or None when it names none.

    Raises:
        ValidationFailure: If the slug names no active category. The failure
            names the category parameter.

    """
    if slug is None or catalogue.category_exists(slug):
        return
    logger.info("catalogue.unknown_category_refused", extra={"category": slug})
    raise refused(
        CATEGORY_PARAMETER,
        f"Attempted to search category {slug!r}, which is not a category of this catalogue.",
        {"category": slug},
    )


class BrowseCatalogue:
    """The catalogue as a visitor reads it."""

    def __init__(self, catalogue: CatalogueQuery) -> None:
        """Keep the port the catalogue is read through."""
        self._catalogue = catalogue

    def categories(self) -> list[CategoryEntry]:
        """Return every active category, each parent followed by its children."""
        return self._catalogue.list_categories()

    def models(self, search: ModelSearch) -> ModelPage:
        """Return one page of the published models that match a search.

        Raises:
            ValidationFailure: If the search names an unknown category.

        """
        ensure_category_exists(self._catalogue, search.category_slug)
        return self._catalogue.search_models(search)

    def model(self, slug: str) -> ModelDetail:
        """Return the published model with this slug.

        Raises:
            NotFound: If no published model carries the slug.

        """
        found = self._catalogue.find_model(slug)
        if found is None:
            logger.info("catalogue.model_not_found", extra={"slug": slug})
            raise NotFound(
                f"Attempted to open catalogue model {slug!r}, which does not exist.",
                {"slug": slug},
            )
        return found
