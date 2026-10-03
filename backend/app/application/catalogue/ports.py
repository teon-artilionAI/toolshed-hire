"""The catalogue ports, one for a booking and one for a visitor.

A reservation line snapshots the prices of the product model it hires (BR-20),
so the booking flow has to read the catalogue entry. The catalogue module owns
that table, and `ProductModelRepository` is how another module reads it.

`CatalogueQuery` is the read side. It answers what a visitor with no account
asks of the catalogue, and it returns the small read models of this package
and never a table row. The infrastructure layer implements it as a query
object.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from app.application.catalogue.read_models import (
    CategoryEntry,
    ModelDetail,
    ModelPage,
    ModelSearch,
)
from app.domain.catalogue import ProductModel


class ProductModelRepository(Protocol):
    """Read access to catalogue entries."""

    def get(self, product_model_id: UUID) -> ProductModel | None:
        """Return the product model with this key, or None when there is none."""
        ...

    def find_published_by_slug(self, slug: str) -> ProductModel | None:
        """Return the published product model with this slug, or None when there is none.

        A model that exists and is not published is answered with None, so a
        draft cannot be booked and cannot be told apart from a slug nobody
        ever used.
        """
        ...

    def names_of(self, product_model_ids: Sequence[UUID]) -> dict[UUID, str]:
        """Return the display name of each product model asked for, by its key, in one read."""
        ...


class CatalogueQuery(Protocol):
    """What a visitor may read of the catalogue."""

    def list_categories(self) -> list[CategoryEntry]:
        """Return every active category, each parent followed by its children.

        Top level categories are ordered by sort order and then by name, and so
        are the children under each of them.
        """
        ...

    def category_exists(self, slug: str) -> bool:
        """Return True when an active category carries this slug."""
        ...

    def search_models(self, search: ModelSearch) -> ModelPage:
        """Return one page of the published models that match a search."""
        ...

    def find_model(self, slug: str) -> ModelDetail | None:
        """Return the published model with this slug, or None when there is none.

        A model that exists and is not published is answered with None, so a
        draft cannot be told apart from a slug nobody ever used.
        """
        ...
