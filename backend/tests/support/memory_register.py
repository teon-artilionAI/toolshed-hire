"""An in memory unit of work and query for the asset register, with no database at all.

The register's use cases reach the units, the asset repository, the branches,
the product models and the audit log through the unit of work, and read their
answer back through the `AssetRegisterQuery` port once they have committed,
whose double is in `memory_register_reads`. Everything is kept here in plain
dictionaries. Work is kept only when `commit`
is called, so a test can see that a refusal wrote nothing.

The store can be told what the database would say. `held_by` names the booking
that holds a unit, `open_reports` a damage report still open, `history` the
facts a unit's history is read from, `race_on_tag` makes the next insert lose
to the unique constraint after the check found the tag free, `fail_audit`
makes the audit write fail and `forget_answers` makes the read lose what was
committed, which a real commit never does.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from datetime import datetime, time
from decimal import Decimal
from types import TracebackType
from typing import Final, Self
from uuid import UUID, uuid4

from app.application.catalogue.admin_ports import DuplicateCatalogueValue
from app.application.catalogue.asset_read_models import AssetHistoryFacts
from app.domain.asset_register import ASSET_TAG, RegisteredUnit
from app.domain.audit import AuditEvent
from app.domain.catalogue import Asset, ProductModel
from app.domain.identity import Branch
from tests.support.memory_outbox import StoreFault
from tests.support.memory_register_reads import NO_HISTORY, MemoryAssetRegister

COMMIT: Final[str] = "commit"


@dataclass
class RegisterRecords:
    """Everything a transaction of the register can change."""

    units: dict[UUID, RegisteredUnit] = field(default_factory=dict)
    changed_at: dict[UUID, datetime] = field(default_factory=dict)
    audit_events: list[AuditEvent] = field(default_factory=list)


@dataclass
class RegisterStore:
    """The committed register, the reference data and what the database would answer.

    Attributes:
        committed: What has been committed so far.
        branches: The branches, by code.
        closed_branch_codes: The codes of branches that stopped trading.
        models: The product models, by key.
        held_by: The booking that holds a unit, by the unit's key.
        open_reports: A damage report still open, by the unit's key.
        history: The facts of a unit's history, by the unit's key.
        journal: `commit` for every commit, in order.
        race_on_tag: True to make the next insert lose to the unique constraint.
        fail_audit: When True, recording an audit event raises.
        forget_answers: When True, the read finds nothing.
        history_asked: The limit of every history read, in order.

    """

    committed: RegisterRecords = field(default_factory=RegisterRecords)
    branches: dict[str, Branch] = field(default_factory=dict)
    closed_branch_codes: set[str] = field(default_factory=set)
    models: dict[UUID, ProductModel] = field(default_factory=dict)
    held_by: dict[UUID, str] = field(default_factory=dict)
    open_reports: dict[UUID, str] = field(default_factory=dict)
    history: dict[UUID, AssetHistoryFacts] = field(default_factory=dict)
    journal: list[str] = field(default_factory=list)
    race_on_tag: bool = False
    fail_audit: bool = False
    forget_answers: bool = False
    history_asked: list[int] = field(default_factory=list)

    def keep(self, *units: RegisteredUnit) -> None:
        """Commit units a test starts from."""
        for unit in units:
            self.committed.units[unit.unit.id] = unit

    def unit_tagged(self, asset_tag: str) -> RegisteredUnit | None:
        """Return the committed unit with this tag, if there is one."""
        return _tagged(self.committed.units, asset_tag)

    @property
    def events(self) -> list[AuditEvent]:
        """Return the audit events committed so far."""
        return self.committed.audit_events

    def branch_with_id(self, branch_id: UUID) -> Branch:
        """Return the branch with this key.

        Raises:
            LookupError: If the store holds no such branch.

        """
        for branch in self.branches.values():
            if branch.id == branch_id:
                return branch
        raise LookupError(f"Attempted to read branch {branch_id}, which the store does not hold.")


def a_branch(code: str = "CBD", name: str = "Cape Town CBD") -> Branch:
    """Return a trading branch."""
    return Branch(id=uuid4(), code=code, name=name, closes_at=time(17, 0))


def a_model(name: str = "Bosch GBH 2-26 DRE rotary hammer") -> ProductModel:
    """Return a product model, as the domain holds one."""
    return ProductModel(
        id=uuid4(),
        sku="DR-BOSCH-GBH226",
        name=name,
        slug="bosch-gbh-2-26-dre-rotary-hammer",
        daily_rate=Decimal("280.00"),
        weekly_rate=Decimal("1120.00"),
        deposit_amount=Decimal("600.00"),
        late_fee_per_day=Decimal("120.00"),
        replacement_value=Decimal("4200.00"),
        min_hire_days=1,
        max_hire_days=28,
    )


def _tagged(units: dict[UUID, RegisteredUnit], asset_tag: str) -> RegisteredUnit | None:
    """Return the unit with this tag among some units, if there is one."""
    return next((unit for unit in units.values() if unit.unit.asset_tag == asset_tag), None)


class _Register:
    """The register repository over the working copy."""

    def __init__(self, store: RegisterStore, working: RegisterRecords) -> None:
        """Bind to the store and to the working copy of one transaction."""
        self._store = store
        self._working = working

    def tag_taken(self, asset_tag: str) -> bool:
        """Return True when a unit carries the tag."""
        return _tagged(self._working.units, asset_tag) is not None

    def add(self, unit: RegisteredUnit, now: datetime) -> None:
        """Keep a new unit, unless the test made it lose a race."""
        if self._store.race_on_tag:
            self._store.race_on_tag = False
            raise DuplicateCatalogueValue(ASSET_TAG)
        self._working.units[unit.unit.id] = unit
        self._working.changed_at[unit.unit.id] = now

    def find_for_update(self, asset_tag: str) -> RegisteredUnit | None:
        """Return the unit with this tag. Nothing is locked in memory."""
        return _tagged(self._working.units, asset_tag)

    def save_details(self, unit: RegisteredUnit, now: datetime) -> None:
        """Keep the changed paperwork of a unit."""
        self._working.units[unit.unit.id] = unit
        self._working.changed_at[unit.unit.id] = now

    def holding_reservation(self, asset_id: UUID) -> str | None:
        """Return the booking the test said holds the unit."""
        return self._store.held_by.get(asset_id)

    def open_damage_report(self, asset_id: UUID) -> str | None:
        """Return the open report the test said the unit has."""
        return self._store.open_reports.get(asset_id)


class _Assets:
    """The part of the asset repository a move writes through."""

    def __init__(self, working: RegisterRecords) -> None:
        """Bind to the working copy of one transaction."""
        self._working = working

    def save_units(self, assets: list[Asset]) -> None:
        """Keep the new status, grade, meter and retirement of each unit."""
        for asset in assets:
            stored = self._working.units[asset.id]
            self._working.units[asset.id] = replace(stored, unit=asset)


class _Branches:
    """The branch repository."""

    def __init__(self, store: RegisterStore) -> None:
        """Bind to the store that holds the branches."""
        self._store = store

    def find_active_by_code(self, code: str) -> Branch | None:
        """Return the trading branch with this code, if there is one."""
        if code in self._store.closed_branch_codes:
            return None
        return self._store.branches.get(code)


class _Models:
    """The product model repository."""

    def __init__(self, store: RegisterStore) -> None:
        """Bind to the store that holds the models."""
        self._store = store

    def get(self, product_model_id: UUID) -> ProductModel | None:
        """Return the model with this key, published or not."""
        return self._store.models.get(product_model_id)


class _AuditLog:
    """The audit log over the working copy."""

    def __init__(self, store: RegisterStore, working: RegisterRecords) -> None:
        """Bind to the store and to the working copy of one transaction."""
        self._store = store
        self._working = working

    def record(self, event: AuditEvent) -> None:
        """Keep the event, or fail when the test has switched the fault on."""
        if self._store.fail_audit:
            raise StoreFault("The audit event could not be written.")
        self._working.audit_events.append(event)


class MemoryRegisterUnitOfWork:
    """A unit of work over the in memory register."""

    asset_register: _Register
    assets: _Assets
    branches: _Branches
    product_models: _Models
    audit: _AuditLog

    def __init__(self, store: RegisterStore) -> None:
        """Bind the unit of work to the store it commits into."""
        self.store = store
        self._working: RegisterRecords | None = None

    def __enter__(self) -> Self:
        """Take a working copy of what is committed."""
        working = copy.deepcopy(self.store.committed)
        self._working = working
        self.asset_register = _Register(self.store, working)
        self.assets = _Assets(working)
        self.branches = _Branches(self.store)
        self.product_models = _Models(self.store)
        self.audit = _AuditLog(self.store, working)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Throw the working copy away. Anything committed has already been kept."""
        self._working = None

    def commit(self) -> None:
        """Make the working copy what is committed."""
        if self._working is None:
            raise RuntimeError("Attempted to commit a register unit of work that is not open.")
        self.store.committed = copy.deepcopy(self._working)
        self.store.journal.append(COMMIT)


__all__ = [
    "COMMIT",
    "NO_HISTORY",
    "MemoryAssetRegister",
    "MemoryRegisterUnitOfWork",
    "RegisterStore",
    "StoreFault",
    "a_branch",
    "a_model",
]
