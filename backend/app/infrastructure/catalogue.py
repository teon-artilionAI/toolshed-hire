"""The SQL repository of the catalogue module, for product models.

Read only here. It maps the SQLModel table class to the domain entity, which
carries the prices a reservation line snapshots (BR-20).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

from sqlmodel import Session

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
        if row is None:
            return None
        # Decimal() on each price. The driver already returns Decimal for a
        # NUMERIC column, and wrapping keeps that true whatever it returns,
        # because money is never a float (BR-22).
        return domain.ProductModel(
            id=row.id,
            sku=row.sku,
            name=row.name,
            daily_rate=Decimal(row.daily_rate),
            weekly_rate=Decimal(row.weekly_rate),
            deposit_amount=Decimal(row.deposit_amount),
            late_fee_per_day=Decimal(row.late_fee_per_day),
            replacement_value=Decimal(row.replacement_value),
        )
