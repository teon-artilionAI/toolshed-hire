"""The use cases by which an administrator registers a unit and edits its paperwork (FR-23, BR-34).

A unit is registered with its tag, its model and the branch that holds it, and
starts at INTAKE. The tag is checked for its form and for another unit that
already carries it, and the unique constraint has the last word, so a race
lost to it is answered as the check would have answered it. The model has to
exist, published or not, because stock often arrives before a model is put in
the catalogue. The branch has to be trading.

An edit changes the serial number, the grade, the meter reading and the notes
it names, and nothing else. The tag, the model and the branch never change
(BR-34), and the request that would carry them is refused before it reaches
here. An edit that changes nothing writes nothing.

Each write locks or inserts the unit, writes it and records `asset.registered`
or `asset.updated` in the same unit of work (BR-49), and answers with the unit
and its history as the register shows them, read once the change committed.
"""

from __future__ import annotations

import logging
from typing import Final
from uuid import uuid4

from app.application.availability.search import UNKNOWN_BRANCH_MESSAGE
from app.application.catalogue.admin_ports import DuplicateCatalogueValue
from app.application.catalogue.asset_changes import (
    UNIT_REGISTERED_ACTION,
    UNIT_UPDATED_ACTION,
    details_state,
    record_unit_change,
    unit_state,
)
from app.application.catalogue.asset_commands import EditUnitCommand, RegisterUnitCommand
from app.application.catalogue.asset_history import HISTORY_LIMIT, history_of
from app.application.catalogue.asset_ports import AssetRegisterQuery
from app.application.catalogue.asset_read_models import AdminAssetDetail
from app.application.catalogue.asset_reads import UNIT_NOT_FOUND_MESSAGE
from app.application.catalogue.catalogue_changes import changed_fields, checked, refused_duplicate
from app.application.clock import Clock
from app.application.identity.account_rules import wire_name
from app.application.refusal import refused
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.asset_register import (
    ASSET_TAG,
    BRANCH_CODE,
    MODEL_ID,
    NewUnitTerms,
    RegisteredUnit,
    checked_details,
    checked_new_unit,
    registered,
)
from app.domain.errors import NotFound

logger = logging.getLogger(__name__)

UNKNOWN_MODEL_MESSAGE: Final[str] = "Choose a model from the list."
TAKEN_MESSAGES: Final[dict[str, str]] = {ASSET_TAG: "Another unit already carries this tag."}


class UnitUseCase[CommandT](UseCase[CommandT, AdminAssetDetail]):
    """What every write of the register shares, the read its answer comes from."""

    def __init__(self, uow: UnitOfWork, clock: Clock, register: AssetRegisterQuery) -> None:
        """Keep the unit of work, the clock and the read the answer comes from."""
        super().__init__(uow, clock)
        self._register = register

    def _answer(self, asset_tag: str) -> AdminAssetDetail:
        """Return the unit with its history as the register shows it, read after the commit.

        Raises:
            LookupError: If the unit cannot be read back, which would mean the
                commit did not keep what it was handed.

        """
        entry = self._register.unit(asset_tag)
        if entry is None:
            raise LookupError(
                f"Attempted to read back unit {asset_tag} after writing it, and it could not be "
                "read."
            )
        facts = self._register.history(entry.id, HISTORY_LIMIT)
        return AdminAssetDetail(entry=entry, history=history_of(facts, HISTORY_LIMIT))


def locked_unit(uow: UnitOfWork, asset_tag: str) -> RegisteredUnit:
    """Return the unit with this tag, locked for the rest of the transaction.

    Raises:
        NotFound: If no unit carries the tag.

    """
    stored = uow.asset_register.find_for_update(asset_tag)
    if stored is None:
        logger.info("asset.register_unit_not_found", extra={"asset_tag": asset_tag})
        raise NotFound(UNIT_NOT_FOUND_MESSAGE, {"asset_tag": asset_tag})
    return stored


