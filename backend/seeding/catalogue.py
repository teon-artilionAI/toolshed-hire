"""Load the branches, the categories and the product models.

Each loader reads the rows that already exist in one query, inserts the ones
that are missing and returns every row keyed by its natural key, so the next
loader can resolve a code to an id without asking the database again.
"""

from __future__ import annotations

import logging

from sqlmodel import Session, select

from app.infrastructure.models import Branch, Category, ProductModel
from seed_data import BRANCHES, CATEGORIES, PRODUCT_MODELS
from seed_data.types import CategorySeed
from seeding.errors import SeedDataError
from seeding.report import SeedTally

logger = logging.getLogger("seed")

BRANCH_KIND = "branch"
CATEGORY_KIND = "category"
PRODUCT_MODEL_KIND = "product_model"


def load_branches(session: Session, tally: SeedTally) -> dict[str, Branch]:
    """Insert the branches that are missing and return all of them by code."""
    by_code = {branch.code: branch for branch in session.exec(select(Branch)).all()}
    created = 0
    for seed in BRANCHES:
        if seed.code in by_code:
            logger.debug("seed.branch_found", extra={"code": seed.code})
            continue
        branch = Branch(
            code=seed.code,
            name=seed.name,
            street_address=seed.street_address,
            suburb=seed.suburb,
            city=seed.city,
            postal_code=seed.postal_code,
            phone=seed.phone,
            opens_at=seed.opens_at,
            closes_at=seed.closes_at,
            is_active=True,
        )
        session.add(branch)
        by_code[seed.code] = branch
        created += 1
        logger.info("seed.branch_created", extra={"code": seed.code, "branch_name": seed.name})
    session.flush()
    tally.record(BRANCH_KIND, created=created, found=len(BRANCHES) - created)
    return {seed.code: by_code[seed.code] for seed in BRANCHES}


def load_categories(session: Session, tally: SeedTally) -> dict[str, Category]:
    """Insert the categories that are missing, parents first, and return all by code.

    Raises:
        SeedDataError: If a child names a parent that is not in the data, or a
            parent that is itself a child. The catalogue nests one level and no
            deeper.

    """
    _check_category_tree()
    by_code = {category.code: category for category in session.exec(select(Category)).all()}
    created = 0
    parents = [seed for seed in CATEGORIES if seed.parent_code is None]
    children = [seed for seed in CATEGORIES if seed.parent_code is not None]
    # I flush the parents before the children. Nothing tells the session that a
    # child row depends on its parent row, so the order is mine to keep.
    for group in (parents, children):
        for seed in group:
            if seed.code in by_code:
                logger.debug("seed.category_found", extra={"code": seed.code})
                continue
            parent = by_code[seed.parent_code] if seed.parent_code is not None else None
            category = Category(
                code=seed.code,
                name=seed.name,
                slug=seed.slug,
                description=seed.description,
                parent_category_id=parent.id if parent is not None else None,
                sort_order=seed.sort_order,
                is_active=True,
            )
            session.add(category)
            by_code[seed.code] = category
            created += 1
            logger.info(
                "seed.category_created",
                extra={"code": seed.code, "parent_code": seed.parent_code},
            )
        session.flush()
    tally.record(CATEGORY_KIND, created=created, found=len(CATEGORIES) - created)
    return {seed.code: by_code[seed.code] for seed in CATEGORIES}


def load_product_models(
    session: Session, categories: dict[str, Category], tally: SeedTally
) -> dict[str, ProductModel]:
    """Insert the product models that are missing, published, and return all by SKU.

    Raises:
        SeedDataError: If a model names a category that is not in the data.

    """
    by_sku = {model.sku: model for model in session.exec(select(ProductModel)).all()}
    created = 0
    for seed in PRODUCT_MODELS:
        if seed.category_code not in categories:
            raise SeedDataError(
                f"Product model {seed.sku} names category {seed.category_code!r}, which is "
                f"not in the seed data. The known codes are {sorted(categories)}."
            )
        if seed.sku in by_sku:
            logger.debug("seed.product_model_found", extra={"sku": seed.sku})
            continue
        model = ProductModel(
            sku=seed.sku,
            name=seed.name,
            slug=seed.slug,
            category_id=categories[seed.category_code].id,
            manufacturer=seed.manufacturer,
            model_number=seed.model_number,
            short_description=seed.short_description,
            long_description=seed.long_description,
            daily_rate=seed.daily_rate,
            weekly_rate=seed.weekly_rate,
            deposit_amount=seed.deposit_amount,
            late_fee_per_day=seed.late_fee_per_day,
            replacement_value=seed.replacement_value,
            min_hire_days=seed.min_hire_days,
            max_hire_days=seed.max_hire_days,
            is_published=True,
        )
        session.add(model)
        by_sku[seed.sku] = model
        created += 1
        logger.debug("seed.product_model_created", extra={"sku": seed.sku})
    session.flush()
    tally.record(PRODUCT_MODEL_KIND, created=created, found=len(PRODUCT_MODELS) - created)
    return {seed.sku: by_sku[seed.sku] for seed in PRODUCT_MODELS}


def _check_category_tree() -> None:
    """Refuse a category whose parent is missing or is itself a child."""
    by_code: dict[str, CategorySeed] = {seed.code: seed for seed in CATEGORIES}
    for seed in CATEGORIES:
        if seed.parent_code is None:
            continue
        parent = by_code.get(seed.parent_code)
        if parent is None:
            raise SeedDataError(
                f"Category {seed.code} names parent {seed.parent_code!r}, which is not in "
                f"the seed data. The known codes are {sorted(by_code)}."
            )
        if parent.parent_code is not None:
            raise SeedDataError(
                f"Category {seed.code} sits under {parent.code}, which is itself a child of "
                f"{parent.parent_code}. The catalogue nests one level and no deeper."
            )
