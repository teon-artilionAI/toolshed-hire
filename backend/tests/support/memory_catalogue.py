"""An in memory unit of work for the admin catalogue, with no database at all.

The catalogue use cases reach the categories, the product models and the
audit log through the unit of work, and read their answer back through the
`AdminCatalogueQuery` port once they have committed, whose double is in
`memory_catalogue_reads`. Everything is kept here in plain dictionaries. Work
is kept only when `commit` is called, so a test can see that a refusal wrote
nothing.

The store can be told to lose a race. `race_on` names a field the next write
finds taken, as the unique constraint would after the use case's own check
found it free, and `fail_audit` makes the audit write fail. `forget_answers`
makes the read lose what was committed, which a real commit never does.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime
from types import TracebackType
from typing import Final, Self
from uuid import UUID

from app.application.catalogue.admin_ports import DuplicateCatalogueValue
from app.domain.audit import AuditEvent
from app.domain.catalogue_entry_rules import CatalogueEntry
from app.domain.category_rules import CatalogueCategory
from tests.support.memory_catalogue_reads import MemoryAdminCatalogue
from tests.support.memory_outbox import StoreFault

COMMIT: Final[str] = "commit"


@dataclass
class CatalogueRecords:
    """Everything a transaction of the catalogue can change."""

    categories: dict[UUID, CatalogueCategory] = field(default_factory=dict)
    entries: dict[UUID, CatalogueEntry] = field(default_factory=dict)
    changed_at: dict[UUID, datetime] = field(default_factory=dict)
    audit_events: list[AuditEvent] = field(default_factory=list)


@dataclass
class CatalogueStore:
    """The committed catalogue, the units of the fleet and the fault switches.

    Attributes:
        committed: What has been committed so far.
        asset_counts: How many units the fleet holds of each model.
        journal: `commit` for every commit, in order.
        race_on: A field the next write finds taken, or None.
        fail_audit: When True, recording an audit event raises.
        forget_answers: When True, the read finds nothing.

    """

    committed: CatalogueRecords = field(default_factory=CatalogueRecords)
    asset_counts: dict[UUID, int] = field(default_factory=dict)
    journal: list[str] = field(default_factory=list)
    race_on: str | None = None
    fail_audit: bool = False
    forget_answers: bool = False

    def keep(self, *items: CatalogueCategory | CatalogueEntry) -> None:
        """Commit categories and models a test starts from."""
        for item in items:
            if isinstance(item, CatalogueCategory):
                self.committed.categories[item.id] = item
            else:
                self.committed.entries[item.id] = item

    @property
    def events(self) -> list[AuditEvent]:
        """Return the audit events committed so far."""
        return self.committed.audit_events


class _Categories:
    """The category repository over the working copy."""

    def __init__(self, store: CatalogueStore, working: CatalogueRecords) -> None:
        """Bind to the store and to the working copy of one transaction."""
        self._store = store
        self._working = working

    def get(self, category_id: UUID) -> CatalogueCategory | None:
        """Return the category with this key, if there is one."""
        return self._working.categories.get(category_id)

    def get_for_update(self, category_id: UUID) -> CatalogueCategory | None:
        """Return the category with this key. Nothing is locked in memory."""
        return self.get(category_id)

    def has_children(self, category_id: UUID) -> bool:
        """Return True when a category sits under this one."""
        return any(
            category.terms.parent_category_id == category_id
            for category in self._working.categories.values()
        )

    def taken_fields(
        self, *, code: str | None, slug: str | None, other_than: UUID | None
    ) -> frozenset[str]:
        """Return which of the code and the slug another category holds."""
        others = [c for c in self._working.categories.values() if c.id != other_than]
        taken = {"code" for c in others if code is not None and c.terms.code == code}
        taken |= {"slug" for c in others if slug is not None and c.terms.slug == slug}
        return frozenset(taken)

    def add(self, category: CatalogueCategory, now: datetime) -> None:
        """Keep a new category, unless the test made it lose a race."""
        _lose_a_race(self._store)
        self._working.categories[category.id] = category

    def save(self, category: CatalogueCategory, now: datetime) -> None:
        """Keep a changed category, unless the test made it lose a race."""
        _lose_a_race(self._store)
        self._working.categories[category.id] = category


class _Entries:
    """The product model repository over the working copy."""

    def __init__(self, store: CatalogueStore, working: CatalogueRecords) -> None:
        """Bind to the store and to the working copy of one transaction."""
        self._store = store
        self._working = working

    def get_for_update(self, model_id: UUID) -> CatalogueEntry | None:
        """Return the model with this key. Nothing is locked in memory."""
        return self._working.entries.get(model_id)

    def taken_fields(
        self, *, sku: str | None, slug: str | None, other_than: UUID | None
    ) -> frozenset[str]:
        """Return which of the SKU and the slug another model holds."""
        others = [e for e in self._working.entries.values() if e.id != other_than]
        taken = {"sku" for e in others if sku is not None and e.terms.sku == sku}
        taken |= {"slug" for e in others if slug is not None and e.terms.slug == slug}
        return frozenset(taken)

    def add(self, entry: CatalogueEntry, now: datetime) -> None:
        """Keep a new model, unless the test made it lose a race."""
        _lose_a_race(self._store)
        self._working.entries[entry.id] = entry
        self._working.changed_at[entry.id] = now

    def save(self, entry: CatalogueEntry, now: datetime) -> None:
        """Keep a changed model, unless the test made it lose a race."""
        _lose_a_race(self._store)
        self._working.entries[entry.id] = entry
        self._working.changed_at[entry.id] = now


class _AuditLog:
    """The audit log over the working copy."""

    def __init__(self, store: CatalogueStore, working: CatalogueRecords) -> None:
        """Bind to the store and to the working copy of one transaction."""
        self._store = store
        self._working = working

    def record(self, event: AuditEvent) -> None:
        """Keep the event, or fail when the test has switched the fault on."""
        if self._store.fail_audit:
            raise StoreFault("The audit event could not be written.")
        self._working.audit_events.append(event)


def _lose_a_race(store: CatalogueStore) -> None:
    """Refuse a write as the unique constraint would, once, when the test asked for it."""
    if store.race_on is not None:
        field_name, store.race_on = store.race_on, None
        raise DuplicateCatalogueValue(field_name)


class MemoryCatalogueUnitOfWork:
    """A unit of work over the in memory catalogue."""

    categories: _Categories
    catalogue_entries: _Entries
    audit: _AuditLog

    def __init__(self, store: CatalogueStore) -> None:
        """Bind the unit of work to the store it commits into."""
        self.store = store
        self._working: CatalogueRecords | None = None

    def __enter__(self) -> Self:
        """Take a working copy of what is committed."""
        working = copy.deepcopy(self.store.committed)
        self._working = working
        self.categories = _Categories(self.store, working)
        self.catalogue_entries = _Entries(self.store, working)
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
            raise RuntimeError("Attempted to commit a catalogue unit of work that is not open.")
        self.store.committed = copy.deepcopy(self._working)
        self.store.journal.append(COMMIT)


__all__ = [
    "COMMIT",
    "CatalogueStore",
    "MemoryAdminCatalogue",
    "MemoryCatalogueUnitOfWork",
    "StoreFault",
]
