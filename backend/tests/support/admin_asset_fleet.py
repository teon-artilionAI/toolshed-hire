"""The small fleet the register's route tests read, and how they read a page and a history.

Two branches, CBD and BLV, a hammer and a breaker in one category, a hammer
on the shelf at each branch with the one at BLV in quarantine, and a breaker
at CBD with a serial number. Each tag sorts where a test of the order expects
it. Nothing is committed but by `stock_fleet`, which the test calls once.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from sqlmodel import Session

from app.domain.enums import AssetStatus
from app.infrastructure.models import Branch, ProductModel
from tests.support.catalogue import a_category, a_model
from tests.support.factories import Factory

HAMMER_TAG: Final[str] = "TSH-DR-0042"
QUARANTINED_TAG: Final[str] = "TSH-DR-0043"
BREAKER_TAG: Final[str] = "TSH-BR-0011"
BREAKER_SERIAL: Final[str] = "HIL-77120"


@dataclass(frozen=True, slots=True)
class Fleet:
    """Two branches, two models and three units, one of them in quarantine."""

    cbd: Branch
    blv: Branch
    hammer: ProductModel
    breaker: ProductModel


def stock_fleet(session: Session, factory: Factory) -> Fleet:
    """Commit a hammer at each branch, the second in quarantine, and a breaker with a serial."""
    cbd = factory.branch(code="CBD", name="Cape Town CBD")
    blv = factory.branch(code="BLV", name="Bellville")
    category = a_category(factory, name="Drilling")
    hammer = a_model(factory, name="Rotary hammer", category=category)
    breaker = a_model(factory, name="Demolition breaker", category=category)
    factory.asset(product_model=hammer, branch=cbd, asset_tag=HAMMER_TAG)
    factory.asset(
        product_model=hammer,
        branch=blv,
        asset_tag=QUARANTINED_TAG,
        status=AssetStatus.QUARANTINED,
    )
    unit = factory.asset(product_model=breaker, branch=cbd, asset_tag=BREAKER_TAG)
    unit.serial_number = BREAKER_SERIAL
    session.add(unit)
    session.commit()
    return Fleet(cbd=cbd, blv=blv, hammer=hammer, breaker=breaker)


def tags_of(page: dict[str, object]) -> list[object]:
    """Return the tags of the units on a page, in order."""
    items = page["items"]
    assert isinstance(items, list)
    return [item["assetTag"] for item in items]


def history_in(detail: dict[str, object]) -> list[dict[str, object]]:
    """Return the history of a unit as the route answered it."""
    history = detail["history"]
    assert isinstance(history, list)
    return history


__all__ = [
    "BREAKER_SERIAL",
    "BREAKER_TAG",
    "HAMMER_TAG",
    "QUARANTINED_TAG",
    "Fleet",
    "history_in",
    "stock_fleet",
    "tags_of",
]
