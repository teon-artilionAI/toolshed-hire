"""The read side of the in memory asset register, over what the store committed.

The register's use cases answer through the `AssetRegisterQuery` port once
they have committed, and the read of the register goes through it as well.
This double reads the committed units of a `RegisterStore`, and hands back the
history facts a test put in the store. It records every limit a history was
read with, so a test can see that the use case asked for fifty.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final
from uuid import UUID

from app.application.catalogue.asset_read_models import (
    AdminAssetEntry,
    AdminAssetPage,
    AdminAssetSearch,
    AssetHistoryFacts,
)
from app.domain.asset_register import RegisteredUnit

if TYPE_CHECKING:
    from tests.support.memory_register import RegisterStore

CATEGORY_NAME: Final[str] = "Drilling"
NO_HISTORY: Final[AssetHistoryFacts] = AssetHistoryFacts(
    allocations=(), hires=(), damage_reports=(), audit_events=()
)


class MemoryAssetRegister:
    """The read side of the register over what the store committed."""

    def __init__(self, store: RegisterStore) -> None:
        """Bind to the store."""
        self._store = store

    def branch_id_of(self, branch_code: str) -> UUID | None:
        """Return the key of the branch with this code, trading or not."""
        branch = self._store.branches.get(branch_code)
        return branch.id if branch is not None else None

    def page(self, search: AdminAssetSearch) -> AdminAssetPage:
        """Return one page of the committed units that match, in tag order."""
        matching = [
            self._entry(unit)
            for unit in self._store.committed.units.values()
            if _matches(unit, search)
        ]
        matching.sort(key=lambda entry: entry.asset_tag)
        items = tuple(matching[search.offset : search.offset + search.page_size])
        return AdminAssetPage(
            items=items, page=search.page, page_size=search.page_size, total=len(matching)
        )

    def unit(self, asset_tag: str) -> AdminAssetEntry | None:
        """Return one committed unit as the list shows it."""
        found = self._store.unit_tagged(asset_tag)
        if found is None or self._store.forget_answers:
            return None
        return self._entry(found)

    def history(self, asset_id: UUID, limit: int) -> AssetHistoryFacts:
        """Return the facts the test gave for the unit, and remember the limit asked for."""
        self._store.history_asked.append(limit)
        return self._store.history.get(asset_id, NO_HISTORY)

    def _entry(self, registered: RegisteredUnit) -> AdminAssetEntry:
        """Return the read model of one committed unit."""
        unit = registered.unit
        model = self._store.models[unit.product_model_id]
        branch = self._store.branch_with_id(unit.branch_id)
        return AdminAssetEntry(
            id=unit.id,
            asset_tag=unit.asset_tag,
            model_id=model.id,
            model_name=model.name,
            model_slug=model.slug,
            category_name=CATEGORY_NAME,
            branch_code=branch.code,
            branch_name=branch.name,
            serial_number=registered.serial_number,
            status=unit.status,
            condition_grade=unit.condition_grade,
            acquired_on=registered.acquired_on,
            acquisition_cost=registered.acquisition_cost,
            hour_meter_reading=unit.hour_meter_reading,
            notes=registered.notes,
            retired_on=unit.retired_on,
            active_allocation_count=1 if unit.id in self._store.held_by else 0,
            open_damage_reports=1 if unit.id in self._store.open_reports else 0,
        )


def _matches(registered: RegisteredUnit, search: AdminAssetSearch) -> bool:
    """Return True when a unit is one the search asks for."""
    unit = registered.unit
    return (
        (search.branch_id is None or unit.branch_id == search.branch_id)
        and (search.status is None or unit.status is search.status)
        and (search.model_id is None or unit.product_model_id == search.model_id)
        and (search.text is None or search.text.upper() in unit.asset_tag)
    )


__all__ = ["CATEGORY_NAME", "NO_HISTORY", "MemoryAssetRegister"]
