"""The damage report, which is FR-20, US-24 and US-38 (BR-35 to BR-40).

A damage report records that a unit was found damaged, what it will cost to
put right, and whether the customer is charged for it. Whether the customer is
charged is a decision made on every report and never a default (BR-40), so
`chargeable_to_customer` has no default here, in the request or in the schema.
Fair wear and tear is not charged.

A report is OPEN when it is filed. An administrator sends it for repair, which
makes it UNDER_REPAIR, and closes it as RESOLVED, with the actual cost of the
repair, or as WRITTEN_OFF, which retires the unit (BR-38). The moves are
listed once, in `PERMITTED_REPORT_MOVES`, and a move the list does not hold is
a `StateTransitionError`, which the API answers with 409. A closed report never
moves again.

A report is numbered from a database sequence, in the form TSH-D-26-00031,
which names the year it was filed in.

What a report does to its unit is in `app.domain.damage_units`, what it
recovers from the customer in `app.domain.damage_recovery`, and the filing
that puts the two together in `app.domain.damage_filing`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Final
from uuid import UUID, uuid4

from app.domain.customer_account import REFUSED_FIELD
from app.domain.enums import DamageSeverity, DamageStatus
from app.domain.errors import StateTransitionError, ValidationFailure
from app.domain.money import Money

DAMAGE_REFERENCE_PREFIX: Final[str] = "TSH-D"
REFERENCE_YEAR_MODULUS: Final[int] = 100
REPAIR_RULE: Final[str] = "BR-38"
ACTUAL_COST_FIELD: Final[str] = "actual_repair_cost"
ACTUAL_COST_REQUIRED_MESSAGE: Final[str] = (
    "Enter what the repair actually cost. A report is resolved with its actual cost."
)
NEGATIVE_COST_MESSAGE: Final[str] = "A repair cost cannot be less than R0.00."

# Every permitted move of a report, from each status to the statuses it may lead to.
PERMITTED_REPORT_MOVES: Final[Mapping[DamageStatus, frozenset[DamageStatus]]] = (
    MappingProxyType(
        {
            DamageStatus.OPEN: frozenset(
                {DamageStatus.UNDER_REPAIR, DamageStatus.RESOLVED, DamageStatus.WRITTEN_OFF}
            ),
            DamageStatus.UNDER_REPAIR: frozenset(
                {DamageStatus.RESOLVED, DamageStatus.WRITTEN_OFF}
            ),
            DamageStatus.RESOLVED: frozenset(),
            DamageStatus.WRITTEN_OFF: frozenset(),
        }
    )
)
# The statuses of a report that is still being dealt with.
OPEN_REPORT_STATUSES: Final[frozenset[DamageStatus]] = frozenset(
    {DamageStatus.OPEN, DamageStatus.UNDER_REPAIR}
)
# The two outcomes an administrator closes a report with.
CLOSING_STATUSES: Final[frozenset[DamageStatus]] = frozenset(
    {DamageStatus.RESOLVED, DamageStatus.WRITTEN_OFF}
)
# Where a report stands, and what a move to each status would have done, in words.
REPORT_STANDING_IN_WORDS: Final[Mapping[DamageStatus, str]] = MappingProxyType(
    {
        DamageStatus.OPEN: "open",
        DamageStatus.UNDER_REPAIR: "already under repair",
        DamageStatus.RESOLVED: "resolved",
        DamageStatus.WRITTEN_OFF: "written off",
    }
)
REPORT_MOVE_IN_WORDS: Final[Mapping[DamageStatus, str]] = MappingProxyType(
    {
        DamageStatus.OPEN: "opened again",
        DamageStatus.UNDER_REPAIR: "sent for repair",
        DamageStatus.RESOLVED: "resolved",
        DamageStatus.WRITTEN_OFF: "written off",
    }
)


def format_damage_reference(year: int, sequence_value: int) -> str:
    """Return a damage report reference, for example TSH-D-26-00031.

    Args:
        year: The calendar year the report is filed in. Only its last two
            digits are used, the way a rental reference uses them.
        sequence_value: The next value of the damage report sequence.

    """
    return f"{DAMAGE_REFERENCE_PREFIX}-{year % REFERENCE_YEAR_MODULUS:02d}-{sequence_value:05d}"


def report_may_move(current: DamageStatus, target: DamageStatus) -> bool:
    """Return True when a report may move from one status to another."""
    return target in PERMITTED_REPORT_MOVES[current]


@dataclass(slots=True)
class DamageReport:
    """A record that a unit was found damaged, and what was decided about it.

    Attributes:
        reference: The reference the counter quotes, for example TSH-D-26-00031.
        asset_id: The unit that is damaged.
        rental_item_id: The hire it came back from, or None when the damage
            was found outside a hire.
        severity: How bad the damage is.
        description: What is wrong with the unit.
        repair_estimate: What the repair is expected to cost.
        chargeable_to_customer: Whether the customer is charged. It has no
            default, because it is decided on every report (BR-40).
        reported_by_user_id: The member of staff who filed it.
        reported_at: When it was filed, from the clock.
        status: Where the report stands.
        actual_repair_cost: What the repair cost, once it is resolved.
        resolved_at: When it was resolved or written off.
        resolution_notes: What the administrator wrote when closing it.
        id: The report key, generated here so it is known before the insert.

    """

    reference: str
    asset_id: UUID
    rental_item_id: UUID | None
    severity: DamageSeverity
    description: str
    repair_estimate: Decimal
    chargeable_to_customer: bool
    reported_by_user_id: UUID
    reported_at: datetime
    status: DamageStatus = DamageStatus.OPEN
    actual_repair_cost: Decimal | None = None
    resolved_at: datetime | None = None
    resolution_notes: str | None = None
    id: UUID = field(default_factory=uuid4)

    def is_open(self) -> bool:
        """Return True while the report is still being dealt with."""
        return self.status in OPEN_REPORT_STATUSES

    def send_for_repair(self) -> None:
        """Move an open report to UNDER_REPAIR.

        Raises:
            StateTransitionError: If the report is not OPEN.

        """
        self._ensure_may_move_to(DamageStatus.UNDER_REPAIR)
        self.status = DamageStatus.UNDER_REPAIR

    def close(
        self,
        outcome: DamageStatus,
        *,
        actual_repair_cost: Money | None,
        notes: str | None,
        now: datetime,
    ) -> None:
        """Close the report as RESOLVED, with what the repair cost, or as WRITTEN_OFF.

        Args:
            outcome: RESOLVED or WRITTEN_OFF.
            actual_repair_cost: What the repair cost. Required to resolve, and
                kept when given for a write off.
            notes: What the administrator wrote, or None.
            now: The current instant, from the clock.

        Raises:
            ValueError: If the outcome is not one that closes a report, which
                means the calling code built the request wrongly.
            ValidationFailure: If a report is resolved with no cost, or a cost
                is below nothing. The detail names `actual_repair_cost`.
            StateTransitionError: If the report is already closed.

        """
        if outcome not in CLOSING_STATUSES:
            raise ValueError(
                f"Attempted to close report {self.reference} as {outcome.value}. A report is "
                "closed as RESOLVED or WRITTEN_OFF."
            )
        if actual_repair_cost is None and outcome is DamageStatus.RESOLVED:
            raise _refused_cost(ACTUAL_COST_REQUIRED_MESSAGE)
        if actual_repair_cost is not None and actual_repair_cost.is_negative():
            raise _refused_cost(NEGATIVE_COST_MESSAGE)
        self._ensure_may_move_to(outcome)
        written = (notes or "").strip()
        self.status = outcome
        self.actual_repair_cost = (
            actual_repair_cost.rounded().amount if actual_repair_cost is not None else None
        )
        self.resolution_notes = written or None
        self.resolved_at = now

    def _ensure_may_move_to(self, target: DamageStatus) -> None:
        """Refuse a move the report's status does not permit.

        Raises:
            StateTransitionError: Naming the report, where it stands and the move.

        """
        if report_may_move(self.status, target):
            return
        raise StateTransitionError(
            f"Report {self.reference} is {REPORT_STANDING_IN_WORDS[self.status]}, so it "
            f"cannot be {REPORT_MOVE_IN_WORDS[target]}.",
            from_status=self.status.value,
            to_status=target.value,
            rule=REPAIR_RULE,
        )


def _refused_cost(message: str) -> ValidationFailure:
    """Return the refusal of the actual repair cost."""
    return ValidationFailure(message, {REFUSED_FIELD: ACTUAL_COST_FIELD}, rule=REPAIR_RULE)
