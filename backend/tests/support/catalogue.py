"""A visitor's client and a few builders for the catalogue and availability tests.

The public read side is asked by somebody with no account, on a day the test
chooses. `visitor_client` gives the real application a session and a clock
that stands still, and takes both away again afterwards. It works on the in
memory database and on PostgreSQL alike, because the only thing that differs
between the two is the session it is handed.

The builders go through the shared factories and then set the few columns a
catalogue test cares about, a rate, a manufacturer, a parent category. That
keeps the factories as they are for every other test.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Final

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.deps import get_clock
from app.domain.enums import ReleaseReason, UserRole
from app.domain.period import BookingPeriod
from app.infrastructure.database import get_session
from app.infrastructure.models import (
    Asset,
    AssetAllocation,
    Branch,
    Category,
    ProductModel,
)
from app.main import app as production_app
from tests.support.clock import FixedClock
from tests.support.factories import Factory

logger = logging.getLogger(__name__)

BRANCHES_PATH: Final[str] = "/api/branches"
CATEGORIES_PATH: Final[str] = "/api/catalogue/categories"
MODELS_PATH: Final[str] = "/api/catalogue/models"
AVAILABILITY_PATH: Final[str] = "/api/catalogue/availability"
VALIDATION_PROBLEM: Final[str] = "request-validation-failure"
RELEASED_AT: Final[datetime] = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)


def model_path(slug: str) -> str:
    """Return the path of one model."""
    return f"{MODELS_PATH}/{slug}"


def model_availability_path(slug: str) -> str:
    """Return the path of the availability of one model."""
    return f"{MODELS_PATH}/{slug}/availability"


@contextmanager
def visitor_client(session: Session, clock: FixedClock | None = None) -> Iterator[TestClient]:
    """Yield a client for the real application, with no credential and a still clock.

    The request session is the one the test holds, and it is rolled back when
    a request ends, as the shared `client` fixture does. A test therefore
    commits its setup before it asks anything.

    Args:
        session: The session every request is served with.
        clock: The clock the application is given. A fixed clock at its
            default instant when omitted, which is the second of March 2026.

    """
    still_clock = clock or FixedClock()

    def _session() -> Iterator[Session]:
        """Hand the request the test's session and discard uncommitted work after."""
        try:
            yield session
        finally:
            session.rollback()

    production_app.dependency_overrides[get_session] = _session
    production_app.dependency_overrides[get_clock] = lambda: still_clock
    try:
        yield TestClient(production_app)
    finally:
        production_app.dependency_overrides.pop(get_session, None)
        production_app.dependency_overrides.pop(get_clock, None)


def refused_fields(body: dict[str, object]) -> dict[str, str]:
    """Return the per field messages of a 422 problem document."""
    errors = body["errors"]
    assert isinstance(errors, dict), f"The problem carries no errors member. Got {body!r}."
    fields = errors["fields"]
    assert isinstance(fields, dict), f"The errors member carries no fields. Got {errors!r}."
    return {str(name): str(message) for name, message in fields.items()}


def a_category(
    factory: Factory,
    *,
    name: str,
    sort_order: int = 0,
    parent: Category | None = None,
    is_active: bool = True,
    description: str | None = None,
) -> Category:
    """Create a category, optionally under a parent."""
    category = factory.category(name=name)
    category.sort_order = sort_order
    category.parent_category_id = parent.id if parent else None
    category.is_active = is_active
    category.description = description
    factory.session.add(category)
    factory.session.flush()
    return category


def a_model(
    factory: Factory,
    *,
    name: str,
    category: Category | None = None,
    manufacturer: str = "Bosch",
    model_number: str = "GBH 2-26 DRE",
    daily_rate: str = "185.00",
    is_published: bool = True,
    min_hire_days: int = 1,
    max_hire_days: int = 28,
) -> ProductModel:
    """Create a catalogue entry with the columns a catalogue test reads."""
    model = factory.product_model(name=name, category=category)
    model.manufacturer = manufacturer
    model.model_number = model_number
    model.daily_rate = Decimal(daily_rate)
    model.is_published = is_published
    model.min_hire_days = min_hire_days
    model.max_hire_days = max_hire_days
    factory.session.add(model)
    factory.session.flush()
    return model


def hold_unit(
    factory: Factory, asset: Asset, period: BookingPeriod, *, released: bool = False
) -> AssetAllocation:
    """Allocate one unit for a period, on a booking of its own, and flush it.

    Args:
        factory: The factory bound to the session under test.
        asset: The unit to hold.
        period: The half open period it is held for.
        released: When True the allocation is written as already released, so
            it is history and no longer occupies the unit.

    """
    session = factory.session
    branch = session.get(Branch, asset.branch_id)
    model = session.get(ProductModel, asset.product_model_id)
    assert branch is not None and model is not None, "The unit has no branch or no model."
    customer = factory.user(role=UserRole.CUSTOMER)
    profile = factory.customer_profile(branch=branch, account=customer)
    reservation = factory.reservation(
        profile=profile, created_by=customer, branch=branch, period=period
    )
    line = factory.reservation_line(reservation=reservation, product_model=model)
    allocation = factory.allocation(
        line=line,
        asset=asset,
        period=period,
        released_at=RELEASED_AT if released else None,
        release_reason=ReleaseReason.RETURNED if released else None,
    )
    session.add(allocation)
    session.flush()
    logger.debug(
        "test.unit_held",
        extra={
            "asset_tag": asset.asset_tag,
            "period": period.as_postgres_daterange(),
            "released": released,
        },
    )
    return allocation


__all__ = [
    "AVAILABILITY_PATH",
    "BRANCHES_PATH",
    "CATEGORIES_PATH",
    "MODELS_PATH",
    "VALIDATION_PROBLEM",
    "a_category",
    "a_model",
    "hold_unit",
    "model_availability_path",
    "model_path",
    "refused_fields",
    "visitor_client",
]
