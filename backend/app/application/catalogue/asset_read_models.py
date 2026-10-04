"""What the asset register is read with and what it hands back (FR-23, US-31, SC-21).

These are small frozen dataclasses with no behaviour beyond checking
themselves. The SQL that fills them lives in the infrastructure layer, behind
the `AssetRegisterQuery` port, and returns these and never a table row.

The register is for an administrator, so unlike everything a visitor reads it
carries the tag, the serial number and the cost of every unit, retired or not.
Money stays `Decimal` all the way to the HTTP boundary (BR-22).

The history of a unit is read as facts from four places, its allocations, its
hires, its damage reports and its audit events. `app.application.catalogue.
asset_history` turns them into the entries the screen shows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from app.application.admin_lists import (
    FIRST_PAGE,
    MAXIMUM_PAGE,
    MAXIMUM_PAGE_SIZE,
    MINIMUM_PAGE_SIZE,
    offset_of,
)
from app.application.catalogue.locator import (
    MAXIMUM_LOCATOR_SEARCH_LENGTH,
    MINIMUM_LOCATOR_SEARCH_LENGTH,
)
from app.domain.asset_transitions import transitions_by_hand
from app.domain.enums import (
    AssetStatus,
    ConditionGrade,
    DamageSeverity,
    DamageStatus,
    ReleaseReason,
)


class AssetHistoryKind(str, Enum):
    """Where an entry of a unit's history comes from."""

    ALLOCATION = "ALLOCATION"
    RENTAL = "RENTAL"
    DAMAGE_REPORT = "DAMAGE_REPORT"
    AUDIT_EVENT = "AUDIT_EVENT"


@dataclass(frozen=True, slots=True)
class AdminAssetSearch:
    """Which units to list, and which page of them, in tag order.

    Attributes:
        text: Part of the tag, the serial number or the model name, or None.
        branch_id: Only the units this branch holds, or None for every branch.
        status: Only the units in this status, or None for every status.
        model_id: Only the units of this model, or None for every model.
        page: The page, counted from one.
        page_size: How many units a page holds.

    """

    text: str | None
    branch_id: UUID | None
    status: AssetStatus | None
    model_id: UUID | None
    page: int
    page_size: int

    def __post_init__(self) -> None:
        """Refuse a search no caller should be able to build.

        The HTTP boundary holds the same limits and answers a 422. This is the
        second line, so nothing inside the system can ask for the whole fleet
        at once or hand a query object a negative offset.

        Raises:
            ValueError: If the text, the page or its size is out of range.

        """
        if self.text is not None and not (
            MINIMUM_LOCATOR_SEARCH_LENGTH <= len(self.text) <= MAXIMUM_LOCATOR_SEARCH_LENGTH
        ):
            raise ValueError(
                f"Attempted to search the register with {len(self.text)} characters. A search "
                f"has between {MINIMUM_LOCATOR_SEARCH_LENGTH} and "
                f"{MAXIMUM_LOCATOR_SEARCH_LENGTH}."
            )
        if not FIRST_PAGE <= self.page <= MAXIMUM_PAGE:
            raise ValueError(
                f"Attempted to list units for page {self.page}. A page is between {FIRST_PAGE} "
                f"and {MAXIMUM_PAGE}."
            )
        if not MINIMUM_PAGE_SIZE <= self.page_size <= MAXIMUM_PAGE_SIZE:
            raise ValueError(
                f"Attempted to list units with a page size of {self.page_size}. A page holds "
                f"between {MINIMUM_PAGE_SIZE} and {MAXIMUM_PAGE_SIZE}."
            )

    @property
    def offset(self) -> int:
        """Return how many units come before the first one on the page."""
        return offset_of(self.page, self.page_size)


