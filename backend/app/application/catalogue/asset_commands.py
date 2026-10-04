"""What an administrator asks of the asset register, as the use cases are handed it (FR-23, US-31).

A registration names every field. An edit names only the paperwork the request
sent, and each of those arrives as a `Change`, so a field left out keeps its
value and a field sent as null is cleared, which only the serial number, the
meter reading and the notes allow. The tag, the model and the branch are not
among the changes, because none of them ever changes (BR-34).

A unit is named by its tag, which is what the office knows it by and what is
painted on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.catalogue.admin_commands import Change, chosen
from app.domain.asset_register import NewUnitTerms, UnitDetails
from app.domain.enums import AssetStatus, ConditionGrade
from app.domain.identity import Actor


@dataclass(frozen=True, slots=True)
class RegisterUnitCommand:
    """A request to register a unit. A new unit starts at INTAKE.

    Attributes:
        actor: The administrator registering it.
        model_id: The product model it realises.
        branch_code: The code of the branch that holds it.
        terms: The tag, the acquisition and the paperwork.

    """

    actor: Actor
    model_id: UUID
    branch_code: str
    terms: NewUnitTerms


@dataclass(frozen=True, slots=True)
class UnitChanges:
    """The paperwork of a unit an edit names, each None when it was left out."""

    serial_number: Change[str | None] | None = None
    condition_grade: Change[ConditionGrade] | None = None
    hour_meter_reading: Change[int | None] | None = None
    notes: Change[str | None] | None = None

    def applied_to(self, details: UnitDetails) -> UnitDetails:
        """Return the paperwork with every named field changed and the rest as it was."""
        return UnitDetails(
            serial_number=chosen(details.serial_number, self.serial_number),
            condition_grade=chosen(details.condition_grade, self.condition_grade),
            hour_meter_reading=chosen(details.hour_meter_reading, self.hour_meter_reading),
            notes=chosen(details.notes, self.notes),
        )


@dataclass(frozen=True, slots=True)
class EditUnitCommand:
    """A request to change the paperwork of a unit.

    Attributes:
        actor: The administrator editing it.
        asset_tag: The tag of the unit.
        changes: The fields the request named.

    """

    actor: Actor
    asset_tag: str
    changes: UnitChanges


@dataclass(frozen=True, slots=True)
class MoveUnitCommand:
    """A request to move a unit through its lifecycle by hand.

    Attributes:
        actor: The administrator moving it.
        asset_tag: The tag of the unit.
        target: The status it is to move to.
        reason: Why, or None. Required to take a unit out of service.

    """

    actor: Actor
    asset_tag: str
    target: AssetStatus
    reason: str | None
