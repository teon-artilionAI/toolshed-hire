"""The damage report port.

The hire module owns damage reports, as it owns the rentals they are filed
against, and is the only module that writes them. The repository adds a report
once and saves the moves of its status, and a report that is going to change
is read locked, so two administrators closing one report take turns.

A report also has to ask a few things about its unit and its hire that no
other port answers, which unit a tag names, which rental an item is on, what
the unit's last hire was and whether it still waits for an assessment, how
many other reports of the unit are open and whether a booking still holds it.
They sit here, beside the report, because a report is the only thing that
asks them.

The reads that return read models sit behind the same port, so a use case
reads what it has just written inside the transaction that wrote it. One
report is one statement. A page of them is two, however long the page is.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.application.hire.damage_models import (
    DamageReportDetail,
    DamageReportKey,
    DamageReportPage,
    DamageReportSearch,
)
from app.domain.damage import DamageReport
from app.domain.damage_filing import UnitLastHire


class DamageReportRepository(Protocol):
    """Where damage reports are stored and where their references come from."""

    def next_reference(self, year: int) -> str:
        """Return the next unused report reference, for example TSH-D-26-00031.

        The number comes from a database sequence, which never hands one
        number out twice and never takes one back.

        Args:
            year: The calendar year the report is filed in.

        """
        ...

    def add(self, report: DamageReport) -> None:
        """Write a new report inside the current transaction."""
        ...

    def find_for_update(self, key: DamageReportKey) -> DamageReport | None:
        """Return one report, locked for a change, or None when there is none."""
        ...

    def save(self, report: DamageReport) -> None:
        """Write the status, the cost, the notes and the time a report was closed.

        Raises:
            LookupError: If the report was never stored.

        """
        ...

    def unit_id_of_tag(self, asset_tag: str) -> UUID | None:
        """Return the key of the unit with this tag, or None when no unit has it."""
        ...

    def hire_of_item(self, rental_item_id: UUID) -> UUID | None:
        """Return the key of the rental an item is on, or None when there is no such item."""
        ...

    def last_hire_of(self, asset_id: UUID) -> UnitLastHire | None:
        """Return the most recent hire of a unit, or None when it was never hired."""
        ...

    def other_open_reports(self, asset_id: UUID, report_id: UUID) -> int:
        """Return how many reports of a unit are still open, one report left out."""
        ...

    def holds_active_allocation(self, asset_id: UUID) -> bool:
        """Return True when a booking still holds the unit (BR-37)."""
        ...

    def find_detail(self, key: DamageReportKey) -> DamageReportDetail | None:
        """Return one report as staff read it, or None when there is none."""
        ...

    def search(self, search: DamageReportSearch) -> DamageReportPage:
        """Return one page of the reports that match, newest first."""
        ...
