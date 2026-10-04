"""Which field of the catalogue a unique constraint guards, read from the driver.

A code, a SKU and a slug are unique, and the use cases check that before they
write. Two administrators can still pass the check at once, and then the
constraint refuses the second row. The violation is recognised by SQLSTATE
`23505` together with the name of the constraint, both read from the
diagnostics of the driver and never from its message, which is the way the
account repository recognises a second registration for one address.

`flushed` writes what a repository added or changed and turns such a refusal
into `DuplicateCatalogueValue` naming the field. Any other fault of integrity
is logged and raised unchanged.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Final

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.application.catalogue.admin_ports import DuplicateCatalogueValue
from app.domain import catalogue_entry_rules as model_fields
from app.domain import category_rules as category_fields
from app.infrastructure.schema_ddl import (
    CATEGORY_CODE_CONSTRAINT_NAME,
    CATEGORY_SLUG_CONSTRAINT_NAME,
    PRODUCT_MODEL_SKU_CONSTRAINT_NAME,
    PRODUCT_MODEL_SLUG_CONSTRAINT_NAME,
)

logger = logging.getLogger(__name__)

# PostgreSQL unique_violation.
UNIQUE_VIOLATION_SQLSTATE: Final[str] = "23505"

# The field each unique constraint of the catalogue guards.
CATEGORY_UNIQUES: Final[Mapping[str, str]] = {
    CATEGORY_CODE_CONSTRAINT_NAME: category_fields.CODE,
    CATEGORY_SLUG_CONSTRAINT_NAME: category_fields.SLUG,
}
MODEL_UNIQUES: Final[Mapping[str, str]] = {
    PRODUCT_MODEL_SKU_CONSTRAINT_NAME: model_fields.SKU,
    PRODUCT_MODEL_SLUG_CONSTRAINT_NAME: model_fields.SLUG,
}


def flushed(session: Session, uniques: Mapping[str, str], attempted: str) -> None:
    """Write what the session holds, naming the field a unique constraint refused.

    Args:
        session: The session of the unit of work.
        uniques: The field each unique constraint of the table guards.
        attempted: What was being written, for the log.

    Raises:
        DuplicateCatalogueValue: If one of those constraints refused the row.
        IntegrityError: Unchanged, for every other fault of integrity.

    """
    try:
        session.flush()
    except IntegrityError as error:
        field = _guarded_field(error, uniques)
        if field is not None:
            raise DuplicateCatalogueValue(field) from error
        logger.error(
            "catalogue.write_failed",
            extra={"sqlstate": _sqlstate_of(error), "attempted": attempted},
        )
        raise


def _guarded_field(error: IntegrityError, uniques: Mapping[str, str]) -> str | None:
    """Return the field whose unique constraint refused a row, or None for any other fault."""
    if _sqlstate_of(error) != UNIQUE_VIOLATION_SQLSTATE:
        return None
    diagnostics = getattr(error.orig, "diag", None)
    constraint = getattr(diagnostics, "constraint_name", None) if diagnostics is not None else None
    return uniques.get(constraint) if isinstance(constraint, str) else None


def _sqlstate_of(error: IntegrityError) -> str | None:
    """Return the five character SQLSTATE the driver reported, if any."""
    state = getattr(error.orig, "sqlstate", None)
    return str(state) if state is not None else None
