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

The schema has no column for the counter's flag, so I keep the flag where the
schema keeps what the counter says about a unit, in the notes of its rental
item. The notes of a flagged unit begin with `FLAGGED_NOTE`, followed by
anything the counter wrote, and `was_flagged` reads the flag back from there.
Nothing else writes that sentence, and the notes are never shown to a client.

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
FLAGGED_NOTE: Final[str] = "Flagged for a damage assessment at return."
NOTE_SEPARATOR: Final[str] = "\n"


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


def notes_on_return(notes: str | None, *, flagged: bool) -> str | None:
    """Return the notes a unit is stored with as it comes back, with the flag when it was flagged.

    Args:
        notes: What the counter wrote about the unit, or None.
        flagged: Whether the counter flagged it for a damage assessment.

    Returns:
        The counter's notes without surrounding space, after `FLAGGED_NOTE`
        on a line of its own when the unit was flagged, or None when there is
        nothing to keep.

    """
    written = (notes or "").strip()
    if not flagged:
        return written or None
    return NOTE_SEPARATOR.join(part for part in (FLAGGED_NOTE, written) if part)


def was_flagged(notes: str | None) -> bool:
    """Return True when the stored notes of a unit say the counter flagged it."""
    return notes is not None and notes.startswith(FLAGGED_NOTE)


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
        flagged=was_flagged(item.notes),
        reported=item.damage_reported,
    )


def assessments_due_on(rental: Rental) -> int:
    """Return how many units of a rental came back and still wait for their assessment."""
    return sum(assessment_of(item) is DamageAssessment.REQUIRED for item in rental.items)
