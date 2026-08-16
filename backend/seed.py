"""Idempotent seed data for local development and demonstration.

Run it as often as you like. Every row is matched on its natural key, the
branch code, the SKU, the asset tag or the email address, so a second run
updates rather than duplicating.

The catalogue, the tags and the people match `frontend/src/shared/fixtures.ts`
wherever the two overlap, so the React client and the API describe the same
business rather than two different ones. TSH-DR-0042 is the worked example unit
from the Task 1 document.

Passwords come from the SEED_PASSWORD environment variable. Outside
development the script refuses to run without it rather than seeding a known
password into a reachable database.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import date
from decimal import Decimal

from sqlmodel import Session, select

from app.config import settings
from app.domain.enums import AssetStatus, ConditionGrade, UserRole
from app.infrastructure.database import session_scope
from app.infrastructure.models import Asset, Branch, ProductModel, UserAccount
from app.infrastructure.security import hash_password
from app.logging_config import configure_logging

logger = logging.getLogger("seed")

SEED_PASSWORD_VARIABLE = "SEED_PASSWORD"
DEVELOPMENT_SEED_PASSWORD = "toolshed-dev-password"
CITY = "Cape Town"

BRANCHES: tuple[tuple[str, str, str], ...] = (
    ("CBD", "Cape Town CBD", "Woodstock"),
    ("BEL", "Bellville", "Stikland"),
    ("SOM", "Somerset West", "Firgrove"),
)

# sku, name, slug, manufacturer, description, daily, deposit, late fee, replacement
PRODUCT_MODELS: tuple[tuple[str, str, str, str, str, str, str, str, str], ...] = (
    (
        "TSH-PM-0101",
        "GBH 2-26 DRE Rotary Hammer",
        "gbh-2-26-dre-rotary-hammer",
        "Bosch",
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
    ("TSH-DR-0044", "TSH-PM-0101", "BEL", "AVAILABLE", "B", "2023-02-20", "3650.00"),
    ("TSH-DR-0045", "TSH-PM-0101", "SOM", "QUARANTINED", "C", "2023-02-20", "3650.00"),
    ("TSH-BR-0011", "TSH-PM-0102", "CBD", "AVAILABLE", "B", "2022-11-04", "29500.00"),
    ("TSH-BR-0012", "TSH-PM-0102", "BEL", "AVAILABLE", "A", "2025-01-15", "31800.00"),
    ("TSH-PC-0021", "TSH-PM-0201", "CBD", "AVAILABLE", "A", "2024-03-18", "17200.00"),
    ("TSH-PC-0022", "TSH-PM-0201", "CBD", "AVAILABLE", "B", "2023-05-22", "16400.00"),
    ("TSH-PC-0023", "TSH-PM-0201", "BEL", "AVAILABLE", "A", "2025-02-10", "18100.00"),
    ("TSH-MX-0051", "TSH-PM-0301", "CBD", "AVAILABLE", "B", "2023-01-12", "6300.00"),
    ("TSH-MX-0052", "TSH-PM-0301", "BEL", "AVAILABLE", "A", "2025-04-08", "7100.00"),
    ("TSH-CS-0071", "TSH-PM-0401", "CBD", "AVAILABLE", "A", "2025-06-02", "16200.00"),
    ("TSH-CS-0072", "TSH-PM-0401", "SOM", "AVAILABLE", "B", "2023-08-11", "15400.00"),
)

# email, full name, role, branch code
USERS: tuple[tuple[str, str, UserRole, str | None], ...] = (
    ("w.adonis@buildright.co.za", "Wesley Adonis", UserRole.CUSTOMER, None),
    ("elmarie@toolshedhire.co.za", "Elmarie Fourie", UserRole.COUNTER_STAFF, "CBD"),
    ("marius@toolshedhire.co.za", "Marius Pretorius", UserRole.ADMIN, None),
)


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
    for code, name, suburb in BRANCHES:
        branch = session.exec(select(Branch).where(Branch.code == code)).first()
        if branch is None:
            branch = Branch(code=code, name=name, suburb=suburb, city=CITY, is_active=True)
            session.add(branch)
            logger.info("seed.branch_created", extra={"code": code, "branch_name": name})
        else:
            branch.name, branch.suburb, branch.city = name, suburb, CITY
            logger.debug("seed.branch_unchanged", extra={"code": code})
        result[code] = branch
    session.flush()
    return result


def seed_product_models(session: Session) -> dict[str, ProductModel]:
    """Create or update the catalogue entries, keyed by SKU."""
    result: dict[str, ProductModel] = {}
    for entry in PRODUCT_MODELS:
        sku, name, slug, maker, description, daily, deposit, late_fee, replacement = entry
        model = session.exec(select(ProductModel).where(ProductModel.sku == sku)).first()
        values = {
            "name": name,
            "slug": slug,
            "manufacturer": maker,
            "short_description": description,
            "daily_rate": Decimal(daily),
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


def run_seed() -> None:
    """Seed every table in one transaction and log a summary."""
    password = resolve_seed_password()
    logger.info("seed.started", extra={"environment": settings.environment.value})
    with session_scope() as session:
        branches = seed_branches(session)
        models = seed_product_models(session)
        asset_count = seed_assets(session, branches, models)
        user_count = seed_users(session, branches, password)
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
