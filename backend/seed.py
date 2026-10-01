"""Idempotent seed data for local development and demonstration.

Run it as often as you like. Every row is matched on its natural key, the
branch code, the category code, the SKU, the asset tag or the email address, so
a second run updates rather than duplicating.

The catalogue, the tags and the people match `frontend/src/shared/fixtures.ts`
wherever the two overlap, so the React client and the API describe the same
business rather than two different ones. TSH-DR-0042 is the worked example unit
from the Task 1 document.

This is still the small seed. It carries just enough to satisfy the documented
schema, which is one holding category for the five models and a customer
profile for the one seeded customer. The full fleet and the real category tree
replace it.

Passwords come from the SEED_PASSWORD environment variable. Outside
development the script refuses to run without it rather than seeding a known
password into a reachable database.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import date, time
from decimal import Decimal

from sqlmodel import Session, select

from app.config import settings
from app.domain.enums import (
    AccountStatus,
    AssetStatus,
    ConditionGrade,
    CustomerType,
    IdDocType,
    UserRole,
)
from app.infrastructure.database import session_scope
from app.infrastructure.models import (
    Asset,
    Branch,
    Category,
    CustomerProfile,
    ProductModel,
    UserAccount,
)
from app.infrastructure.security import hash_password
from app.logging_config import configure_logging

logger = logging.getLogger("seed")

SEED_PASSWORD_VARIABLE = "SEED_PASSWORD"
DEVELOPMENT_SEED_PASSWORD = "toolshed-dev-password"
CITY = "Cape Town"
# Every branch keeps the same counter hours. The no-show sweep reads the
# closing time.
BRANCH_OPENS_AT = time(7, 0)
BRANCH_CLOSES_AT = time(17, 0)

# code, name, street address, suburb, postal code, phone
BRANCHES: tuple[tuple[str, str, str, str, str, str], ...] = (
    ("CBD", "Cape Town CBD", "14 Albert Road", "Woodstock", "7925", "021 555 0101"),
    ("BLV", "Bellville", "8 Stikland Road", "Stikland", "7530", "021 555 0102"),
    ("SMW", "Somerset West", "21 Main Road", "Firgrove", "7130", "021 555 0103"),
)

# One holding category, because a product model cannot exist without one.
SEED_CATEGORY_CODE = "GENERAL"
SEED_CATEGORY_NAME = "General hire"
SEED_CATEGORY_SLUG = "general-hire"

# The seed has no weekly prices yet. Four daily rates for seven days is a
# placeholder so the column is filled, and the fleet seed carries real ones.
DAILY_RATES_PER_WEEK = 4

# sku, name, slug, manufacturer, model number, description, daily, deposit,
# late fee, replacement
PRODUCT_MODELS: tuple[tuple[str, str, str, str, str, str, str, str, str, str], ...] = (
    (
        "TSH-PM-0101",
        "GBH 2-26 DRE Rotary Hammer",
        "gbh-2-26-dre-rotary-hammer",
        "Bosch",
        "GBH 2-26 DRE",
        "SDS-plus rotary hammer, 800 W, 2.7 J impact energy. Anchor holes to 26 mm.",
        "185.00",
        "600.00",
        "120.00",
        "4200.00",
    ),
    (
        "TSH-PM-0102",
        "TE 1000-AVR Breaker",
        "te-1000-avr-breaker",
        "Hilti",
        "TE 1000-AVR",
        "Heavy demolition breaker for floors and foundations, 26 J single impact energy.",
        "620.00",
        "2500.00",
        "380.00",
        "32000.00",
    ),
    (
        "TSH-PM-0201",
        "CP 100 Plate Compactor",
        "cp-100-plate-compactor",
        "Wacker Neuson",
        "CP 100",
        "Forward plate compactor, 62 kg, 500 mm plate. Paving and trench backfill.",
        "340.00",
        "1500.00",
        "220.00",
        "18500.00",
    ),
    (
        "TSH-PM-0301",
        "140 L Concrete Mixer",
        "140-l-concrete-mixer",
        "Baumax",
        "140 L",
        "Tip-up drum mixer on a road-tow frame, 550 W. Small slabs, screeds and mortar.",
        "210.00",
        "800.00",
        "140.00",
        "6800.00",
    ),
    (
        "TSH-PM-0401",
        "TS 420 Cut-off Saw",
        "ts-420-cut-off-saw",
        "Stihl",
        "TS 420",
        "Petrol cut-off saw, 350 mm blade, 125 mm cutting depth. Concrete and masonry.",
        "385.00",
        "1600.00",
        "240.00",
        "16800.00",
    ),
)

# asset tag, sku, branch code, status, condition grade, acquired on, acquisition cost.
# The status and the grade are held as their stored values and converted on use,
# which keeps one row on one line and readable next to the frontend fixtures.
ASSETS: tuple[tuple[str, str, str, str, str, str, str], ...] = (
    ("TSH-DR-0042", "TSH-PM-0101", "CBD", "AVAILABLE", "A", "2024-06-11", "3980.00"),
    ("TSH-DR-0043", "TSH-PM-0101", "CBD", "AVAILABLE", "A", "2024-06-11", "3980.00"),
    ("TSH-DR-0044", "TSH-PM-0101", "BLV", "AVAILABLE", "B", "2023-02-20", "3650.00"),
    ("TSH-DR-0045", "TSH-PM-0101", "SMW", "QUARANTINED", "C", "2023-02-20", "3650.00"),
    ("TSH-BR-0011", "TSH-PM-0102", "CBD", "AVAILABLE", "B", "2022-11-04", "29500.00"),
    ("TSH-BR-0012", "TSH-PM-0102", "BLV", "AVAILABLE", "A", "2025-01-15", "31800.00"),
    ("TSH-PC-0021", "TSH-PM-0201", "CBD", "AVAILABLE", "A", "2024-03-18", "17200.00"),
    ("TSH-PC-0022", "TSH-PM-0201", "CBD", "AVAILABLE", "B", "2023-05-22", "16400.00"),
    ("TSH-PC-0023", "TSH-PM-0201", "BLV", "AVAILABLE", "A", "2025-02-10", "18100.00"),
    ("TSH-MX-0051", "TSH-PM-0301", "CBD", "AVAILABLE", "B", "2023-01-12", "6300.00"),
    ("TSH-MX-0052", "TSH-PM-0301", "BLV", "AVAILABLE", "A", "2025-04-08", "7100.00"),
    ("TSH-CS-0071", "TSH-PM-0401", "CBD", "AVAILABLE", "A", "2025-06-02", "16200.00"),
    ("TSH-CS-0072", "TSH-PM-0401", "SMW", "AVAILABLE", "B", "2023-08-11", "15400.00"),
)

# email, full name, role, branch code
USERS: tuple[tuple[str, str, UserRole, str | None], ...] = (
    ("w.adonis@buildright.co.za", "Wesley Adonis", UserRole.CUSTOMER, None),
    ("elmarie@toolshedhire.co.za", "Elmarie Fourie", UserRole.COUNTER_STAFF, "CBD"),
    ("marius@toolshedhire.co.za", "Marius Pretorius", UserRole.ADMIN, None),
)

# The hire profile of the one seeded customer. A reservation belongs to a
# profile, so without this row the seeded customer could not book anything.
SEED_CUSTOMER_EMAIL = "w.adonis@buildright.co.za"
SEED_CUSTOMER_BRANCH_CODE = "CBD"
SEED_CUSTOMER_PROFILE: dict[str, str] = {
    "display_name": "Wesley Adonis",
    "id_document_last4": "4189",
    "contact_phone": "082 441 7719",
    "billing_address_line1": "27 Durham Avenue",
    "billing_suburb": "Salt River",
    "billing_city": CITY,
    "billing_postal_code": "7925",
}


def resolve_seed_password() -> str:
    """Return the password to seed, refusing a default outside development.

    Raises:
        RuntimeError: If SEED_PASSWORD is unset in a non development environment.

    """
    supplied = os.environ.get(SEED_PASSWORD_VARIABLE)
    if supplied:
        return supplied
    if not settings.environment.is_relaxed:
        raise RuntimeError(
            f"Attempted to seed environment {settings.environment.value!r} without "
            f"{SEED_PASSWORD_VARIABLE}. Set it to the password the seeded accounts should "
            "carry. The development default is never used outside development."
        )
    logger.warning(
        "seed.using_development_password",
        extra={"variable": SEED_PASSWORD_VARIABLE, "environment": settings.environment.value},
    )
    return DEVELOPMENT_SEED_PASSWORD


def seed_branches(session: Session) -> dict[str, Branch]:
    """Create or update the three branches, keyed by code."""
    result: dict[str, Branch] = {}
    for code, name, street_address, suburb, postal_code, phone in BRANCHES:
        branch = session.exec(select(Branch).where(Branch.code == code)).first()
        values = {
            "name": name,
            "street_address": street_address,
            "suburb": suburb,
            "city": CITY,
            "postal_code": postal_code,
            "phone": phone,
            "opens_at": BRANCH_OPENS_AT,
            "closes_at": BRANCH_CLOSES_AT,
        }
        if branch is None:
            branch = Branch(code=code, is_active=True, **values)
            session.add(branch)
            logger.info("seed.branch_created", extra={"code": code, "branch_name": name})
        else:
            for field, value in values.items():
                setattr(branch, field, value)
            logger.debug("seed.branch_updated", extra={"code": code})
        result[code] = branch
    session.flush()
    return result


def seed_category(session: Session) -> Category:
    """Create or update the one holding category, matched on its code."""
    category = session.exec(select(Category).where(Category.code == SEED_CATEGORY_CODE)).first()
    if category is None:
        category = Category(
            code=SEED_CATEGORY_CODE, name=SEED_CATEGORY_NAME, slug=SEED_CATEGORY_SLUG
        )
        session.add(category)
        logger.info("seed.category_created", extra={"code": SEED_CATEGORY_CODE})
    else:
        category.name, category.slug = SEED_CATEGORY_NAME, SEED_CATEGORY_SLUG
        logger.debug("seed.category_updated", extra={"code": SEED_CATEGORY_CODE})
    session.flush()
    return category


def seed_product_models(session: Session, category: Category) -> dict[str, ProductModel]:
    """Create or update the catalogue entries, keyed by SKU."""
    result: dict[str, ProductModel] = {}
    for entry in PRODUCT_MODELS:
        sku, name, slug, maker, model_number, summary, daily, deposit, late_fee, replacement = entry
        model = session.exec(select(ProductModel).where(ProductModel.sku == sku)).first()
        values = {
            "name": name,
            "slug": slug,
            "category_id": category.id,
            "manufacturer": maker,
            "model_number": model_number,
            "short_description": summary,
            "daily_rate": Decimal(daily),
            "weekly_rate": Decimal(daily) * DAILY_RATES_PER_WEEK,
            "deposit_amount": Decimal(deposit),
            "late_fee_per_day": Decimal(late_fee),
            "replacement_value": Decimal(replacement),
            "is_published": True,
        }
        if model is None:
            model = ProductModel(sku=sku, **values)
            session.add(model)
            logger.info("seed.product_model_created", extra={"sku": sku, "model_name": name})
        else:
            for field, value in values.items():
                setattr(model, field, value)
            logger.debug("seed.product_model_updated", extra={"sku": sku})
        result[sku] = model
    session.flush()
    return result


def seed_assets(
    session: Session, branches: dict[str, Branch], models: dict[str, ProductModel]
) -> int:
    """Create or update the physical units. Returns the number of rows touched."""
    touched = 0
    for tag, sku, branch_code, status, grade, acquired, cost in ASSETS:
        asset = session.exec(select(Asset).where(Asset.asset_tag == tag)).first()
        values = {
            "product_model_id": models[sku].id,
            "branch_id": branches[branch_code].id,
            "status": AssetStatus(status),
            "condition_grade": ConditionGrade(grade),
            "acquired_on": date.fromisoformat(acquired),
            "acquisition_cost": Decimal(cost),
        }
        if asset is None:
            session.add(Asset(asset_tag=tag, **values))
            logger.info("seed.asset_created", extra={"asset_tag": tag, "branch": branch_code})
        else:
            for field, value in values.items():
                setattr(asset, field, value)
            logger.debug("seed.asset_updated", extra={"asset_tag": tag})
        touched += 1
    session.flush()
    return touched


def seed_users(session: Session, branches: dict[str, Branch], password: str) -> int:
    """Create or update one account per role. Returns the number of rows touched."""
    password_hash = hash_password(password)
    touched = 0
    for email, full_name, role, branch_code in USERS:
        account = session.exec(select(UserAccount).where(UserAccount.email == email)).first()
        branch_id = branches[branch_code].id if branch_code else None
        if account is None:
            session.add(
                UserAccount(
                    email=email,
                    password_hash=password_hash,
                    role=role,
                    full_name=full_name,
                    branch_id=branch_id,
                    is_active=True,
                )
            )
            logger.info("seed.user_created", extra={"email": email, "role": role.value})
        else:
            account.full_name = full_name
            account.role = role
            account.branch_id = branch_id
            account.password_hash = password_hash
            account.is_active = True
            logger.debug("seed.user_updated", extra={"email": email})
        touched += 1
    session.flush()
    return touched


def seed_customer_profile(session: Session, branches: dict[str, Branch]) -> None:
    """Create or update the hire profile of the seeded customer.

    Raises:
        RuntimeError: If the customer account is absent, which means
            `seed_users` did not run first.

    """
    account = session.exec(
        select(UserAccount).where(UserAccount.email == SEED_CUSTOMER_EMAIL)
    ).first()
    if account is None:
        raise RuntimeError(
            f"Attempted to seed a customer profile for {SEED_CUSTOMER_EMAIL}, but that account "
            "does not exist. Seed the user accounts before the profile."
        )
    profile = session.exec(
        select(CustomerProfile).where(CustomerProfile.user_account_id == account.id)
    ).first()
    if profile is None:
        session.add(
            CustomerProfile(
                user_account_id=account.id,
                customer_type=CustomerType.INDIVIDUAL,
                id_document_type=IdDocType.SA_ID,
                account_status=AccountStatus.ACTIVE,
                registered_branch_id=branches[SEED_CUSTOMER_BRANCH_CODE].id,
                **SEED_CUSTOMER_PROFILE,
            )
        )
        logger.info("seed.customer_profile_created", extra={"email": SEED_CUSTOMER_EMAIL})
    else:
        for field, value in SEED_CUSTOMER_PROFILE.items():
            setattr(profile, field, value)
        logger.debug("seed.customer_profile_updated", extra={"email": SEED_CUSTOMER_EMAIL})
    session.flush()


def run_seed() -> None:
    """Seed every table in one transaction and log a summary."""
    password = resolve_seed_password()
    logger.info("seed.started", extra={"environment": settings.environment.value})
    with session_scope() as session:
        branches = seed_branches(session)
        category = seed_category(session)
        models = seed_product_models(session, category)
        asset_count = seed_assets(session, branches, models)
        user_count = seed_users(session, branches, password)
        seed_customer_profile(session, branches)
    logger.info(
        "seed.completed",
        extra={
            "branches": len(branches),
            "product_models": len(models),
            "assets": asset_count,
            "users": user_count,
        },
    )


if __name__ == "__main__":
    configure_logging()
    try:
        run_seed()
    except Exception as exc:  # noqa: BLE001  the entry point reports and exits
        logger.exception("seed.failed", extra={"error_type": type(exc).__name__})
        sys.exit(1)
