"""The use case that files a damage report, which is FR-20 and US-24 (BR-35 to BR-40).

A member of staff at the branch that holds the unit files the report (BR-43).
In one unit of work the rental of the named rental item is locked first, the
way every change to a rental locks it, and then the unit. The domain decides
every refusal before anything changes (`app.domain.damage_filing`). Only then
is a reference drawn from the damage report sequence, so a refused report uses
no number.

The report is written, the unit is taken out of availability, and when the
customer is charged a DAMAGE_RECOVERY charge is raised on the rental. When the
report completes the last assessment the hire was waiting on and every unit is
back, the deposit is settled in the same unit of work, through the settlement
the return uses, with the recovery among what it withholds (BR-32). Audit
events are written for the report, the unit and the rental (BR-49). Either all
of it is committed or none of it is.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from app.application.hire.damage_audit import (
    DAMAGE_REPORT_FILED_ACTION,
    RENTAL_DAMAGE_ASSESSED_ACTION,
    record_report_change,
    record_unit_move,
)
from app.application.hire.damage_models import DamageReportDetail, DamageReportKey
from app.application.hire.damage_reads import read_report
from app.application.hire.read_models import RentalKey
from app.application.hire.rental_audit import record_rental_change, rental_state
from app.application.hire.settle import settle_when_nothing_waits
from app.application.identity.account_rules import refused_field
from app.application.refusal import refused
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.damage_filing import DamageFiling, ensure_may_file, file_damage_report
from app.domain.errors import ValidationFailure
from app.domain.identity import Actor, ensure_branch_scope
from app.domain.rental import Rental

logger = logging.getLogger(__name__)

# The name the contract gives the tag of the unit, which a refusal of it names.
ASSET_TAG_PARAMETER: Final[str] = "assetTag"
UNKNOWN_UNIT_MESSAGE: Final[str] = "We could not find a unit with that tag. Check it and try again."


@dataclass(frozen=True, slots=True)
class FileDamageReportCommand:
    """A request to file a damage report against one unit.

    Attributes:
        actor: The member of staff filing it.
        asset_tag: The tag of the damaged unit, in upper case.
        filing: What the counter stated about the damage.

    """

    actor: Actor
    asset_tag: str
    filing: DamageFiling


class FileDamageReportUseCase(UseCase[FileDamageReportCommand, DamageReportDetail]):
    """File a report, quarantine the unit, charge the recovery and settle when it may."""

    def execute(self, command: FileDamageReportCommand) -> DamageReportDetail:
        """File the report, or refuse and change nothing.

        Raises:
            ValidationFailure: Naming the field, for an unknown tag, an amount
                to recover that does not follow from the decision or is above
                the cap, or a rental item that is not a hire of the unit.
            BranchScopeError: If counter staff file a report at another branch.
            StateTransitionError: If the unit waits for the report of another
                hire, is out on hire or retired, or the deposit of the hire was
                already settled when the customer is charged.

        """
        actor, filing = command.actor, command.filing
        logger.info(
            "damage_report.file_requested",
            extra={
                "actor_user_id": str(actor.user_id),
                "actor_role": actor.role.value,
                "asset_tag": command.asset_tag,
                "rental_item_id": str(filing.rental_item_id) if filing.rental_item_id else None,
                "severity": filing.severity.value,
                "chargeable_to_customer": filing.chargeable_to_customer,
                "recovery_amount": (
                    str(filing.recovery_amount.amount) if filing.recovery_amount else None
                ),
            },
        )
        now = self._clock.now()
        today = self._clock.today()
        with self._uow as uow:
            unit_id = uow.damage_reports.unit_id_of_tag(command.asset_tag)
            if unit_id is None:
                raise refused(
                    ASSET_TAG_PARAMETER, UNKNOWN_UNIT_MESSAGE, {"asset_tag": command.asset_tag}
                )
            rental = _rental_of(uow, filing.rental_item_id)
            rental_before = rental_state(rental) if rental is not None else None
            (unit,) = uow.assets.lock_units([unit_id])
            ensure_branch_scope(actor, unit.branch_id)
            last_hire = uow.damage_reports.last_hire_of(unit.id)
            try:
                ensure_may_file(filing, unit=unit, rental=rental, last_hire=last_hire)
                filed = file_damage_report(
                    filing,
                    unit=unit,
                    rental=rental,
                    last_hire=last_hire,
                    reference=uow.damage_reports.next_reference(today.year),
                    reported_by=actor.user_id,
                    now=now,
                )
            except ValidationFailure as failure:
                raise refused_field(failure) from failure
            report = filed.report
            uow.damage_reports.add(report)
            record_unit_move(
                uow,
                actor=actor,
                unit_before=filed.unit_before,
                unit=filed.unit,
                report_reference=report.reference,
                occurred_at=now,
            )
            record_report_change(
                uow,
                actor=actor,
                report=report,
                action=DAMAGE_REPORT_FILED_ACTION,
                occurred_at=now,
                before=None,
                extra={"asset_tag": unit.asset_tag},
            )
            if rental is not None and rental_before is not None:
                charged = filed.recovery_charge
                record_rental_change(
                    uow,
                    actor=actor,
                    rental=rental,
                    action=RENTAL_DAMAGE_ASSESSED_ACTION,
                    occurred_at=now,
                    before=rental_before,
                    extra={
                        "damage_report_reference": report.reference,
                        "recovery": str(charged.amount_inc_vat) if charged else None,
                    },
                )
                settle_when_nothing_waits(uow, rental, actor=actor, now=now)
                uow.rentals.save(rental)
            detail = read_report(uow, DamageReportKey.of(report.id))
            uow.commit()
        logger.info(
            "damage_report.filed",
            extra={
                "reference": detail.reference,
                "damage_report_id": str(detail.id),
                "asset_tag": detail.asset_tag,
                "unit_status": filed.unit.status.value,
                "rental_reference": detail.rental_reference,
                "recovery_charged": (
                    str(detail.recovery_charged) if detail.recovery_charged is not None else None
                ),
                "rental_status": rental.status.value if rental is not None else None,
            },
        )
        return detail


def _rental_of(uow: UnitOfWork, rental_item_id: UUID | None) -> Rental | None:
    """Return the rental of the named rental item, locked, or None.

    None when the report names no item, and when the item does not exist,
    which the domain then refuses by the field that named it.
    """
    if rental_item_id is None:
        return None
    rental_id = uow.damage_reports.hire_of_item(rental_item_id)
    if rental_id is None:
        return None
    return uow.rentals.find_for_update(RentalKey.of(rental_id))
