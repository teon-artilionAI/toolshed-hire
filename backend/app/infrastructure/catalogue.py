"""The SQL repository of the catalogue module, for product models.

Read only here. It maps the SQLModel table class to the domain entity, which
carries the prices a reservation line snapshots (BR-20) and the hire limits a
booking is held to (BR-03).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlmodel import Session, col, select

from app.domain import catalogue as domain
from app.infrastructure.models import ProductModel

logger = logging.getLogger(__name__)


class SqlProductModelRepository:
    """Reads catalogue entries through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to the session of its unit of work."""
        self._session = session

    def get(self, product_model_id: UUID) -> domain.ProductModel | None:
        """Return the product model with this key, or None when there is none."""
        logger.debug(
            "catalogue.product_model_lookup_started",
            extra={"product_model_id": str(product_model_id)},
        )
        row = self._session.get(ProductModel, product_model_id)
        logger.debug(
            "catalogue.product_model_lookup_finished",
            extra={"product_model_id": str(product_model_id), "found": row is not None},
        )
        return _product_model_of(row) if row is not None else None

    def find_published_by_slug(self, slug: str) -> domain.ProductModel | None:
        """Return the published product model with this slug, or None when there is none."""
        statement = select(ProductModel).where(
            col(ProductModel.slug) == slug, col(ProductModel.is_published)
        )
        row = self._session.exec(statement).first()
        logger.debug(
            "catalogue.product_model_slug_lookup_finished",
            extra={"slug": slug, "found": row is not None},
        )
        return _product_model_of(row) if row is not None else None

    def names_of(self, product_model_ids: Sequence[UUID]) -> dict[UUID, str]:
        """Return the display name of each product model asked for, by its key, in one read."""
        statement = select(col(ProductModel.id), col(ProductModel.name)).where(
            col(ProductModel.id).in_(list(product_model_ids))
        )
        names = dict(self._session.exec(statement).all())
        logger.debug(
            "catalogue.product_model_names_read",
            extra={"requested_count": len(product_model_ids), "found_count": len(names)},
        )
        return names


def _product_model_of(row: ProductModel) -> domain.ProductModel:
    """Return the domain entity for a product model row."""
    # Decimal() on each price. The driver already returns Decimal for a
    # NUMERIC column, and wrapping keeps that true whatever it returns,
    # because money is never a float (BR-22).
    return domain.ProductModel(
        id=row.id,
        sku=row.sku,
        name=row.name,
        slug=row.slug,
        daily_rate=Decimal(row.daily_rate),
        weekly_rate=Decimal(row.weekly_rate),
        deposit_amount=Decimal(row.deposit_amount),
        late_fee_per_day=Decimal(row.late_fee_per_day),
        replacement_value=Decimal(row.replacement_value),
        min_hire_days=row.min_hire_days,
        max_hire_days=row.max_hire_days,
    )
