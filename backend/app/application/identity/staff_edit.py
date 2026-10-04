"""The use case by which an administrator edits a staff account (FR-25, US-35).

An edit changes the name, the phone, the role and the branch it names. A role
change takes effect on the next request the person makes, because every
request reads the role from the account and never from the token. An edit
that makes somebody an administrator and names no branch lets go of their
branch, because an administrator belongs to none. The last active
administrator is never given another role. An edit that changes nothing
writes nothing.

The edit is asked with every active administrator locked, as every staff
write is, so the rule about the last administrator holds when two
administrators change each other at the same moment.
"""

from __future__ import annotations

import logging

from app.application.catalogue.admin_commands import chosen
from app.application.catalogue.catalogue_changes import checked
from app.application.identity.staff_changes import (
    BRANCH_KEY,
    CHANGED_KEY,
    ROLE_KEY,
    STAFF_UPDATED_ACTION,
    StaffAccountUseCase,
    branch_code_of,
    locked_administrators,
    locked_staff_account,
    record_staff_change,
    trading_branch_id,
)
from app.application.identity.staff_commands import EditStaffAccountCommand, StaffChanges
from app.application.identity.staff_read_models import StaffMember
from app.application.unit_of_work import UnitOfWork
from app.domain.account import Account
from app.domain.audit import StateValue
from app.domain.staff_account import (
    STAFF_FULL_NAME,
    STAFF_PHONE,
    StaffDetails,
    branch_kept_for,
    checked_staff_details,
    details_of,
    ensure_an_administrator_remains,
    with_details,
)

logger = logging.getLogger(__name__)


class EditStaffAccountUseCase(StaffAccountUseCase[EditStaffAccountCommand, StaffMember]):
    """Change the name, the phone, the role and the branch an edit names, and record it."""

    def execute(self, command: EditStaffAccountCommand) -> StaffMember:
        """Change the account, or refuse and change nothing.

        Raises:
            NotFound: If no staff account has the key.
            ValidationFailure: Naming the field that breaks a rule.
            StateTransitionError: If the account is the last active
                administrator and the edit gives it another role.
            AuthorisationFailure: If the actor is no longer an active administrator.

        """
        logger.info(
            "staff.edit_requested",
            extra={
                "actor_user_id": str(command.actor.user_id),
                "user_id": str(command.user_id),
                "role_named": command.changes.role is not None,
                "branch_named": command.changes.branch_code is not None,
            },
        )
        now = self._clock.now()
        with self._uow as uow:
            administrators = locked_administrators(uow, command.actor)
            account = locked_staff_account(uow, command.user_id)
            edited = _edited(uow, account, command.changes)
            ensure_an_administrator_remains(
                account, after=edited, active_administrators=administrators
            )
            before, after = _changes_of(uow, account, edited)
            if not after:
                logger.info("staff.edit_unchanged", extra={"user_id": str(account.id)})
                return self._answer(account.id)
            uow.staff.save_staff(edited)
            record_staff_change(
                uow,
                actor=command.actor,
                account_id=account.id,
                action=STAFF_UPDATED_ACTION,
                now=now,
                before=before,
                after=after,
            )
            uow.commit()
        logger.info(
            "staff.edited", extra={"user_id": str(account.id), "changed": after[CHANGED_KEY]}
        )
        return self._answer(account.id)


def _edited(uow: UnitOfWork, account: Account, changes: StaffChanges) -> Account:
    """Return the account as the edit would leave it, or refuse a field it cannot hold.

    Raises:
        ValidationFailure: Naming the field.

    """
    current = details_of(account)
    candidate = StaffDetails(
        full_name=chosen(current.full_name, changes.full_name),
        phone=chosen(current.phone, changes.phone),
        role=chosen(current.role, changes.role),
    )
    branch_id = account.branch_id
    if changes.branch_code is not None:
        named = changes.branch_code.value
        branch_id = trading_branch_id(uow, named) if named is not None else None
    branch_id = branch_kept_for(
        candidate.role, branch_id, branch_named=changes.branch_code is not None
    )
    details = checked(
        lambda given: checked_staff_details(given, has_branch=branch_id is not None), candidate
    )
    return with_details(account, details, branch_id)


def _changes_of(
    uow: UnitOfWork, account: Account, edited: Account
) -> tuple[dict[str, StateValue], dict[str, StateValue]]:
    """Return what an edit changed, as the audit event records it, both empty for nothing.

    The role and the branch carry their values before and after. The name and
    the phone are named in the list of what changed, without their values.
    """
    changed = sorted(
        name
        for name, was, became in (
            (STAFF_FULL_NAME, account.full_name, edited.full_name),
            (STAFF_PHONE, account.phone, edited.phone),
            (ROLE_KEY, account.role, edited.role),
            (BRANCH_KEY, account.branch_id, edited.branch_id),
        )
        if was != became
    )
    if not changed:
        return {}, {}
    before: dict[str, StateValue] = {}
    after: dict[str, StateValue] = {CHANGED_KEY: changed}
    if ROLE_KEY in changed:
        before[ROLE_KEY], after[ROLE_KEY] = account.role.value, edited.role.value
    if BRANCH_KEY in changed:
        before[BRANCH_KEY] = branch_code_of(uow, account.branch_id)
        after[BRANCH_KEY] = branch_code_of(uow, edited.branch_id)
    return before, after