@dataclass(frozen=True, slots=True)
class AdminAssetEntry:
    """One unit as the register shows it, retired or not.

    Attributes:
        id: The asset key.
        asset_tag: The tag painted on the unit.
        model_id: The model it realises.
        model_name: That model's name.
        model_slug: That model's slug.
        category_name: The name of the model's category.
        branch_code: The branch that holds it.
        branch_name: That branch's name.
        serial_number: The manufacturer's serial number, or None.
        status: Where it is in its lifecycle.
        condition_grade: The grade it is in.
        acquired_on: The day it was acquired.
        acquisition_cost: What it cost, excluding VAT.
        hour_meter_reading: The last meter reading, or None.
        notes: What the office keeps about it, or None.
        retired_on: The day it was retired, or None.
        active_allocation_count: The bookings that hold it now.
        open_damage_reports: Its damage reports that are open or under repair.

    """

    id: UUID
    asset_tag: str
    model_id: UUID
    model_name: str
    model_slug: str
    category_name: str
    branch_code: str
    branch_name: str
    serial_number: str | None
    status: AssetStatus
    condition_grade: ConditionGrade
    acquired_on: date
    acquisition_cost: Decimal
    hour_meter_reading: int | None
    notes: str | None
    retired_on: date | None
    active_allocation_count: int
    open_damage_reports: int

    @property
    def allowed_transitions(self) -> tuple[AssetStatus, ...]:
        """Return the statuses an administrator may move the unit to, from the lifecycle rules.

        A unit with a damage report still open is not offered the move back to
        service, because the move is refused until the report is resolved, and
        a button that can only fail helps nobody. Retiring stays on offer while
        a booking holds the unit, because its refusal names the booking that
        has to be dealt with first (US-32).
        """
        moves = transitions_by_hand(self.status)
        if self.open_damage_reports > 0:
            return tuple(move for move in moves if move is not AssetStatus.AVAILABLE)
        return moves


@dataclass(frozen=True, slots=True)
class AdminAssetPage:
    """One page of the units, in tag order, and how many match across every page."""

    items: tuple[AdminAssetEntry, ...]
    page: int
    page_size: int
    total: int


@dataclass(frozen=True, slots=True)
class AllocationFact:
    """One time a booking held the unit.

    Attributes:
        allocated_at: When the unit was held.
        released_at: When it was let go, or None while it is held.
        release_reason: Why it was let go, or None while it is held.
        reservation_reference: The booking that held it.
        start_date: The first day of the hire.
        end_date: The day it ends, which is the day the unit is free again.

    """

    allocated_at: datetime
    released_at: datetime | None
    release_reason: ReleaseReason | None
    reservation_reference: str
    start_date: date
    end_date: date


@dataclass(frozen=True, slots=True)
class HireFact:
    """One time the unit went out on hire.

    Attributes:
        checked_out_at: When it was handed over.
        returned_at: When it came back or was recorded as lost, or None while out.
        rental_reference: The rental it went out on.
        condition_out: The grade it went out in.
        condition_in: The grade it came back in, or None while out or when lost.
        due_back_on: The day it was due back.

    """

    checked_out_at: datetime
    returned_at: datetime | None
    rental_reference: str
    condition_out: ConditionGrade
    condition_in: ConditionGrade | None
    due_back_on: date


@dataclass(frozen=True, slots=True)
class DamageFact:
    """One damage report of the unit.

    Attributes:
        reported_at: When it was filed.
        resolved_at: When it was resolved or written off, or None while open.
        reference: The report's reference.
        severity: How bad the damage was.
        status: Where the report stands.

    """

    reported_at: datetime
    resolved_at: datetime | None
    reference: str
    severity: DamageSeverity
    status: DamageStatus


@dataclass(frozen=True, slots=True)
class AuditFact:
    """One audit event about the unit, with the parts of its states the history reads.

    Attributes:
        occurred_at: When it happened.
        action: The name of the change, for example `asset.status_changed`.
        before_status: The status the unit moved from, or None.
        after_status: The status it moved to, or None.
        reason: The reason the administrator gave, or None.
        reference: The rental or damage report the change belongs to, or None.
        changed_fields: The fields an edit changed, in the order it named them.

    """

    occurred_at: datetime
    action: str
    before_status: str | None
    after_status: str | None
    reason: str | None
    reference: str | None
    changed_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AssetHistoryFacts:
    """Every fact the history of one unit is built from, each the newest first and bounded."""

    allocations: tuple[AllocationFact, ...]
    hires: tuple[HireFact, ...]
    damage_reports: tuple[DamageFact, ...]
    audit_events: tuple[AuditFact, ...]


@dataclass(frozen=True, slots=True)
class AssetHistoryEntry:
    """One line of a unit's history.

    Attributes:
        at: When it happened.
        kind: Where it comes from.
        summary: What happened, in a sentence.
        reference: The booking, rental or damage report it belongs to, or None.

    """

    at: datetime
    kind: AssetHistoryKind
    summary: str
    reference: str | None


@dataclass(frozen=True, slots=True)
class AdminAssetDetail:
    """One unit as the register shows it, with its history, the newest first."""

    entry: AdminAssetEntry
    history: tuple[AssetHistoryEntry, ...]
