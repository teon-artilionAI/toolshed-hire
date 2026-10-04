"""What the report query object reads about the fleet, in small frozen dataclasses.

The query object answers in three parts, each read by one statement however
many units there are.

1. `UnitRow`, one for every unit in scope, with what it is, where it is, the
   status the recorded changes left it in on either side of the period, and
   the money charged on it directly within the period, summed in the database.
2. `DatedRow`, one for every dated fact about a unit that touches the period.
   A hire, a loss, a booking not yet collected, a damage report and a recorded
   change of status are each one row, told apart by `kind`.
3. `SharedHireRow`, one for every unit of every hire charge raised on a whole
   hire within the period, with what that unit's share is weighed by.

None of these works anything out. The days are counted and the shares are
taken in the domain, and `app.application.reporting.unit_figures` puts the
three parts together.

Money stays `Decimal` here, as it does in every read model (BR-22).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from app.domain.enums import AssetStatus


@dataclass(frozen=True, slots=True)
class ReportScope:
    """The period and the filters the fleet is read for.

    Attributes:
        starts_on: The first day of the period.
        ends_on: The first day after it, so the period is `[starts_on, ends_on)`.
        starts_at: The instant the first day begins in Cape Town, in UTC.
        ends_at: The instant the day after the period begins, in UTC.
        now: The current instant. A hold that has not run out by then still
            holds its unit.
        branch_id: Only the units held at this branch, or None for every branch.
        category_slug: Only the units of models in this category or its
            children, or None for every category.

    """

    starts_on: date
    ends_on: date
    starts_at: datetime
    ends_at: datetime
    now: datetime
    branch_id: UUID | None = None
    category_slug: str | None = None


@dataclass(frozen=True, slots=True)
class UnitRow:
    """One unit in scope, with its money of the period summed.

    Attributes:
        asset_id: The unit key.
        asset_tag: The tag painted on it.
        status: Its status now.
        acquired_on: The day it joined the fleet.
        retired_on: The day it left the fleet, or None.
        branch_code: The branch that holds it.
        branch_name: That branch's name.
        model_slug: The slug of its model.
        model_name: The name of its model.
        category_slug: The slug of its model's category.
        category_name: The name of that category.
        held_on_entry: The status the last recorded change before the period
            gave it, or None.
        held_on_exit: The status the first recorded change after the period
            moved it from, or None.
        hire_revenue: Hire charges raised on it alone within the period, ex VAT.
        late_fees: Late fees raised on it within the period, ex VAT.
        damage_recovery: Damage recovery and deposit kept for it within the period, ex VAT.
        repair_costs: The actual repair costs of its reports resolved within the period.

    """

    asset_id: UUID
    asset_tag: str
    status: AssetStatus
    acquired_on: date
    retired_on: date | None
    branch_code: str
    branch_name: str
    model_slug: str
    model_name: str
    category_slug: str
    category_name: str
    held_on_entry: AssetStatus | None
    held_on_exit: AssetStatus | None
    hire_revenue: Decimal
    late_fees: Decimal
    damage_recovery: Decimal
    repair_costs: Decimal


class EvidenceKind(str, Enum):
    """What a dated fact about a unit is."""

    HIRE = "HIRE"
    LOSS = "LOSS"
    BOOKING = "BOOKING"
    DAMAGE = "DAMAGE"
    STATUS = "STATUS"


@dataclass(frozen=True, slots=True)
class DatedRow:
    """One dated fact about a unit that touches the period.

    A hire runs from `began_at` to `ended_at`, which is None while the unit
    is out. A loss runs from when it was recorded to the next recorded change
    of status, or None. A damage report runs from when it was reported to when
    it was resolved, or None. A booking runs from `begins_on` to `ends_on`.
    A change of status happened at `began_at`, from one status to another.

    Attributes:
        asset_id: The unit.
        kind: What the fact is.
        began_at: When it began, for every kind but a booking.
        ended_at: When it ended, or None while it has not.
        begins_on: The first day of a booking.
        ends_on: The day after the last day of a booking.
        moved_from: The status a change moved the unit from.
        moved_to: The status a change moved the unit to.

    """

    asset_id: UUID
    kind: EvidenceKind
    began_at: datetime | None = None
    ended_at: datetime | None = None
    begins_on: date | None = None
    ends_on: date | None = None
    moved_from: AssetStatus | None = None
    moved_to: AssetStatus | None = None


@dataclass(frozen=True, slots=True)
class SharedHireRow:
    """One unit of a hire charge raised on a whole hire within the period.

    Attributes:
        charge_id: The charge, so the units of one charge can be kept together.
        amount_ex_vat: The charge excluding VAT, negative for a reversal.
        asset_id: The unit.
        line_amount: The amount of the booking line the unit was hired on, ex VAT.
        units_on_line: How many units that line books.

    """

    charge_id: UUID
    amount_ex_vat: Decimal
    asset_id: UUID
    line_amount: Decimal
    units_on_line: int


@dataclass(frozen=True, slots=True)
class FleetEvidence:
    """Everything the report reads about the fleet for one period.

    Attributes:
        units: Every unit in scope, in tag order.
        dated: Every dated fact about those units that touches the period.
        shared_hire: Every unit of every hire charge raised on a whole hire
            within the period, the units of a charge together and in the order
            its shares are taken, so the last takes the rounding cent. A unit
            outside the scope is still listed when it shares a charge with one
            inside it, so a unit's share is the same whatever the report is
            narrowed to.

    """

    units: tuple[UnitRow, ...]
    dated: tuple[DatedRow, ...]
    shared_hire: tuple[SharedHireRow, ...]
