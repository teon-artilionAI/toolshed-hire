"""The catalogue port a booking reads through.

A reservation line snapshots the prices of the product model it hires (BR-20),
so the booking flow has to read the catalogue entry. The catalogue module owns
that table, and this port is how another module reads it.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.domain.catalogue import ProductModel


class ProductModelRepository(Protocol):
    """Read access to catalogue entries."""

    def get(self, product_model_id: UUID) -> ProductModel | None:
        """Return the product model with this key, or None when there is none."""
        ...
