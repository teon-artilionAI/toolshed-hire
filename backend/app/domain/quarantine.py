"""Whether a unit that comes back goes to quarantine and waits for an assessment (BR-35).

A unit that came back in a worse grade than it went out in, or that the
counter flagged, goes to QUARANTINED instead of AVAILABLE in the transaction
of its return, so it leaves availability at once. Grade A is the best and C
the worst. A unit out in A and back in B is worse, and one out in B and back
in A is not.

Such a unit waits for its damage to be assessed. Its assessment is REQUIRED
until a damage report names it, and DONE from then on. A unit that came back
as it went out, and was not flagged, needs none. A unit still out, or one
recorded as lost, waits for nothing here, because nobody has inspected it. A
report that names any unit makes its assessment DONE.

The return records the counter's flag on the rental item as
`flagged_for_damage`, beside the grade it came back in, and every later
question about the unit reads it from there. The notes keep what the counter
wrote and decide nothing.

How many units of a rental still wait is `assessments_due_on`. It is the
number the settlement asks before it lets the deposit go (BR-32).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from app.domain.enums import AssetStatus, ConditionGrade
from app.domain.rental import DamageAssessment, Rental, RentalItem

# The grades from the best to the worst. A higher rank is a worse grade.
GRADE_RANK: Final[Mapping[ConditionGrade, int]] = MappingProxyType(
    {ConditionGrade.A: 0, ConditionGrade.B: 1, ConditionGrade.C: 2}
)


def came_back_worse(condition_out: ConditionGrade, condition_in: ConditionGrade) -> bool:
    """Return True when a unit came back in a worse grade than it went out in."""
    return GRADE_RANK[condition_in] > GRADE_RANK[condition_out]


def goes_to_quarantine(
    *, condition_out: ConditionGrade, condition_in: ConditionGrade, flagged: bool
) -> bool:
    """Return True when a unit coming back has to go to quarantine (BR-35).

    Args:
        condition_out: The grade it went out in.
        condition_in: The grade it came back in.
        flagged: Whether the counter flagged it for a damage assessment.

    """
    return flagged or came_back_worse(condition_out, condition_in)


def status_on_return(
    condition_out: ConditionGrade, condition_in: ConditionGrade, flagged: bool
) -> AssetStatus:
    """Return the status a unit takes as it comes back, QUARANTINED or AVAILABLE (BR-35)."""
    if goes_to_quarantine(condition_out=condition_out, condition_in=condition_in, flagged=flagged):
        return AssetStatus.QUARANTINED
    return AssetStatus.AVAILABLE


def damage_assessment_of(
    *,
    condition_out: ConditionGrade,
    condition_in: ConditionGrade | None,
    flagged: bool,
    reported: bool,
) -> DamageAssessment:
    """Return whether a unit of a rental waits for its damage to be assessed.

    Args:
        condition_out: The grade it went out in.
        condition_in: The grade it came back in, or None while it is out and
            for a unit recorded as lost.
        flagged: Whether the counter flagged it as it came back.
        reported: Whether a damage report names it.

    """
    if reported:
        return DamageAssessment.DONE
    if condition_in is None:
        return DamageAssessment.NOT_NEEDED
    if goes_to_quarantine(condition_out=condition_out, condition_in=condition_in, flagged=flagged):
        return DamageAssessment.REQUIRED
    return DamageAssessment.NOT_NEEDED


def assessment_of(item: RentalItem) -> DamageAssessment:
    """Return whether one unit of a rental read for a change waits for its assessment."""
    return damage_assessment_of(
        condition_out=item.condition_out,
        condition_in=item.condition_in,
        flagged=item.flagged_for_damage,
        reported=item.damage_reported,
    )


def assessments_due_on(rental: Rental) -> int:
    """Return how many units of a rental came back and still wait for their assessment."""
    return sum(assessment_of(item) is DamageAssessment.REQUIRED for item in rental.items)
