"""Fakes of the two reporting ports and builders for the rows they answer with.

The report and the dashboard are tested in `tests/unit` against these, so a
test states the evidence a query object would have read and pins what the
application makes of it. A fake keeps every question it was asked and writes
down when it was read, so a test can show the sweep ran first.

Importing this module opens no connection.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Final
from uuid import UUID, uuid4

from app.application.reporting.evidence import (
    DatedRow,
    EvidenceKind,
    FleetEvidence,
    ReportScope,
    SharedHireRow,
    UnitRow,
)
from app.application.reporting.report_models import (
    AttentionCounts,
    BranchCounts,
    BranchPosition,
)
from app.domain.business_time import business_instant
from app.domain.enums import AssetStatus
from app.domain.identity import Branch

NOTHING: Final[Decimal] = Decimal("0.00")
MORNING: Final[time] = time(10, 0)
ACQUIRED_LONG_AGO: Final[date] = date(2025, 1, 10)
SWEEP: Final[str] = "sweep"
READ: Final[str] = "read"


def at_ten(day: date) -> datetime:
    """Return ten in the morning in Cape Town on a day, in UTC."""
    return business_instant(day, MORNING).astimezone(UTC)


def a_unit(
    tag: str,
    *,
    model: str = "hammer",
    category: str = "drilling",
    branch: str = "CBD",
    status: AssetStatus = AssetStatus.AVAILABLE,
    acquired_on: date = ACQUIRED_LONG_AGO,
    retired_on: date | None = None,
    hire_revenue: str = "0.00",
    late_fees: str = "0.00",
    damage_recovery: str = "0.00",
    repair_costs: str = "0.00",
    asset_id: UUID | None = None,
) -> UnitRow:
    """Return one unit as the query object reads it, its names made from its keys."""
    return UnitRow(
        asset_id=asset_id or uuid4(),
        asset_tag=tag,
        status=status,
        acquired_on=acquired_on,
        retired_on=retired_on,
        branch_code=branch,
        branch_name=f"Branch {branch}",
        model_slug=model,
        model_name=model.title(),
        category_slug=category,
        category_name=category.title(),
        held_on_entry=None,
        held_on_exit=None,
        hire_revenue=Decimal(hire_revenue),
        late_fees=Decimal(late_fees),
        damage_recovery=Decimal(damage_recovery),
        repair_costs=Decimal(repair_costs),
    )


def a_hire(unit: UnitRow, out: date, back: date | None = None) -> DatedRow:
    """Return a hire of a unit, out and back at ten in the morning."""
    return DatedRow(
        asset_id=unit.asset_id,
        kind=EvidenceKind.HIRE,
        began_at=at_ten(out),
        ended_at=at_ten(back) if back is not None else None,
    )


def a_fact(unit: UnitRow, kind: EvidenceKind, began: date, ended: date | None) -> DatedRow:
    """Return a loss or a damage report of a unit, at ten in the morning."""
    return DatedRow(
        asset_id=unit.asset_id,
        kind=kind,
        began_at=at_ten(began),
        ended_at=at_ten(ended) if ended is not None else None,
    )


def a_change(unit: UnitRow, on: date, moved_from: AssetStatus, moved_to: AssetStatus) -> DatedRow:
    """Return a recorded change of a unit's status, at ten in the morning."""
    return DatedRow(
        asset_id=unit.asset_id,
        kind=EvidenceKind.STATUS,
        began_at=at_ten(on),
        moved_from=moved_from,
        moved_to=moved_to,
    )


def a_booking(unit: UnitRow, begins: date, ends: date) -> DatedRow:
    """Return a booking of a unit not yet collected."""
    return DatedRow(
        asset_id=unit.asset_id, kind=EvidenceKind.BOOKING, begins_on=begins, ends_on=ends
    )


def shared(charge_id: UUID, amount: str, unit: UnitRow, line: str, units: int) -> SharedHireRow:
    """Return one unit of a hire charge raised on a whole hire."""
    return SharedHireRow(
        charge_id=charge_id,
        amount_ex_vat=Decimal(amount),
        asset_id=unit.asset_id,
        line_amount=Decimal(line),
        units_on_line=units,
    )


@dataclass
class FakeFleetReport:
    """Answers every read with the evidence it was given and keeps the scopes asked about."""

    evidence_to_answer: FleetEvidence = field(
        default_factory=lambda: FleetEvidence(units=(), dated=(), shared_hire=())
    )
    categories: frozenset[str] = frozenset({"drilling"})
    scopes: list[ReportScope] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)

    def evidence(self, scope: ReportScope) -> FleetEvidence:
        """Keep the scope and answer with the evidence given."""
        self.scopes.append(scope)
        self.calls.append(READ)
        return self.evidence_to_answer

    def category_exists(self, slug: str) -> bool:
        """Return True for a slug among the categories given."""
        return slug in self.categories


@dataclass
class FakeBranches:
    """The trading branches a test names, found by code."""

    branches: tuple[Branch, ...] = ()

    def get(self, branch_id: UUID) -> Branch | None:
        """Return the branch with this key."""
        return next((branch for branch in self.branches if branch.id == branch_id), None)

    def find_active_by_code(self, code: str) -> Branch | None:
        """Return the branch with this code."""
        return next((branch for branch in self.branches if branch.code == code), None)


@dataclass
class FakeDashboardCounts:
    """Answers the dashboard's counts with what a test gives it."""

    positions: tuple[BranchPosition, ...] = ()
    attention: AttentionCounts = field(
        default_factory=lambda: AttentionCounts(
            open_damage_reports=0, customers_on_hold=0, failed_notifications=0
        )
    )
    days_asked: list[date] = field(default_factory=list)

    def branch_positions(self, today: date) -> tuple[BranchPosition, ...]:
        """Keep the day asked about and answer with the positions given."""
        self.days_asked.append(today)
        return self.positions

    def attention_counts(self) -> AttentionCounts:
        """Answer with the counts given."""
        return self.attention


def a_position(code: str, **counts: int) -> BranchPosition:
    """Return one branch with the counts named and nought for the rest."""
    every = {one.name: counts.get(one.name, 0) for one in fields(BranchCounts)}
    return BranchPosition(
        branch_code=code, branch_name=f"Branch {code}", counts=BranchCounts(**every)
    )
