"""Load the physical units, the pinned ones and the generated ones."""

from __future__ import annotations

import logging

from sqlmodel import Session, col, select

from app.infrastructure.models import Asset, Branch, ProductModel
from seed_data import BRANCHES, PINNED_ASSETS, PRODUCT_MODELS
from seeding.fleet_plan import PlannedAsset, plan_fleet
from seeding.report import SeedTally

logger = logging.getLogger("seed")

PINNED_ASSET_KIND = "pinned_asset"
GENERATED_ASSET_KIND = "generated_asset"


def load_assets(
    session: Session,
    branches: dict[str, Branch],
    models: dict[str, ProductModel],
    tally: SeedTally,
) -> None:
    """Insert every planned unit whose tag is not in the database yet.

    The planned tags that already exist are read in one query and the missing
    units go out in one flush, so a run costs no round trip per unit and never
    reads the rest of a fleet that has grown since.

    Args:
        session: The open session the units are added to.
        branches: The loaded branches by code.
        models: The loaded product models by SKU.
        tally: Where the created and found counts are recorded.

    Raises:
        SeedDataError: If the plan cannot be built from the seed data.

    """
    plan = plan_fleet(PRODUCT_MODELS, PINNED_ASSETS, [branch.code for branch in BRANCHES])
    planned_tags = [unit.asset_tag for unit in plan]
    existing_tags = set(
        session.exec(
            select(col(Asset.asset_tag)).where(col(Asset.asset_tag).in_(planned_tags))
        ).all()
    )
    created = {PINNED_ASSET_KIND: 0, GENERATED_ASSET_KIND: 0}
    found = {PINNED_ASSET_KIND: 0, GENERATED_ASSET_KIND: 0}
    for unit in plan:
        kind = PINNED_ASSET_KIND if unit.is_pinned else GENERATED_ASSET_KIND
        if unit.asset_tag in existing_tags:
            found[kind] += 1
            logger.debug("seed.asset_found", extra={"asset_tag": unit.asset_tag})
            continue
        session.add(_asset_from(unit, branches, models))
        created[kind] += 1
        logger.debug(
            "seed.asset_created",
            extra={"asset_tag": unit.asset_tag, "sku": unit.sku, "branch_code": unit.branch_code},
        )
    session.flush()
    for kind in (PINNED_ASSET_KIND, GENERATED_ASSET_KIND):
        tally.record(kind, created=created[kind], found=found[kind])


def _asset_from(
    unit: PlannedAsset, branches: dict[str, Branch], models: dict[str, ProductModel]
) -> Asset:
    """Build the row for one planned unit."""
    return Asset(
        asset_tag=unit.asset_tag,
        product_model_id=models[unit.sku].id,
        branch_id=branches[unit.branch_code].id,
        serial_number=unit.serial_number,
        status=unit.status,
        condition_grade=unit.condition_grade,
        acquired_on=unit.acquired_on,
        acquisition_cost=unit.acquisition_cost,
        hour_meter_reading=unit.hour_meter_reading,
        retired_on=unit.retired_on,
    )