class RegisterUnitUseCase(UnitUseCase[RegisterUnitCommand]):
    """Register a unit at INTAKE, with its audit event."""

    def execute(self, command: RegisterUnitCommand) -> AdminAssetDetail:
        """Register the unit, or refuse and write nothing.

        Raises:
            ValidationFailure: Naming the field, for a field that breaks a
                rule, a model nobody can find, a branch that is not trading,
                or a tag another unit carries.

        """
        logger.info(
            "asset.register_requested",
            extra={
                "actor_user_id": str(command.actor.user_id),
                "asset_tag": command.terms.asset_tag,
                "model_id": str(command.model_id),
                "branch_code": command.branch_code,
            },
        )
        now = self._clock.now()
        today = self._clock.today()
        with self._uow as uow:
            terms = checked(lambda given: checked_new_unit(given, today=today), command.terms)
            unit = self._unit_of(uow, command, terms)
            branch_code = command.branch_code
            try:
                uow.asset_register.add(unit, now)
            except DuplicateCatalogueValue as duplicate:
                raise refused_duplicate(duplicate, TAKEN_MESSAGES) from duplicate
            record_unit_change(
                uow,
                actor=command.actor,
                registered=unit,
                action=UNIT_REGISTERED_ACTION,
                now=now,
                before=None,
                after=unit_state(unit, branch_code),
            )
            uow.commit()
        logger.info(
            "asset.registered",
            extra={"asset_id": str(unit.unit.id), "asset_tag": terms.asset_tag},
        )
        return self._answer(terms.asset_tag)

    @staticmethod
    def _unit_of(
        uow: UnitOfWork, command: RegisterUnitCommand, terms: NewUnitTerms
    ) -> RegisteredUnit:
        """Return the new unit, or refuse a model, a branch or a tag the register cannot take.

        Raises:
            ValidationFailure: Naming `modelId`, `branchCode` or `assetTag`.

        """
        model = uow.product_models.get(command.model_id)
        if model is None:
            logger.info("asset.register_model_unknown", extra={"model_id": str(command.model_id)})
            raise refused(wire_name(MODEL_ID), UNKNOWN_MODEL_MESSAGE)
        branch = uow.branches.find_active_by_code(command.branch_code)
        if branch is None:
            logger.info(
                "asset.register_branch_unknown", extra={"branch_code": command.branch_code}
            )
            raise refused(wire_name(BRANCH_CODE), UNKNOWN_BRANCH_MESSAGE)
        if uow.asset_register.tag_taken(terms.asset_tag):
            logger.info("asset.register_tag_taken", extra={"asset_tag": terms.asset_tag})
            raise refused(wire_name(ASSET_TAG), TAKEN_MESSAGES[ASSET_TAG])
        return registered(
            terms, unit_id=uuid4(), product_model_id=model.id, branch_id=branch.id
        )


class EditUnitUseCase(UnitUseCase[EditUnitCommand]):
    """Change the paperwork of a unit an edit names, with its audit event."""

    def execute(self, command: EditUnitCommand) -> AdminAssetDetail:
        """Change the paperwork, or refuse and write nothing.

        Raises:
            NotFound: If no unit carries the tag.
            ValidationFailure: Naming the field that breaks a rule.

        """
        logger.info(
            "asset.edit_requested",
            extra={"actor_user_id": str(command.actor.user_id), "asset_tag": command.asset_tag},
        )
        now = self._clock.now()
        with self._uow as uow:
            stored = locked_unit(uow, command.asset_tag)
            details = checked(checked_details, command.changes.applied_to(stored.details))
            before, after = changed_fields(details_state(stored.details), details_state(details))
            if not after:
                logger.info("asset.edit_unchanged", extra={"asset_tag": command.asset_tag})
                return self._answer(stored.unit.asset_tag)
            edited = stored.with_details(details)
            uow.asset_register.save_details(edited, now)
            record_unit_change(
                uow,
                actor=command.actor,
                registered=edited,
                action=UNIT_UPDATED_ACTION,
                now=now,
                before=before,
                after=after,
            )
            uow.commit()
        logger.info(
            "asset.edited",
            extra={"asset_tag": stored.unit.asset_tag, "changed": sorted(after)},
        )
        return self._answer(stored.unit.asset_tag)
