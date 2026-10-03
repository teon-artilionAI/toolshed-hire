"""Which unit coming back goes to quarantine and waits for an assessment, with no database (BR-35).

The decision is a function of the two grades and the counter's flag. A worse
grade or the flag alone sends the unit to QUARANTINED, and the unit waits for
its assessment until a damage report names it. These pin the decision for each
pair of grades the brief names, that the flag is kept on the item apart from
the notes, and what a return through the domain does with both.
"""

from __future__ import annotations

import pytest

from app.domain.enums import AssetStatus, ConditionGrade
from app.domain.quarantine import (
    assessment_of,
    assessments_due_on,
    damage_assessment_of,
    goes_to_quarantine,
    status_on_return,
)
from app.domain.rental import DamageAssessment
from tests.support.reservations import NINTH
from tests.support.return_domain import TWO_UNITS, a_hire, back, returned

A, B, C = ConditionGrade.A, ConditionGrade.B, ConditionGrade.C


class TestTheQuarantineDecision:
    """A worse grade or the flag, and nothing else, sends a unit to quarantine."""

    @pytest.mark.parametrize(
        ("out", "back_in", "flagged", "quarantined"),
        [
            (A, A, False, False),
            (A, B, False, True),
            (A, C, False, True),
            (B, A, False, False),
            (B, B, False, False),
            (C, C, True, True),
            (A, A, True, True),
        ],
        ids=["A to A", "A to B", "A to C", "B to A", "B to B", "C to C flagged", "flag alone"],
    )
    def test_the_two_grades_and_the_flag_decide(
        self, out: ConditionGrade, back_in: ConditionGrade, flagged: bool, quarantined: bool
    ) -> None:
        decided = goes_to_quarantine(condition_out=out, condition_in=back_in, flagged=flagged)
        assert decided is quarantined
        expected = AssetStatus.QUARANTINED if quarantined else AssetStatus.AVAILABLE
        assert status_on_return(out, back_in, flagged) is expected


class TestTheFlagOnTheItem:
    """The flag is its own field on the item, and the notes never decide anything."""

    @pytest.mark.parametrize(
        ("notes", "flagged", "assessment"),
        [
            ("Cracked guard", True, DamageAssessment.REQUIRED),
            (None, True, DamageAssessment.REQUIRED),
            ("Flagged for a damage assessment at return.", False, DamageAssessment.NOT_NEEDED),
            (None, False, DamageAssessment.NOT_NEEDED),
        ],
        ids=["flagged with notes", "flagged alone", "words in the notes", "neither"],
    )
    def test_the_flag_and_not_the_notes_decides_the_assessment(
        self, notes: str | None, flagged: bool, assessment: DamageAssessment
    ) -> None:
        hire = a_hire()
        (closed,) = returned(hire, NINTH, back(hire, notes=notes, flagged_for_damage=flagged)).units
        assert (closed.item.flagged_for_damage, closed.item.notes) == (flagged, notes)
        assert assessment_of(closed.item) is assessment


class TestTheAssessment:
    """REQUIRED until a report names the unit, DONE after, NOT_NEEDED otherwise."""

    @pytest.mark.parametrize(
        ("back_in", "flagged", "reported", "assessment"),
        [
            (B, False, False, DamageAssessment.REQUIRED),
            (A, True, False, DamageAssessment.REQUIRED),
            (B, False, True, DamageAssessment.DONE),
            (A, False, True, DamageAssessment.DONE),
            (A, False, False, DamageAssessment.NOT_NEEDED),
            (None, False, False, DamageAssessment.NOT_NEEDED),
        ],
        ids=["worse", "flagged", "worse and reported", "reported", "as it went", "still out"],
    )
    def test_the_assessment_follows_the_return_and_the_report(
        self,
        back_in: ConditionGrade | None,
        flagged: bool,
        reported: bool,
        assessment: DamageAssessment,
    ) -> None:
        found = damage_assessment_of(
            condition_out=A, condition_in=back_in, flagged=flagged, reported=reported
        )
        assert found is assessment


class TestAReturnThroughTheDomain:
    """The return quarantines what the decision says, and the rental counts what waits."""

    def test_a_unit_back_worse_is_quarantined_and_waits(self) -> None:
        hire = a_hire(TWO_UNITS)
        outcome = returned(hire, NINTH, [*back(hire, 0, condition_in=B), *back(hire, 1)])
        statuses = [closed.unit.status for closed in outcome.units]
        assert statuses == [AssetStatus.QUARANTINED, AssetStatus.AVAILABLE]
        assert outcome.units[0].unit.condition_grade is B
        assert assessments_due_on(hire.rental) == 1

    def test_a_flagged_unit_is_quarantined_with_the_flag_and_its_notes_as_written(self) -> None:
        hire = a_hire()
        (closed,) = returned(hire, NINTH, back(hire, flagged_for_damage=True, notes="Smells")).units
        assert closed.unit.status is AssetStatus.QUARANTINED
        assert (closed.item.flagged_for_damage, closed.item.notes) == (True, "Smells")
        assert assessments_due_on(hire.rental) == 1

    def test_a_report_naming_the_unit_lifts_the_wait(self) -> None:
        hire = a_hire()
        returned(hire, NINTH, back(hire, condition_in=C))
        hire.rental.items[0].damage_reported = True
        assert assessments_due_on(hire.rental) == 0
