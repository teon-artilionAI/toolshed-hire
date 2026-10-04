"""The ports of the asset register, one that writes and one that reads (FR-23, US-31, US-32).

`AssetRegisterRepository` is reached through the unit of work, so a unit, its
paperwork and the audit event of the change commit together (BR-49). A unit
about to change is read under a row lock, so two administrators moving one
unit take turns and the second sees what the first committed, and a booking
that wants the unit at the same moment either waits for the move or skips the
unit, because the allocation path locks the same row.

A change of status is written through the asset repository of the unit of
work, `save_units`, which is where checkout, a return, a loss and a damage
report write theirs, so a status is written in one place.

The tag is unique, and the database has the last word on it. A use case asks
first, and a repository that loses a race to the unique constraint raises
`DuplicateCatalogueValue` naming the tag.

`AssetRegisterQuery` is the read side. It answers the register's list, one
unit and the facts its history is built from.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.application.catalogue.asset_read_models import (
    AdminAssetEntry,
    AdminAssetPage,
    AdminAssetSearch,
    AssetHistoryFacts,
)
from app.domain.asset_register import RegisteredUnit


class AssetRegisterRepository(Protocol):
    """The units of the fleet, read and written inside a unit of work."""

    def tag_taken(self, asset_tag: str) -> bool:
        """Return True when a unit already carries this tag."""
        ...

    def add(self, unit: RegisteredUnit, now: datetime) -> None:
        """Write a new unit inside the current transaction.

        Raises:
            DuplicateCatalogueValue: If the unique constraint on the tag refused it.

        """
        ...

    def find_for_update(self, asset_tag: str) -> RegisteredUnit | None:
        """Return the unit with this tag, locked until the transaction ends, or None."""
        ...

    def save_details(self, unit: RegisteredUnit, now: datetime) -> None:
        """Write the paperwork of a unit this transaction locked, stamped as changed now."""
        ...

    def holding_reservation(self, asset_id: UUID) -> str | None:
        """Return the reference of a booking that holds the unit now, or None (BR-37)."""
        ...

    def open_damage_report(self, asset_id: UUID) -> str | None:
        """Return the reference of a damage report of the unit still open, or None."""
        ...


class AssetRegisterQuery(Protocol):
    """What the administrator reads of the fleet."""

    def branch_id_of(self, branch_code: str) -> UUID | None:
        """Return the key of the branch with this code, trading or not, or None."""
        ...

    def page(self, search: AdminAssetSearch) -> AdminAssetPage:
        """Return one page of the units that match, in tag order.

        It takes the same number of statements however long the page is.
        """
        ...

    def unit(self, asset_tag: str) -> AdminAssetEntry | None:
        """Return one unit as the list shows it, or None when no unit carries the tag."""
        ...

    def history(self, asset_id: UUID, limit: int) -> AssetHistoryFacts:
        """Return the facts of one unit's history, at most `limit` of each kind, newest first.

        A fact is ordered by the latest instant it carries, so the newest
        `limit` entries of the history are always among them. It takes the
        same number of statements however long the unit's history is.
        """
        ...
