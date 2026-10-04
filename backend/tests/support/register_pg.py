"""The fleet and the lives of units the register's PostgreSQL tests read.

`stocked_units` commits units of two models at one branch, each with a serial
number, and `lived_in` gives one unit a history of returned hires, resolved
damage reports and changes of status. `plan_of` explains a statement with
sequential scans switched off, which shows whether a condition matches the
index it was written for.

`plan_of` analyses the tables first, because an empty or stale table gives the
planner no figures and it then takes any index as good as any other. It does
so inside the transaction that explains, and rolls that transaction back, so
the figures of these few skewed rows never outlive the test. The tables are
emptied between tests and the figures are not, and a later test of another
read would otherwise be planned with this test's figures.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Final

from sqlalchemy import text
from sqlmodel import Session

from app.domain.asset_register import NewUnitTerms, UnitDetails
from app.domain.enums import (
    ConditionGrade,
    DamageSeverity,
    DamageStatus,
    ReservationStatus,
    UserRole,
)
from app.domain.identity import Actor
from app.infrastructure.models import Asset, Branch, DamageReport, ProductModel, UserAccount
from tests.support.admin_log_pg import write_event
from tests.support.catalogue import a_category, a_model
from tests.support.factories import Factory
from tests.support.hire_factories import HireFactory, hire_from

EXPLAIN_PREFIX: Final[str] = "EXPLAIN "
FIRST_DAY: Final[date] = date(2025, 1, 6)
REPORTED_AT: Final[datetime] = datetime(2025, 6, 1, 8, 0, tzinfo=UTC)
SHELF_TAG: Final[str] = "TSH-DR-0042"
NEW_TAG: Final[str] = "TSH-DR-0099"
PAPERWORK: Final[UnitDetails] = UnitDetails(
    serial_number="SN-882731",
    condition_grade=ConditionGrade.A,
    hour_meter_reading=None,
    notes=None,
)
ANALYSED_TABLES: Final[tuple[str, ...]] = (
    "asset",
    "product_model",
    "branch",
    "asset_allocation",
    "rental_item",
    "damage_report",
    "audit_event",
)


def stocked_units(session: Session, factory: Factory, units: int) -> tuple[Branch, list[Asset]]:
    """Commit units of two models at one branch, each with a serial number."""
    branch = factory.branch(code="CBD")
    category = a_category(factory, name="Drilling")
    models = [
        a_model(factory, name=f"Model {number}", category=category) for number in range(2)
    ]
    rows: list[Asset] = []
    for number in range(units):
        unit = factory.asset(
            product_model=models[number % 2], branch=branch, asset_tag=f"TSH-DR-{number:04d}"
        )
        unit.serial_number = f"SN-{number:05d}"
        session.add(unit)
        rows.append(unit)
    session.commit()
    return branch, rows


def lived_in(
    session: Session, factory: Factory, unit: Asset, model: ProductModel, times: int
) -> None:
    """Give one unit a history of `times` returned hires, damage reports and audit events."""
    staff = factory.user(role=UserRole.ADMIN)
    branch = session.get(Branch, unit.branch_id)
    assert branch is not None
    customer = factory.user(role=UserRole.CUSTOMER)
    profile = factory.customer_profile(branch=branch, account=customer)
    hires = HireFactory(factory)
    for number in range(times):
        booked = hires.booking(
            profile=profile,
            created_by=staff,
            branch=branch,
            model=model,
            units=[unit],
            period=hire_from(FIRST_DAY + timedelta(days=7 * number)),
            status=ReservationStatus.RETURNED,
        )
        hires.rental(booked, checked_out_by=staff, units_back=1)
        session.add(_report(unit, staff, number))
        write_event(
            session,
            occurred_at=REPORTED_AT + timedelta(hours=number),
            action="asset.status_changed",
            entity_type="asset",
            entity_id=unit.id,
            actor=staff,
            after_state={"status": "QUARANTINED", "asset_tag": unit.asset_tag},
        )
    session.flush()
    session.commit()


def _report(unit: Asset, staff: UserAccount, number: int) -> DamageReport:
    """Return a resolved damage report of the unit."""
    return DamageReport(
        reference=f"TSH-D-25-{number:05d}",
        asset_id=unit.id,
        severity=DamageSeverity.MINOR,
        status=DamageStatus.RESOLVED,
        description="Worn chuck.",
        repair_estimate=Decimal("100.00"),
        actual_repair_cost=Decimal("90.00"),
        chargeable_to_customer=False,
        reported_by_user_id=staff.id,
        reported_at=REPORTED_AT + timedelta(days=number),
        resolved_at=REPORTED_AT + timedelta(days=number, hours=2),
    )


def plan_of(session: Session, statement: str, **params: object) -> str:
    """Return the plan of a statement with sequential scans switched off, to see the choice.

    The tables are analysed in the same transaction, which is rolled back once
    the plan is read, so the figures go with it.
    """
    for table in ANALYSED_TABLES:
        session.execute(text(f"ANALYZE {table}"))
    session.execute(text("SET LOCAL enable_seqscan = off"))
    plan = session.execute(text(EXPLAIN_PREFIX + statement), params).all()
    session.rollback()
    return "\n".join(str(row[0]) for row in plan)


@dataclass(frozen=True, slots=True)
class Shelf:
    """The CBD branch, a published hammer and one unit of it on the shelf there."""

    branch: Branch
    model: ProductModel
    unit: Asset


def stock_shelf(session: Session, factory: Factory) -> Shelf:
    """Commit a branch, a published hammer and one unit of it on the shelf."""
    branch = factory.branch(code="CBD")
    category = a_category(factory, name="Drilling")
    model = a_model(factory, name="Rotary hammer", category=category)
    unit = factory.asset(product_model=model, branch=branch, asset_tag=SHELF_TAG)
    session.commit()
    return Shelf(branch=branch, model=model, unit=unit)


def admin_actor(account: UserAccount) -> Actor:
    """Return an administrator's account as the actor its audit events name."""
    return Actor(user_id=account.id, role=UserRole.ADMIN)


def new_terms(tag: str = NEW_TAG) -> NewUnitTerms:
    """Return the terms of a new hammer."""
    return NewUnitTerms(
        asset_tag=tag,
        acquired_on=date(2026, 2, 1),
        acquisition_cost=Decimal("3900.00"),
        details=PAPERWORK,
    )


__all__ = [
    "NEW_TAG",
    "SHELF_TAG",
    "Shelf",
    "admin_actor",
    "lived_in",
    "new_terms",
    "plan_of",
    "stock_shelf",
    "stocked_units",
]
