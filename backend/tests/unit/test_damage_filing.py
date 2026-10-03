"""Filing a damage report, and the settlement waiting and resuming, with no database.

A hire is put out and taken back by the domain itself (`tests/support/return_domain.py`),
one grade worse, so its deposit waits for the assessment. Filing the report
completes the assessment, and the settlement the return uses then settles the
deposit with the recovery among what it withholds. The refusals of a filing
are pinned in the order they are tried, and a refused filing changes nothing.

The hammer of these tests holds a deposit of R1,200.00 and is worth R6,500.00.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Final
from uuid import UUID, uuid4

import pytest

from app.domain.catalogue import Asset
from app.domain.damage_filing import (
    DamageFiling,
    UnitLastHire,
    ensure_may_file,
    file_damage_report,
)
from app.domain.enums import (
    AssetStatus,
    ChargeStatus,
    ChargeType,
    ConditionGrade,
    DamageSeverity,
    DamageStatus,
    RentalStatus,
)
from app.domain.errors import StateTransitionError, ValidationFailure
from app.domain.money import Money
from app.domain.quarantine import assessments_due_on
from app.domain.rental import DamageAssessment, Rental, SettlementWait
from app.domain.settlement import settle_deposit, settlement_wait
from tests.support.checkout_domain import ASSISTANT
from tests.support.return_domain import (
    DUE_BACK_ON,
    Hire,
    a_hire,
    back,
    days_after_due,
    lost,
    returned,
)

NOW: Final[datetime] = datetime(2026, 3, 12, 8, 0, tzinfo=UTC)
REFERENCE: Final[str] = "TSH-D-26-00031"


def a_filing(
    item_id: UUID | None = None,
    *,
    chargeable: bool = False,
    amount: str | None = None,
    description: str = "Cracked gearbox housing",
    estimate: str = "450.00",
) -> DamageFiling:
    """Return what the counter states about a damaged unit."""
    return DamageFiling(
        rental_item_id=item_id,
        severity=DamageSeverity.MINOR,
        description=description,
        repair_estimate=Money.create(estimate),
        chargeable_to_customer=chargeable,
        recovery_amount=None if amount is None else Money.create(amount),
    )


def back_worse(hire: Hire) -> Asset:
    """Take the hire's one unit back a grade worse on its due date, and return the unit."""
    (closed,) = returned(hire, DUE_BACK_ON, back(hire, condition_in=ConditionGrade.B)).units
    return closed.unit


def waiting_on(rental: Rental) -> SettlementWait | None:
    """Return what the settlement of a rental waits on, as the return asks it."""
    return settlement_wait(
        status=rental.status,
        items_out=len(rental.items_out()),
        assessments_due=assessments_due_on(rental),
        balance_due=rental.balance_due,
    )


def last_hire_of(hire: Hire) -> UnitLastHire:
    """Return the hire as the unit's last, waiting for its assessment."""
    return UnitLastHire(
        rental_item_id=hire.rental.items[0].id,
        rental_reference=hire.rental.reference,
        assessment=DamageAssessment.REQUIRED,
    )


class TestTheSettlementWaitsAndResumes:
    """The deposit waits for the assessment and is settled once the report is filed."""

    def test_a_chargeable_report_lets_the_deposit_settle_with_the_recovery_withheld(self) -> None:
        hire = a_hire()
        unit = back_worse(hire)
        rental = hire.rental
        assert (rental.status, waiting_on(rental)) == (
            RentalStatus.RETURNED, SettlementWait.DAMAGE_ASSESSMENT
        )

        filed = file_damage_report(
            a_filing(rental.items[0].id, chargeable=True, amount="450.00"),
            unit=unit,
            rental=rental,
            last_hire=last_hire_of(hire),
            reference=REFERENCE,
            reported_by=ASSISTANT,
            now=NOW,
        )
        charge = filed.recovery_charge
        assert charge is not None and charge.damage_report_id == filed.report.id
        assert (charge.charge_type, charge.status) == (
            ChargeType.DAMAGE_RECOVERY, ChargeStatus.PENDING
        )
        assert (charge.amount_ex_vat, charge.vat_amount, charge.amount_inc_vat) == (
            Decimal("391.30"), Decimal("58.70"), Decimal("450.00")
        )
        assert waiting_on(rental) is None

        settlement = settle_deposit(rental, settled_by=ASSISTANT, now=NOW)
        assert (settlement.withheld, settlement.released) == (
            Money.create("450.00"), Money.create("750.00")
        )
        assert (rental.status, rental.balance_due) == (RentalStatus.SETTLED, Decimal("0.00"))
        assert {charge.status for charge in rental.charges} == {ChargeStatus.SETTLED}

    def test_a_report_that_is_not_chargeable_raises_no_charge_and_lifts_the_wait(self) -> None:
        hire = a_hire()
        unit = back_worse(hire)
        charges_before = list(hire.rental.charges)
        filed = file_damage_report(
            a_filing(hire.rental.items[0].id),
            unit=unit,
            rental=hire.rental,
            last_hire=last_hire_of(hire),
            reference=REFERENCE,
            reported_by=ASSISTANT,
            now=NOW,
        )
        assert filed.recovery_charge is None
        assert hire.rental.charges == charges_before
        assert (filed.report.status, filed.report.chargeable_to_customer) == (
            DamageStatus.OPEN, False
        )
        assert filed.unit is unit and waiting_on(hire.rental) is None

    def test_a_report_outside_a_hire_quarantines_the_unit_and_charges_nobody(self) -> None:
        hire = a_hire()
        (closed,) = returned(hire, DUE_BACK_ON, back(hire)).units
        assert closed.unit.status is AssetStatus.AVAILABLE
        filed = file_damage_report(
            a_filing(chargeable=True),
            unit=closed.unit,
            rental=None,
            last_hire=None,
            reference=REFERENCE,
            reported_by=ASSISTANT,
            now=NOW,
        )
        assert (filed.unit.status, filed.recovery_charge, filed.report.rental_item_id) == (
            AssetStatus.QUARANTINED, None, None
        )
        assert filed.report.description == "Cracked gearbox housing"


