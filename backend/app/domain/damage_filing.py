"""Filing a damage report, which is FR-20 and US-24 (BR-35, BR-39, BR-40).

A report is filed against one unit. It may name the rental item of the hire
the unit came back from, or no rental item when the damage was found outside a
hire. Filing does four things together.

1. The report is recorded OPEN, with the decision on whether the customer is
   charged, which is never a default (BR-40).
2. The unit is taken out of availability (`app.domain.damage_units`).
3. When the report names a rental item, the item's damage assessment is done,
   which may be the last thing the deposit of the hire was waiting on.
4. When the customer is charged, a DAMAGE_RECOVERY charge is raised on the
   rental for the amount to recover, which the deposit pays first (BR-39).

A unit that came back from a hire in a worse grade, or flagged, waits for the
report of that return. A report about it that does not name that rental item
is refused with 409 and a sentence naming the hire. Without that refusal a
report filed from somewhere other than the return would leave the hire waiting
for an assessment that never comes, and its deposit would never be settled.

Every refusal is decided by `ensure_may_file` before anything changes, the
refusals of a field first (422) and then those of a state (409), so a refused
report changes nothing and draws no reference.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

from app.domain.catalogue import Asset
from app.domain.charge import Charge
from app.domain.customer_account import REFUSED_FIELD
from app.domain.damage import DamageReport
from app.domain.damage_recovery import (
    already_recovered,
    ensure_deposit_still_held,
    ensure_recovery_decided,
    ensure_recovery_within_cap,
)
from app.domain.damage_units import quarantined_for_report
from app.domain.enums import AssetStatus, DamageSeverity
from app.domain.errors import StateTransitionError, ValidationFailure
from app.domain.money import Money
from app.domain.rental import DamageAssessment, Rental, RentalItem
from app.domain.return_charges import damage_recovery_charge

FILING_RULE: Final[str] = "BR-35"
RENTAL_ITEM_FIELD: Final[str] = "rental_item_id"
DESCRIPTION_FIELD: Final[str] = "description"
ESTIMATE_FIELD: Final[str] = "repair_estimate"
UNKNOWN_RENTAL_ITEM_MESSAGE: Final[str] = (
    "We could not find that hire of this unit. Check the rental item and try again."
)
BLANK_DESCRIPTION_MESSAGE: Final[str] = "Describe the damage."
NEGATIVE_ESTIMATE_MESSAGE: Final[str] = "A repair estimate cannot be less than R0.00."


@dataclass(frozen=True, slots=True)
class DamageFiling:
    """What the counter states about the damage of one unit.

    Attributes:
        rental_item_id: The hire the unit came back from, or None.
        severity: How bad the damage is.
        description: What is wrong with the unit.
        repair_estimate: What the repair is expected to cost.
        chargeable_to_customer: Whether the customer is charged (BR-40).
        recovery_amount: What to recover from the customer, including VAT.

    """

    rental_item_id: UUID | None
    severity: DamageSeverity
    description: str
    repair_estimate: Money
    chargeable_to_customer: bool
    recovery_amount: Money | None


@dataclass(frozen=True, slots=True)
class UnitLastHire:
    """The most recent hire of a unit, as far as a new report about it needs to know.

    Attributes:
        rental_item_id: The rental item of that hire.
        rental_reference: The reference of its rental, which a refusal names.
        assessment: Whether that hire waits for the damage of the unit to be assessed.

    """

    rental_item_id: UUID
    rental_reference: str
    assessment: DamageAssessment


@dataclass(frozen=True, slots=True)
class FiledReport:
    """What filing a report did, for the caller to store and to record.

    Attributes:
        report: The report, OPEN.
        unit_before: The unit as it stood.
        unit: The unit as it stands now, out of availability.
        recovery_charge: The recovery raised on the rental, or None.

    """

    report: DamageReport
    unit_before: Asset
    unit: Asset
    recovery_charge: Charge | None


def ensure_may_file(
    filing: DamageFiling, *, unit: Asset, rental: Rental | None, last_hire: UnitLastHire | None
) -> None:
    """Refuse a report that may not be filed, changing nothing.

    Args:
        filing: What the counter stated.
        unit: The unit, locked by the caller.
        rental: The rental of the named rental item, locked by the caller, or
            None when the report names none or the item was not found.
        last_hire: The unit's most recent hire, or None when it was never hired.

    Raises:
        ValidationFailure: Naming the field, for a blank description, an
            estimate below nothing, an amount to recover that does not follow
            from the decision or is above the cap, or a rental item that is not
            a hire of this unit.
        StateTransitionError: If the unit waits for the report of another
            hire, is out on hire or retired, or the customer is charged on a
            hire whose deposit was already settled.

    """
    if not filing.description.strip():
        raise _refused(DESCRIPTION_FIELD, BLANK_DESCRIPTION_MESSAGE)
    if filing.repair_estimate.is_negative():
        raise _refused(ESTIMATE_FIELD, NEGATIVE_ESTIMATE_MESSAGE)
    ensure_recovery_decided(
        chargeable=filing.chargeable_to_customer,
        names_rental_item=filing.rental_item_id is not None,
        recovery_amount=filing.recovery_amount,
    )
    item = _item_named(filing, unit, rental)
    if rental is not None and item is not None and filing.recovery_amount is not None:
        ensure_recovery_within_cap(
            filing.recovery_amount,
            replacement_value=Money.create(item.terms.replacement_value),
            already=already_recovered(rental, item),
        )
    _ensure_names_the_awaited_hire(filing, unit, last_hire)
    quarantined_for_report(unit)
    if rental is not None and filing.recovery_amount is not None:
        ensure_deposit_still_held(rental)


def file_damage_report(
    filing: DamageFiling,
    *,
    unit: Asset,
    rental: Rental | None,
    last_hire: UnitLastHire | None,
    reference: str,
    reported_by: UUID,
    now: datetime,
) -> FiledReport:
    """File the report, take the unit out of availability and charge what is recovered.

    Args:
        filing: What the counter stated.
        unit: The unit, locked by the caller.
        rental: The rental of the named rental item, locked by the caller, or None.
        last_hire: The unit's most recent hire, or None when it was never hired.
        reference: The reference drawn for the report.
        reported_by: The member of staff filing it.
        now: The current instant, from the clock.

    Raises:
        ValidationFailure: As `ensure_may_file`.
        StateTransitionError: As `ensure_may_file`.

    """
    ensure_may_file(filing, unit=unit, rental=rental, last_hire=last_hire)
    report = DamageReport(
        reference=reference,
        asset_id=unit.id,
        rental_item_id=filing.rental_item_id,
        severity=filing.severity,
        description=filing.description.strip(),
        repair_estimate=filing.repair_estimate.rounded().amount,
        chargeable_to_customer=filing.chargeable_to_customer,
        reported_by_user_id=reported_by,
        reported_at=now,
    )
    item = _item_named(filing, unit, rental)
    charge = None
    if rental is not None and item is not None:
        item.damage_reported = True
        if filing.recovery_amount is not None:
            charge = damage_recovery_charge(
                rental=rental,
                item=item,
                report_id=report.id,
                report_reference=reference,
                amount_inc_vat=filing.recovery_amount,
                raised_by=reported_by,
                now=now,
            )
            rental.charges.append(charge)
    return FiledReport(
        report=report, unit_before=unit, unit=quarantined_for_report(unit), recovery_charge=charge
    )


def _item_named(filing: DamageFiling, unit: Asset, rental: Rental | None) -> RentalItem | None:
    """Return the rental item the report names, or None when it names none.

    Raises:
        ValidationFailure: Naming `rental_item_id` when the item was not found
            or is a hire of another unit.

    """
    if filing.rental_item_id is None:
        return None
    item = rental.item_with_id(filing.rental_item_id) if rental is not None else None
    if item is None or item.asset_id != unit.id:
        raise _refused(RENTAL_ITEM_FIELD, UNKNOWN_RENTAL_ITEM_MESSAGE)
    return item


def _ensure_names_the_awaited_hire(
    filing: DamageFiling, unit: Asset, last_hire: UnitLastHire | None
) -> None:
    """Refuse a report about a unit that waits for the report of another hire.

    Raises:
        StateTransitionError: Naming the rental the unit came back from.

    """
    if last_hire is None or last_hire.assessment is not DamageAssessment.REQUIRED:
        return
    if filing.rental_item_id == last_hire.rental_item_id:
        return
    raise StateTransitionError(
        f"Unit {unit.asset_tag} came back damaged from rental {last_hire.rental_reference} and "
        "waits for the report of that return. File the report from that return, so its "
        "deposit can be settled.",
        from_status=unit.status.value,
        to_status=AssetStatus.QUARANTINED.value,
        rule=FILING_RULE,
    )


def _refused(field: str, message: str) -> ValidationFailure:
    """Return the refusal of one field of the report."""
    return ValidationFailure(message, {REFUSED_FIELD: field}, rule=FILING_RULE)
