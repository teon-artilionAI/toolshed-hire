"""What the reads of damage reports are asked with and hand back, as small frozen dataclasses.

`DamageReportDetail` is one report as staff read it, with the unit, its model
and branch, the hire it came back from, who filed it, the recovery it raised
and the replacement value that capped that recovery. `DamageReportSearch` is
the question a list asks, and `DamageReportPage` one page of the answer, with
the page limits every list of this API keeps.

A report is named by its key or by its reference, the way a rental is, so the
counter can type the reference off a repair docket.

Money stays `Decimal` all the way to the HTTP boundary, which writes it as a
string with two decimals (BR-22).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final
from uuid import UUID

from app.application.booking.read_models import (
    DEFAULT_PAGE_SIZE,
    MAXIMUM_PAGE_SIZE,
    MINIMUM_PAGE_SIZE,
)
from app.application.catalogue.read_models import FIRST_PAGE, MAXIMUM_PAGE
from app.domain.enums import DamageSeverity, DamageStatus

# The width of the reference column. Nothing longer can be a reference.
REFERENCE_MAX_LENGTH: Final[int] = 16


@dataclass(frozen=True, slots=True)
class DamageReportKey:
    """How a caller names one damage report, by its key or by its reference.

    Attributes:
        report_id: The key, when the caller gave a UUID.
        reference: The reference, in upper case, when the caller gave anything else.

    """

    report_id: UUID | None = None
    reference: str | None = None

    @classmethod
    def parse(cls, text: str) -> DamageReportKey:
        """Read what a caller typed as a key when it is one, and as a reference otherwise."""
        candidate = text.strip()
        try:
            return cls(report_id=UUID(candidate))
        except ValueError:
            return cls(reference=candidate.upper()[:REFERENCE_MAX_LENGTH])

    @classmethod
    def of(cls, report_id: UUID) -> DamageReportKey:
        """Return the key that names a report by its id."""
        return cls(report_id=report_id)

    def __str__(self) -> str:
        """Return the key or the reference, whichever the caller gave."""
        return str(self.report_id) if self.report_id is not None else str(self.reference)


@dataclass(frozen=True, slots=True)
class DamageReportDetail:
    """One damage report as staff read it.

    Attributes:
        id: The report key.
        reference: Its reference, for example TSH-D-26-00031.
        asset_tag: The tag of the damaged unit.
        model_name: The name of the unit's model.
        branch_code: The branch that holds the unit.
        rental_id: The rental the unit came back from, or None.
        rental_reference: That rental's reference, or None.
        rental_item_id: The rental item the report names, or None.
        severity: How bad the damage is.
        status: Where the report stands.
        description: What is wrong with the unit.
        repair_estimate: What the repair was expected to cost.
        actual_repair_cost: What it cost, once resolved.
        chargeable_to_customer: Whether the customer is charged.
        recovery_charged: The recovery the report raised, including VAT, or
            None when it raised none.
        replacement_value: The most a customer may be charged for the unit,
            copied onto the booking line of the hire, or the model's value
            for a report outside a hire.
        reported_at: When it was filed.
        reported_by_name: Who filed it.
        resolved_at: When it was closed, or None.
        resolution_notes: What was written when it was closed, or None.

    """

    id: UUID
    reference: str
    asset_tag: str
    model_name: str
    branch_code: str
    rental_id: UUID | None
    rental_reference: str | None
    rental_item_id: UUID | None
    severity: DamageSeverity
    status: DamageStatus
    description: str
    repair_estimate: Decimal
    actual_repair_cost: Decimal | None
    chargeable_to_customer: bool
    recovery_charged: Decimal | None
    replacement_value: Decimal
    reported_at: datetime
    reported_by_name: str
    resolved_at: datetime | None
    resolution_notes: str | None


@dataclass(frozen=True, slots=True)
class DamageReportSearch:
    """Which damage reports to list, and which page of them.

    Attributes:
        asset_tag: Only the reports of the unit with this tag, or None.
        status: Only reports in this status, or None for every status.
        branch_id: Only reports of units held at this branch, or None.
        page: The page wanted, counted from one.
        page_size: How many reports a page holds.

    """

    asset_tag: str | None = None
    status: DamageStatus | None = None
    branch_id: UUID | None = None
    page: int = FIRST_PAGE
    page_size: int = DEFAULT_PAGE_SIZE

    def __post_init__(self) -> None:
        """Refuse a search no caller should be able to build.

        The HTTP boundary checks the same limits and answers with a 422. This
        is the second line, so a caller inside the system cannot hand the
        query a negative offset or an unbounded page.

        Raises:
            ValueError: If the page or the page size is out of range.

        """
        if not FIRST_PAGE <= self.page <= MAXIMUM_PAGE:
            raise ValueError(
                f"Attempted to list damage reports for page {self.page}. A page is between "
                f"{FIRST_PAGE} and {MAXIMUM_PAGE}."
            )
        if not MINIMUM_PAGE_SIZE <= self.page_size <= MAXIMUM_PAGE_SIZE:
            raise ValueError(
                f"Attempted to list damage reports with a page size of {self.page_size}. A "
                f"page holds between {MINIMUM_PAGE_SIZE} and {MAXIMUM_PAGE_SIZE} reports."
            )

    @property
    def offset(self) -> int:
        """Return how many reports come before the page wanted."""
        return (self.page - FIRST_PAGE) * self.page_size


@dataclass(frozen=True, slots=True)
class DamageReportPage:
    """One page of a list of damage reports, newest first.

    Attributes:
        items: The reports on the page.
        page: The page this is, counted from one.
        page_size: How many reports a page holds.
        total: How many reports match across every page.

    """

    items: tuple[DamageReportDetail, ...]
    page: int
    page_size: int
    total: int
