"""The SQL repository of the product models the administrator writes (FR-22, US-30).

It maps the `product_model` rows to the domain's `CatalogueEntry` and back, on
the session of the unit of work that created it. A model about to change is
read with `SELECT ... FOR UPDATE`, so two administrators changing one rate
take turns and the second reads the rate the first committed.

Nothing here touches `reservation_line` or `rental`. A booking copied the
figures it was priced at when it was made (BR-20), so a rate written here
reaches the next booking and no other.

Every statement stands on a key. A model is read by its primary key, and a SKU
and a slug are looked up through their unique indexes in one statement. A
unique constraint that refuses a row is named by
`app/infrastructure/catalogue_uniques.py`. Every instant written comes from
the clock the use case was handed.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ColumnElement, or_
from sqlmodel import Session, col, select

from app.domain import catalogue_entry_rules as fields
from app.domain.catalogue_entry_rules import CatalogueEntry, ModelTerms
from app.infrastructure.catalogue_uniques import MODEL_UNIQUES, flushed
from app.infrastructure.models import ProductModel

logger = logging.getLogger(__name__)


class SqlCatalogueEntryRepository:
    """Reads and writes product models through one session."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to the session of its unit of work."""
        self._session = session

    def get_for_update(self, model_id: UUID) -> CatalogueEntry | None:
        """Return the product model with this key, locked until the transaction ends, or None."""
        statement = (
            select(ProductModel)
            .where(col(ProductModel.id) == model_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        row = self._session.exec(statement).first()
        logger.debug(
            "catalogue.model_locked", extra={"model_id": str(model_id), "found": row is not None}
        )
        return _entry_of(row) if row is not None else None

    def taken_fields(
        self, *, sku: str | None, slug: str | None, other_than: UUID | None
    ) -> frozenset[str]:
        """Return which of a SKU and a slug another product model already holds, in one read."""
        wanted: list[ColumnElement[bool]] = []
        if sku is not None:
            wanted.append(col(ProductModel.sku) == sku)
        if slug is not None:
            wanted.append(col(ProductModel.slug) == slug)
        if not wanted:
            return frozenset()
        statement = select(col(ProductModel.sku), col(ProductModel.slug)).where(or_(*wanted))
        if other_than is not None:
            statement = statement.where(col(ProductModel.id) != other_than)
        taken: set[str] = set()
        for held_sku, held_slug in self._session.exec(statement).all():
            if sku is not None and held_sku == sku:
                taken.add(fields.SKU)
            if slug is not None and held_slug == slug:
                taken.add(fields.SLUG)
        logger.debug("catalogue.model_values_checked", extra={"taken": sorted(taken)})
        return frozenset(taken)

    def add(self, entry: CatalogueEntry, now: datetime) -> None:
        """Write a new product model inside the current transaction.

        Raises:
            DuplicateCatalogueValue: If the unique constraint on the SKU or the
                slug refused it.

        """
        row = ProductModel(id=entry.id, sku=entry.terms.sku, created_at=now)
        _copy_entry(row, entry, now)
        self._session.add(row)
        flushed(self._session, MODEL_UNIQUES, "insert a product_model row")
        logger.info(
            "catalogue.model_added", extra={"model_id": str(entry.id), "sku": entry.terms.sku}
        )

    def save(self, entry: CatalogueEntry, now: datetime) -> None:
        """Write a product model this transaction locked back, stamped as changed now.

        The SKU is never written, because it never changes.

        Raises:
            DuplicateCatalogueValue: If the unique constraint on the slug refused it.
            RuntimeError: If the model has no row, which would mean a use case
                is saving a model it never read.

        """
        row = self._session.get(ProductModel, entry.id)
        if row is None:
            raise RuntimeError(
                f"Attempted to save product model {entry.id}, which has no row. Read it with "
                "get_for_update first."
            )
        _copy_entry(row, entry, now)
        self._session.add(row)
        flushed(self._session, MODEL_UNIQUES, "update a product_model row")
        logger.info(
            "catalogue.model_saved",
            extra={
                "model_id": str(entry.id),
                "sku": entry.terms.sku,
                "published": entry.is_published,
            },
        )


def _copy_entry(row: ProductModel, entry: CatalogueEntry, now: datetime) -> None:
    """Copy every field of a model but its SKU onto its row and stamp the row as changed now."""
    terms = entry.terms
    row.name = terms.name
    row.slug = terms.slug
    row.category_id = terms.category_id
    row.manufacturer = terms.manufacturer
    row.model_number = terms.model_number
    row.short_description = terms.short_description
    row.long_description = terms.long_description
    row.daily_rate = terms.daily_rate
    row.weekly_rate = terms.weekly_rate
    row.deposit_amount = terms.deposit_amount
    row.late_fee_per_day = terms.late_fee_per_day
    row.replacement_value = terms.replacement_value
    row.min_hire_days = terms.min_hire_days
    row.max_hire_days = terms.max_hire_days
    row.is_published = entry.is_published
    row.updated_at = now


def _entry_of(row: ProductModel) -> CatalogueEntry:
    """Return the domain entry for a `product_model` row.

    Decimal() on each amount. The driver already returns Decimal for a
    NUMERIC column, and wrapping keeps that true whatever it returns, because
    money is never a float (BR-22).
    """
    return CatalogueEntry(
        id=row.id,
        terms=ModelTerms(
            sku=row.sku,
            name=row.name,
            slug=row.slug,
            category_id=row.category_id,
            manufacturer=row.manufacturer,
            model_number=row.model_number,
            short_description=row.short_description,
            long_description=row.long_description,
            daily_rate=Decimal(row.daily_rate),
            weekly_rate=Decimal(row.weekly_rate),
            deposit_amount=Decimal(row.deposit_amount),
            late_fee_per_day=Decimal(row.late_fee_per_day),
            replacement_value=Decimal(row.replacement_value),
            min_hire_days=row.min_hire_days,
            max_hire_days=row.max_hire_days,
        ),
        is_published=row.is_published,
    )