class TestWhatAFilingRefuses:
    """The fields first, then the standing of the unit and the hire, and nothing changes."""

    @pytest.mark.parametrize(
        ("filing", "field"),
        [
            (a_filing(description="   "), "description"),
            (a_filing(estimate="-1.00"), "repair_estimate"),
            (a_filing(chargeable=True, amount="10.00"), "recovery_amount"),
            (a_filing(uuid4()), "rental_item_id"),
        ],
        ids=["blank description", "negative estimate", "amount outside a hire", "unknown item"],
    )
    def test_a_field_that_is_wrong_is_refused_by_its_name(
        self, filing: DamageFiling, field: str
    ) -> None:
        hire = a_hire()
        unit = back_worse(hire)
        with pytest.raises(ValidationFailure) as refused:
            ensure_may_file(filing, unit=unit, rental=hire.rental, last_hire=None)
        assert refused.value.detail == {"field": field}

    def test_the_item_of_another_unit_is_refused(self) -> None:
        hire = a_hire()
        other = a_hire()
        unit = back_worse(hire)
        with pytest.raises(ValidationFailure, match="could not find that hire"):
            ensure_may_file(
                a_filing(other.rental.items[0].id), unit=unit, rental=other.rental, last_hire=None
            )

    def test_an_amount_above_the_replacement_value_is_refused(self) -> None:
        hire = a_hire()
        unit = back_worse(hire)
        filing = a_filing(hire.rental.items[0].id, chargeable=True, amount="6500.01")
        with pytest.raises(ValidationFailure, match="more than R6500.00"):
            ensure_may_file(filing, unit=unit, rental=hire.rental, last_hire=last_hire_of(hire))

    def test_a_lost_unit_already_charged_its_value_has_nothing_left_to_recover(self) -> None:
        hire = a_hire()
        outcome = lost(hire, days_after_due(15))
        filing = a_filing(hire.rental.items[0].id, chargeable=True, amount="0.01")
        with pytest.raises(ValidationFailure, match="R6500.00 of the replacement value"):
            ensure_may_file(filing, unit=outcome.unit.unit, rental=hire.rental, last_hire=None)

    def test_a_unit_waiting_for_its_return_report_must_be_reported_from_that_return(self) -> None:
        hire = a_hire()
        unit = back_worse(hire)
        with pytest.raises(StateTransitionError, match=hire.rental.reference):
            ensure_may_file(a_filing(), unit=unit, rental=None, last_hire=last_hire_of(hire))
        assert unit.status is AssetStatus.QUARANTINED

    def test_a_charge_on_a_hire_already_settled_is_refused(self) -> None:
        hire = a_hire()
        (closed,) = returned(hire, DUE_BACK_ON, back(hire)).units
        settle_deposit(hire.rental, settled_by=ASSISTANT, now=NOW)
        filing = a_filing(hire.rental.items[0].id, chargeable=True, amount="100.00")
        with pytest.raises(StateTransitionError, match="already been settled"):
            ensure_may_file(filing, unit=closed.unit, rental=hire.rental, last_hire=None)
        assert len(hire.rental.charges) == 3
