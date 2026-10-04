"""What the staff account use cases share (FR-25, US-35, BR-44, BR-49).

Every write starts the same way. Every active administrator is locked, in the
order of their keys, and the administrator asking has to be among them. That
one lock is two things. It reads the account of the administrator again, so a
change made by somebody who was demoted or deactivated a moment ago is
refused, and it is what the rule about the last administrator is asked
under, so two administrators demoting each other at the same moment take
turns and the second is answered from what the first committed. The routes
therefore do not take the shared lock `FreshAdminUser` takes. Two
administrators each holding a shared lock on their own row and each wanting
to change the other's would wait on each other for ever.

An account that is not a staff account is answered as one nobody opened,
because a customer is kept through their profile and not here.

Every change writes one audit event about the account in its transaction
(BR-49). The role and the branch are recorded as they were and as they became,
because they are what a person may do. The name and the phone are recorded by
name only, the way a customer's own edit is, because a log that can never be
rewritten is the wrong place to keep every number somebody has had.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Final
from uuid import UUID

from app.application.audit import audit_event_for
from app.application.availability.search import UNKNOWN_BRANCH_MESSAGE
from app.application.clock import Clock
from app.application.identity.account_rules import wire_name
from app.application.identity.sessions import ACCOUNT_ENTITY_TYPE
from app.application.identity.staff_read_models import StaffDirectory, StaffMember
from app.application.refusal import refused
from app.application.unit_of_work import UnitOfWork
from app.application.use_case import UseCase
from app.domain.account import Account
from app.domain.audit import StateValue
from app.domain.errors import AuthorisationFailure, NotFound
from app.domain.identity import Actor
from app.domain.staff_account import BRANCH_CODE, STAFF_ROLES

logger = logging.getLogger(__name__)

STAFF_OPENED_ACTION: Final[str] = "user_account.created"
STAFF_UPDATED_ACTION: Final[str] = "user_account.updated"
STAFF_DEACTIVATED_ACTION: Final[str] = "user_account.deactivated"
STAFF_REACTIVATED_ACTION: Final[str] = "user_account.reactivated"
ROLE_KEY: Final[str] = "role"
BRANCH_KEY: Final[str] = "branch_code"
ACTIVE_KEY: Final[str] = "is_active"
CHANGED_KEY: Final[str] = "changed_fields"
STAFF_NOT_FOUND_MESSAGE: Final[str] = "We could not find that staff account."
NO_LONGER_ADMINISTRATOR_MESSAGE: Final[str] = (
    "Your account is no longer an active administrator, so the change was not made."
)


def locked_administrators(uow: UnitOfWork, actor: Actor) -> frozenset[UUID]:
    """Lock every active administrator and refuse an actor who is no longer one of them.

    Returns:
        The keys of every active administrator, locked until the transaction ends.

    Raises:
        AuthorisationFailure: If the actor's account is no longer an active
            administrator. HTTP 403.

    """
    administrators = uow.staff.lock_active_administrators()
    if actor.user_id not in administrators:
        logger.warning(
            "staff.actor_no_longer_administrator",
            extra={"actor_user_id": str(actor.user_id), "administrators": len(administrators)},
        )
        raise AuthorisationFailure(
            NO_LONGER_ADMINISTRATOR_MESSAGE, {"reason": "no-longer-an-administrator"}
        )
    return administrators


def locked_staff_account(uow: UnitOfWork, user_id: UUID) -> Account:
    """Return the staff account with this key, locked for the rest of the transaction.

    Raises:
        NotFound: If no account has the key, or the account is a customer's.

    """
    account = uow.accounts.get_for_update(user_id)
    if account is None or account.role not in STAFF_ROLES:
        logger.info(
            "staff.account_not_found",
            extra={"user_id": str(user_id), "is_customer": account is not None},
        )
        raise NotFound(STAFF_NOT_FOUND_MESSAGE, {"user_id": str(user_id)})
    return account


def trading_branch_id(uow: UnitOfWork, branch_code: str) -> UUID:
    """Return the key of the trading branch with this code.

    Raises:
        ValidationFailure: Naming `branchCode`, when no trading branch has it.

    """
    branch = uow.branches.find_active_by_code(branch_code)
    if branch is None:
        logger.info("staff.branch_unknown", extra={"branch_code": branch_code})
        raise refused(wire_name(BRANCH_CODE), UNKNOWN_BRANCH_MESSAGE, {"branch": branch_code})
    return branch.id


def branch_code_of(uow: UnitOfWork, branch_id: UUID | None) -> str | None:
    """Return the code of a branch an account belongs to, or None for no branch."""
    if branch_id is None:
        return None
    branch = uow.branches.get(branch_id)
    return branch.code if branch is not None else None


def record_staff_change(
    uow: UnitOfWork,
    *,
    actor: Actor,
    account_id: UUID,
    action: str,
    now: datetime,
    before: Mapping[str, StateValue] | None,
    after: Mapping[str, StateValue],
) -> None:
    """Record the audit event of a change to a staff account, in the transaction of the change."""
    uow.audit.record(
        audit_event_for(
            actor=actor,
            entity_type=ACCOUNT_ENTITY_TYPE,
            entity_id=account_id,
            action=action,
            occurred_at=now,
            before_state=before,
            after_state=after,
        )
    )


class StaffAccountUseCase[CommandT, ResultT](UseCase[CommandT, ResultT]):
    """What every staff account write shares, the read its answer comes from."""

    def __init__(self, uow: UnitOfWork, clock: Clock, directory: StaffDirectory) -> None:
        """Keep the unit of work, the clock and the read the answer comes from."""
        super().__init__(uow, clock)
        self._directory = directory

    def _answer(self, user_id: UUID) -> StaffMember:
        """Return the account as the administrator reads it, read once the change committed.

        Raises:
            LookupError: If the account cannot be read back, which would mean
                the commit did not keep what it was handed.

        """
        member = self._directory.one(user_id)
        if member is None:
            raise LookupError(
                f"Attempted to read back staff account {user_id} after writing it, and it could "
                "not be read."
            )
        return member


__all__ = [
    "ACTIVE_KEY",
    "BRANCH_KEY",
    "CHANGED_KEY",
    "ROLE_KEY",
    "STAFF_DEACTIVATED_ACTION",
    "STAFF_OPENED_ACTION",
    "STAFF_REACTIVATED_ACTION",
    "STAFF_UPDATED_ACTION",
    "StaffAccountUseCase",
    "branch_code_of",
    "locked_administrators",
    "locked_staff_account",
    "record_staff_change",
    "trading_branch_id",
]
