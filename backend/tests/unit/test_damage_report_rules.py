"""The rules of a damage report on their own, with no database (BR-37 to BR-40).

The moves of a report's status, what closing it asks for, what each move does
to the unit, the reference, and the two rules of a recovery, which are that
the amount follows from the chargeable decision and that it never passes the
replacement value. The cap is asked below, at and above the value, and again
once part of the value has already been recovered.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Final
from uuid import uuid4

import pytest

from app.application.hire.damage_models import DamageReportKey, DamageReportSearch
from app.domain.catalogue import Asset
from app.domain.damage import DamageReport, format_damage_reference, report_may_move
from app.domain.damage_recovery import (
    ensure_recovery_decided,
    ensure_recovery_within_cap,
    recovery_cap,
)
from app.domain.damage_units import (
    back_in_service,
    quarantined_for_report,
    retired,
    sent_for_repair,
)
from app.domain.enums import AssetStatus, ConditionGrade, DamageSeverity, DamageStatus
from app.domain.errors import StateTransitionError, ValidationFailure
from app.domain.money import Money

NOW: Final[datetime] = datetime(2026, 3, 14, 8, 0, tzinfo=UTC)
TODAY: Final[date] = date(2026, 3, 14)
VALUE: Final[Money] = Money.create("4200.00")
NOTHING: Final[Money] = Money.zero()
OPEN, UNDER_REPAIR = DamageStatus.OPEN, DamageStatus.UNDER_REPAIR
RESOLVED, WRITTEN_OFF = DamageStatus.RESOLVED, DamageStatus.WRITTEN_OFF


def a_report(status: DamageStatus = OPEN) -> DamageReport:
    """Return a report in a status, as it would be filed."""
    return DamageReport(
        reference="TSH-D-26-00031",
        asset_id=uuid4(),
        rental_item_id=None,
        severity=DamageSeverity.MINOR,
        description="Cracked housing",
        repair_estimate=Decimal("450.00"),
        chargeable_to_customer=False,
        reported_by_user_id=uuid4(),
        reported_at=NOW,
        status=status,
    )


def a_unit(status: AssetStatus) -> Asset:
    """Return a unit in a status."""
    return Asset(
        id=uuid4(),
        asset_tag="TSH-DR-0042",
        product_model_id=uuid4(),
        branch_id=uuid4(),
        status=status,
        condition_grade=ConditionGrade.B,
    )


class TestTheStatusMoves:
    """OPEN to UNDER_REPAIR, either of them to a close, and nothing out of a close."""

    @pytest.mark.parametrize(
        ("current", "target", "permitted"),
        [
            (OPEN, UNDER_REPAIR, True),
            (OPEN, RESOLVED, True),
            (OPEN, WRITTEN_OFF, True),
            (UNDER_REPAIR, RESOLVED, True),
            (UNDER_REPAIR, WRITTEN_OFF, True),
            (UNDER_REPAIR, UNDER_REPAIR, False),
            (UNDER_REPAIR, OPEN, False),
            (RESOLVED, UNDER_REPAIR, False),
            (RESOLVED, WRITTEN_OFF, False),
            (WRITTEN_OFF, RESOLVED, False),
        ],
    )
    def test_only_the_listed_moves_are_permitted(
        self, current: DamageStatus, target: DamageStatus, permitted: bool
    ) -> None:
        assert report_may_move(current, target) is permitted

    def test_an_open_report_goes_for_repair_and_one_under_repair_does_not_go_again(self) -> None:
        report = a_report()
        report.send_for_repair()
        assert report.status is UNDER_REPAIR and report.is_open()
        with pytest.raises(StateTransitionError, match="already under repair"):
            report.send_for_repair()

    def test_resolving_keeps_the_cost_the_notes_and_the_time(self) -> None:
        report = a_report(UNDER_REPAIR)
        report.close(RESOLVED, actual_repair_cost=Money.create("380"), notes=" New guard ", now=NOW)
        assert (report.status, report.actual_repair_cost) == (RESOLVED, Decimal("380.00"))
        assert (report.resolution_notes, report.resolved_at, report.is_open()) == (
            "New guard", NOW, False
        )

    def test_a_write_off_needs_no_cost(self) -> None:
        report = a_report()
        report.close(WRITTEN_OFF, actual_repair_cost=None, notes=None, now=NOW)
        assert (report.status, report.actual_repair_cost, report.resolution_notes) == (
            WRITTEN_OFF, None, None
        )

    @pytest.mark.parametrize(
        ("outcome", "cost", "message"),
        [
            (RESOLVED, None, "actually cost"),
            (RESOLVED, Money.create("-1"), "less than R0.00"),
            (WRITTEN_OFF, Money.create("-0.01"), "less than R0.00"),
        ],
    )
    def test_a_close_with_a_wrong_cost_is_refused_by_its_field(
        self, outcome: DamageStatus, cost: Money | None, message: str
    ) -> None:
        with pytest.raises(ValidationFailure, match=message) as refused:
            a_report().close(outcome, actual_repair_cost=cost, notes=None, now=NOW)
        assert refused.value.detail == {"field": "actual_repair_cost"}

    def test_a_closed_report_is_never_closed_again(self) -> None:
        with pytest.raises(StateTransitionError, match="is resolved, so it cannot be written off"):
            a_report(RESOLVED).close(WRITTEN_OFF, actual_repair_cost=None, notes=None, now=NOW)

    def test_an_outcome_that_does_not_close_is_a_fault_in_the_caller(self) -> None:
        with pytest.raises(ValueError, match="RESOLVED or WRITTEN_OFF"):
            a_report().close(UNDER_REPAIR, actual_repair_cost=None, notes=None, now=NOW)


class TestWhatAReportDoesToItsUnit:
    """Out of availability when filed, back on the shelf or retired when closed."""

    @pytest.mark.parametrize(
        ("status", "after"),
        [
            (AssetStatus.AVAILABLE, AssetStatus.QUARANTINED),
            (AssetStatus.LOST, AssetStatus.QUARANTINED),
            (AssetStatus.QUARANTINED, AssetStatus.QUARANTINED),
            (AssetStatus.UNDER_REPAIR, AssetStatus.UNDER_REPAIR),
        ],
    )
    def test_filing_takes_the_unit_out_of_availability(
        self, status: AssetStatus, after: AssetStatus
    ) -> None:
        assert quarantined_for_report(a_unit(status)).status is after

    @pytest.mark.parametrize(
        ("status", "message"),
        [(AssetStatus.ON_HIRE, "out on hire"), (AssetStatus.RETIRED, "is retired")],
    )
    def test_a_unit_on_hire_or_retired_is_refused(self, status: AssetStatus, message: str) -> None:
        with pytest.raises(StateTransitionError, match=message):
            quarantined_for_report(a_unit(status))

    def test_repair_moves_the_unit_unless_it_is_there_already(self) -> None:
        assert sent_for_repair(a_unit(AssetStatus.QUARANTINED)).status is AssetStatus.UNDER_REPAIR
        assert sent_for_repair(a_unit(AssetStatus.UNDER_REPAIR)).status is AssetStatus.UNDER_REPAIR

    @pytest.mark.parametrize(
        ("status", "others", "after"),
        [
            (AssetStatus.UNDER_REPAIR, 0, AssetStatus.AVAILABLE),
            (AssetStatus.QUARANTINED, 0, AssetStatus.AVAILABLE),
            (AssetStatus.QUARANTINED, 1, AssetStatus.QUARANTINED),
            (AssetStatus.RETIRED, 0, AssetStatus.RETIRED),
        ],
    )
    def test_resolving_puts_the_unit_back_once_nothing_else_holds_it(
        self, status: AssetStatus, others: int, after: AssetStatus
    ) -> None:
        assert back_in_service(a_unit(status), other_open_reports=others).status is after

    def test_a_write_off_retires_the_unit_on_the_day(self) -> None:
        unit = retired(a_unit(AssetStatus.UNDER_REPAIR), today=TODAY, holds_active_allocation=False)
        assert (unit.status, unit.retired_on) == (AssetStatus.RETIRED, TODAY)
        already = replace(unit, retired_on=date(2025, 1, 1))
        assert retired(already, today=TODAY, holds_active_allocation=False) == already

    def test_a_write_off_is_refused_while_a_booking_holds_the_unit(self) -> None:
        with pytest.raises(StateTransitionError, match="held for a booking"):
            retired(a_unit(AssetStatus.QUARANTINED), today=TODAY, holds_active_allocation=True)


class TestTheRecoveryCap:
    """Below, at and above the replacement value, and what was already recovered (BR-39)."""

    @pytest.mark.parametrize("amount", ["450.00", "4199.99", "4200.00"])
    def test_an_amount_up_to_the_value_is_accepted(self, amount: str) -> None:
        ensure_recovery_within_cap(Money.create(amount), replacement_value=VALUE, already=NOTHING)

    def test_an_amount_above_the_value_is_refused_naming_the_most(self) -> None:
        with pytest.raises(ValidationFailure, match="more than R4200.00") as refused:
            ensure_recovery_within_cap(
                Money.create("4200.01"), replacement_value=VALUE, already=NOTHING
            )
        assert refused.value.detail == {"field": "recovery_amount"}

    def test_what_was_already_recovered_comes_off_the_cap(self) -> None:
        already = Money.create("4000.00")
        ensure_recovery_within_cap(Money.create("200.00"), replacement_value=VALUE, already=already)
        with pytest.raises(ValidationFailure, match="R4000.00 of the replacement value"):
            ensure_recovery_within_cap(
                Money.create("200.01"), replacement_value=VALUE, already=already
            )

    def test_the_cap_is_never_below_nothing(self) -> None:
        cap = recovery_cap(replacement_value=VALUE, already=Money.create("5000.00"))
        assert cap == Money.zero().rounded()


class TestTheDecision:
    """The amount follows from the decision, and from whether there is a hire (BR-40)."""

    @pytest.mark.parametrize(
        ("chargeable", "on_a_hire", "amount", "message"),
        [
            (True, True, None, "Enter the amount to recover"),
            (False, True, "10.00", "not charged for this damage"),
            (True, False, "10.00", "outside a hire"),
            (True, True, "0.00", "above R0.00"),
        ],
    )
    def test_an_amount_that_does_not_follow_is_refused(
        self, chargeable: bool, on_a_hire: bool, amount: str | None, message: str
    ) -> None:
        recovery = None if amount is None else Money.create(amount)
        with pytest.raises(ValidationFailure, match=message):
            ensure_recovery_decided(
                chargeable=chargeable, names_rental_item=on_a_hire, recovery_amount=recovery
            )

    @pytest.mark.parametrize(
        ("chargeable", "on_a_hire", "amount"),
        [(True, True, "450.00"), (False, True, None), (True, False, None), (False, False, None)],
    )
    def test_an_amount_that_follows_is_accepted(
        self, chargeable: bool, on_a_hire: bool, amount: str | None
    ) -> None:
        recovery = None if amount is None else Money.create(amount)
        ensure_recovery_decided(
            chargeable=chargeable, names_rental_item=on_a_hire, recovery_amount=recovery
        )


class TestTheReferenceAndTheReads:
    """TSH-D-26-00031, a key or a reference, and a list that cannot ask for everything."""

    def test_the_reference_names_the_year_and_five_digits(self) -> None:
        assert format_damage_reference(2026, 31) == "TSH-D-26-00031"

    def test_a_report_is_named_by_its_key_or_its_reference(self) -> None:
        key = uuid4()
        assert DamageReportKey.parse(f" {key} ") == DamageReportKey(report_id=key)
        assert DamageReportKey.parse("tsh-d-26-00031") == DamageReportKey(
            reference="TSH-D-26-00031"
        )
        assert str(DamageReportKey.of(key)) == str(key)
        assert str(DamageReportKey.parse("tsh-d-26-00031")) == "TSH-D-26-00031"

    @pytest.mark.parametrize("bounds", [{"page": 0}, {"page_size": 0}, {"page_size": 51}])
    def test_a_search_out_of_bounds_cannot_be_built(self, bounds: dict[str, int]) -> None:
        with pytest.raises(ValueError, match="Attempted to list damage reports"):
            DamageReportSearch(**bounds)

    def test_a_search_knows_how_many_come_before_its_page(self) -> None:
        assert DamageReportSearch(page=3, page_size=20).offset == 40
